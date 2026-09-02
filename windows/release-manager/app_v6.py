from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import app_v5 as previous
from drowned_shared.upload_status import UploadStatusBroadcaster

APP_VERSION = "0.6.0"


def _format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours} sa {minutes:02d} dk"
    if minutes:
        return f"{minutes} dk {secs:02d} sn"
    return f"{secs} sn"


def _format_rate(value: float) -> str:
    if value <= 0:
        return "—"
    return f"{previous.legacy.format_bytes(int(value))}/sn"


class UploadTelemetryPanel(QFrame):
    """Read-only view of the existing uploader's live transfer state.

    It does not start, stop, throttle or reorder uploads. The panel only
    renders telemetry emitted by drowned_shared.publish.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("infoCard")
        self._started_at: float | None = None
        self._previous_at: float | None = None
        self._previous_bytes = 0
        self._smoothed_speed = 0.0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 13, 14, 13)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("CANLI YÜKLEME")
        title.setObjectName("cardTitle")
        self.status = QLabel("Hazır")
        self.status.setObjectName("cardHint")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.status)
        outer.addLayout(header)

        metrics = QHBoxLayout()
        metrics.setSpacing(22)
        self.metric_data = self._metric(metrics, "AKTARILAN")
        self.metric_now = self._metric(metrics, "ANLIK HIZ")
        self.metric_avg = self._metric(metrics, "ORTALAMA HIZ")
        self.metric_elapsed = self._metric(metrics, "GEÇEN SÜRE")
        self.metric_left = self._metric(metrics, "TAHMİNİ KALAN")
        self.metric_total = self._metric(metrics, "TAHMİNİ TOPLAM")
        outer.addLayout(metrics)

        self.overall = QProgressBar()
        self.overall.setRange(0, 1000)
        self.overall.setValue(0)
        self.overall.setTextVisible(False)
        self.overall.setStyleSheet(
            "QProgressBar{min-height:9px;max-height:9px;background:#0b1017;border:0;}"
            "QProgressBar::chunk{background:#66c0f4;}"
        )
        outer.addWidget(self.overall)

        self.stream_summary = QLabel("Aktif akış yok")
        self.stream_summary.setObjectName("muted")
        outer.addWidget(self.stream_summary)

        self.table = QTreeWidget()
        self.table.setHeaderLabels([
            "AKIŞ",
            "OYUN DOSYASI",
            "DOSYA İLERLEMESİ",
            "CHUNK İLERLEMESİ",
        ])
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(False)
        self.table.setFixedHeight(235)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 410)
        self.table.setColumnWidth(2, 220)
        self.table.setColumnWidth(3, 310)
        outer.addWidget(self.table)

        note = QLabel(
            "Dosya ilerlemesi, chunk segmentlerinin gerçekten gönderilen byte konumlarından hesaplanır. "
            "Bir dosya birden fazla chunk'a bölünmüşse aynı dosya birden fazla aktif akışta görünebilir."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        outer.addWidget(note)

    @staticmethod
    def _metric(row: QHBoxLayout, name: str) -> QLabel:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        caption = QLabel(name)
        caption.setObjectName("muted")
        value = QLabel("—")
        value.setStyleSheet("color:#ffffff;font-size:15px;font-weight:700")
        layout.addWidget(caption)
        layout.addWidget(value)
        row.addWidget(box, 1)
        return value

    def reset(self):
        self._started_at = None
        self._previous_at = None
        self._previous_bytes = 0
        self._smoothed_speed = 0.0
        self.status.setText("Hazır")
        for label in (
            self.metric_data,
            self.metric_now,
            self.metric_avg,
            self.metric_elapsed,
            self.metric_left,
            self.metric_total,
        ):
            label.setText("—")
        self.overall.setValue(0)
        self.stream_summary.setText("Aktif akış yok")
        self.table.clear()

    def update_snapshot(self, snapshot: dict):
        phase = str(snapshot.get("phase") or "upload")
        total = max(0, int(snapshot.get("total_size") or 0))
        sent = max(0, min(int(snapshot.get("total_sent") or 0), total if total else 0))
        workers = max(1, int(snapshot.get("workers") or 1))
        chunk_count = max(0, int(snapshot.get("chunk_count") or 0))
        completed = max(0, int(snapshot.get("completed_chunks") or 0))
        active = list(snapshot.get("active") or [])
        now = time.monotonic()

        if self._started_at is None and phase in {"plan", "upload"}:
            self._started_at = now
            self._previous_at = now
            self._previous_bytes = sent

        instant = 0.0
        if self._previous_at is not None:
            elapsed_sample = now - self._previous_at
            delta = sent - self._previous_bytes
            if elapsed_sample > 0 and delta >= 0:
                instant = delta / elapsed_sample
                if instant > 0:
                    self._smoothed_speed = (
                        instant
                        if self._smoothed_speed <= 0
                        else self._smoothed_speed * 0.72 + instant * 0.28
                    )
        self._previous_at = now
        self._previous_bytes = sent

        elapsed = max(0.0, now - self._started_at) if self._started_at is not None else 0.0
        average = sent / elapsed if sent > 0 and elapsed > 0 else 0.0
        eta_speed = self._smoothed_speed if self._smoothed_speed > 0 else average
        remaining = (total - sent) / eta_speed if eta_speed > 0 and total > sent else 0.0 if total and sent >= total else None
        estimated_total = elapsed + remaining if remaining is not None else None

        self.metric_data.setText(
            f"{previous.legacy.format_bytes(sent)} / {previous.legacy.format_bytes(total)}"
            if total else "—"
        )
        self.metric_now.setText(_format_rate(self._smoothed_speed or instant))
        self.metric_avg.setText(_format_rate(average))
        self.metric_elapsed.setText(_format_duration(elapsed))
        self.metric_left.setText(_format_duration(remaining))
        self.metric_total.setText(_format_duration(estimated_total))
        self.overall.setValue(int(sent * 1000 / max(total, 1)))

        if phase == "plan":
            self.status.setText("Release hazırlanıyor")
        elif phase == "metadata":
            self.status.setText("Oyun verisi tamamlandı • manifest / artwork / katalog yayınlanıyor")
        else:
            self.status.setText("Oyun dosyaları GitHub Release'e yükleniyor")

        self.stream_summary.setText(
            f"{len(active)}/{workers} aktif stream  •  {completed}/{chunk_count} chunk tamamlandı"
        )

        self.table.clear()
        for row in sorted(active, key=lambda item: int(item.get("index") or 0)):
            file_name = str(row.get("file") or "—")
            file_sent = max(0, int(row.get("file_sent") or 0))
            file_size = max(0, int(row.get("file_size") or 0))
            chunk_sent = max(0, int(row.get("chunk_sent") or 0))
            chunk_size = max(0, int(row.get("chunk_size") or 0))
            file_percent = int(file_sent * 100 / max(file_size, 1)) if file_size else 0
            chunk_percent = int(chunk_sent * 100 / max(chunk_size, 1)) if chunk_size else 0
            item = QTreeWidgetItem([
                f"#{int(row.get('index') or 0):02d}",
                file_name,
                (
                    f"{previous.legacy.format_bytes(file_sent)} / "
                    f"{previous.legacy.format_bytes(file_size)}  •  %{file_percent}"
                    if file_size else "—"
                ),
                (
                    f"{row.get('chunk') or 'chunk'}  •  "
                    f"{previous.legacy.format_bytes(chunk_sent)} / "
                    f"{previous.legacy.format_bytes(chunk_size)}  •  %{chunk_percent}"
                ),
            ])
            self.table.addTopLevelItem(item)

    def finish(self):
        self.status.setText("✓ Yayın tamamlandı")
        self.metric_left.setText("0 sn")
        self.overall.setValue(1000)
        self.stream_summary.setText("Tüm veri chunk'ları ve yayın metadatası tamamlandı")
        self.table.clear()

    def fail(self):
        self.status.setText("Yayın hata ile durdu")
        self.stream_summary.setText("Ayrıntı için aşağıdaki log alanına bak")


class TelemetryPublishWorker(previous.MediaPublishWorker):
    telemetry = Signal(object)

    def run(self):
        broadcaster = None
        try:
            p = self.params
            client = previous.GitHubClient(p["token"], p["owner"], p["repo"], p["branch"])
            client.repo_info()
            broadcaster = UploadStatusBroadcaster(
                client, "game", p["title"], p["platform"], p["channel"], p["version"]
            )

            def on_telemetry(snapshot):
                self.telemetry.emit(snapshot)
                broadcaster.update(snapshot)

            manifest = previous.publish_project(
                client,
                Path(p["source"]),
                p["title"],
                p["platform"],
                p["channel"],
                p["version"],
                p["description"],
                p["artwork"],
                progress=lambda sent, total: self.progress.emit(int(sent * 100 / max(total, 1))),
                log=self.log.emit,
                cancelled=lambda: self.cancelled,
                media=p.get("media") or None,
                detailed_progress=on_telemetry,
            )
            broadcaster.finish()
            self.done.emit(manifest["release"]["tag"])
        except Exception as exc:
            if broadcaster:
                broadcaster.fail(str(exc))
            self.error.emit(previous.legacy.permission_message(exc))


class Manager(previous.Manager):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Drowned Release Manager {APP_VERSION}")

    def _publish_tab(self):
        widget = super()._publish_tab()
        root = widget.layout()
        self.upload_monitor = UploadTelemetryPanel()
        insert_at = self._index_of(root, self.progress)
        root.insertWidget(insert_at, self.upload_monitor)
        return widget

    def publish(self):
        if not self.source.text() or not self.game_title.text().strip():
            previous.QMessageBox.warning(self, "Eksik", "Proje adı ve kaynak klasörü gerekli.")
            return
        if not self.token.text().strip():
            previous.QMessageBox.warning(
                self,
                "Token gerekli",
                "GitHub sekmesinden fine-grained PAT girip güvenli olarak kaydet.",
            )
            return

        media = {}
        if self.trailer_panel.trailers:
            media["trailers"] = list(self.trailer_panel.trailers)
        if self._steam_app_id:
            media["steam_app_id"] = int(self._steam_app_id)

        params = {
            **self._params(),
            "source": self.source.text(),
            "title": self.game_title.text().strip(),
            "platform": self.platform.currentText(),
            "channel": self.channel.currentText(),
            "version": self.version.text().strip(),
            "description": self.description.toPlainText(),
            "artwork": {
                "hero": self.hero.path,
                "cover": self.cover.path,
                "logo": self.logo.path,
                "icon": self.icon.path,
                "screenshots": list(self.screenshots.paths),
            },
            "media": media,
        }

        self.upload_monitor.reset()
        self.publish_button.setEnabled(False)
        self.logs.clear()
        self.thread = QThread()
        self.worker = TelemetryPublishWorker(params)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.logs.appendPlainText)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.telemetry.connect(self.upload_monitor.update_snapshot)
        self.worker.done.connect(self.on_done)
        self.worker.error.connect(self.on_error)
        self.worker.done.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.start()

    def on_done(self, tag):
        self.upload_monitor.finish()
        super().on_done(tag)

    def on_error(self, message):
        self.upload_monitor.fail()
        super().on_error(message)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Release Manager")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")
    app.setStyleSheet(previous.MODERN_STYLE)
    win = Manager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
