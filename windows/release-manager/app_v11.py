from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import app_v10 as previous
from drowned_shared.chunking import ChunkBuilder
from drowned_shared.github_client import GitHubClient
from drowned_shared.metadata import load_catalog
from drowned_shared.turbo_upload import choose_upload_plan
from drowned_shared.util import format_bytes, slugify

from game_prepare import (
    PreparedGame,
    cleanup_after_verified_publish,
    confirm_test_success,
    launch_game,
    prepare_game,
    process_snapshot,
    save_job,
    terminate_process_tree,
)

APP_VERSION = "0.11.0"


def _duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _rate(value: float) -> str:
    return "—" if value <= 0 else f"{format_bytes(int(value))}/sn"


class PreparationTelemetryPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("infoCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 13, 14, 13)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("CANLI İŞLEM İSTATİSTİKLERİ")
        title.setObjectName("cardTitle")
        self.status = QLabel("Hazır")
        self.status.setObjectName("cardHint")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.status)
        outer.addLayout(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)
        self.percent = self._metric(grid, 0, 0, "İLERLEME")
        self.transferred = self._metric(grid, 0, 1, "İŞLENEN")
        self.speed = self._metric(grid, 0, 2, "ANLIK HIZ")
        self.average = self._metric(grid, 0, 3, "ORTALAMA")
        self.eta = self._metric(grid, 1, 0, "ETA")
        self.elapsed = self._metric(grid, 1, 1, "GEÇEN")
        self.connections = self._metric(grid, 1, 2, "BAĞLANTI")
        self.disk = self._metric(grid, 1, 3, "DİSK BOŞ")
        outer.addLayout(grid)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        outer.addWidget(self.progress)

        self.detail = QLabel("İşlem bekleniyor")
        self.detail.setObjectName("muted")
        self.detail.setWordWrap(True)
        outer.addWidget(self.detail)

    @staticmethod
    def _metric(grid: QGridLayout, row: int, col: int, caption: str) -> QLabel:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        name = QLabel(caption)
        name.setObjectName("muted")
        value = QLabel("—")
        value.setStyleSheet("color:#ffffff;font-size:15px;font-weight:700")
        layout.addWidget(name)
        layout.addWidget(value)
        grid.addWidget(box, row, col)
        return value

    def reset(self):
        self.status.setText("Hazır")
        self.progress.setValue(0)
        for label in (
            self.percent,
            self.transferred,
            self.speed,
            self.average,
            self.eta,
            self.elapsed,
            self.connections,
            self.disk,
        ):
            label.setText("—")
        self.detail.setText("İşlem bekleniyor")

    def update_snapshot(self, snapshot: dict):
        phase = str(snapshot.get("phase") or "")
        labels = {
            "download": "İndiriliyor",
            "verify": "İndirme doğrulanıyor",
            "extract": "Arşiv çıkartılıyor",
            "ready_test": "Oyun testi için hazır",
            "test": "Oyun çalıştırıldı / test ediliyor",
            "cleanup": "Disk temizliği",
            "remote_verify": "GitHub yayını doğrulanıyor",
            "complete": "Tamamlandı",
        }
        self.status.setText(labels.get(phase, phase or "Çalışıyor"))
        progress = max(0.0, min(1.0, float(snapshot.get("progress") or 0.0)))
        self.progress.setValue(int(progress * 1000))
        self.percent.setText(f"%{progress * 100:.1f}")

        done = max(0, int(snapshot.get("done") or 0))
        total = max(0, int(snapshot.get("total") or 0))
        self.transferred.setText(
            f"{format_bytes(done)} / {format_bytes(total)}" if total else format_bytes(done)
        )
        self.speed.setText(_rate(float(snapshot.get("speed") or 0.0)))
        self.average.setText(_rate(float(snapshot.get("average_speed") or 0.0)))
        self.eta.setText(_duration(snapshot.get("eta")))
        self.elapsed.setText(_duration(snapshot.get("elapsed")))

        active = snapshot.get("active_connections")
        connections = snapshot.get("connections")
        if connections:
            self.connections.setText(
                f"{int(active or 0)} / {int(connections)}" if active is not None else str(connections)
            )
        else:
            self.connections.setText("—")

        free = int(snapshot.get("disk_free") or 0)
        self.disk.setText(format_bytes(free) if free else "—")

        detail = str(snapshot.get("detail") or "")
        files_total = int(snapshot.get("files_total") or 0)
        if files_total:
            detail += f" • Dosya {int(snapshot.get('files_done') or 0)}/{files_total}"
        self.detail.setText(detail or "Çalışıyor")


class PreparationWorker(QObject):
    telemetry = Signal(object)
    log = Signal(str)
    done = Signal(object)
    error = Signal(str)

    def __init__(self, title: str, urls: list[str], download_dir: str, connections: int):
        super().__init__()
        self.title = title
        self.urls = urls
        self.download_dir = download_dir
        self.connections = connections
        self.cancelled = False

    def run(self):
        try:
            result = prepare_game(
                self.title,
                self.urls,
                self.download_dir,
                self.connections,
                telemetry=self.telemetry.emit,
                log=self.log.emit,
                cancelled=lambda: self.cancelled,
            )
            self.done.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class RemoteVerifyWorker(QObject):
    status = Signal(object)
    log = Signal(str)
    done = Signal(object)
    error = Signal(str)

    def __init__(self, params: dict, tag: str, published_after: float):
        super().__init__()
        self.params = params
        self.tag = tag
        self.published_after = published_after
        self.cancelled = False

    @staticmethod
    def _parse_github_time(value: str) -> float:
        if not value:
            return 0.0
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0

    def _workflow_success(self, client: GitHubClient) -> tuple[bool, str]:
        url = (
            f"https://api.github.com/repos/{client.owner}/{client.repo}/actions/workflows/"
            "update-game-list.yml/runs"
        )
        data = client._request(
            "GET",
            url,
            params={"branch": client.branch, "event": "push", "per_page": 30},
        ) or {}
        suitable = []
        for run in data.get("workflow_runs") or []:
            created = self._parse_github_time(str(run.get("created_at") or ""))
            if created >= self.published_after - 90:
                suitable.append(run)
        if not suitable:
            return False, "Game List Action henüz görünmüyor"
        suitable.sort(key=lambda item: self._parse_github_time(str(item.get("created_at") or "")), reverse=True)
        latest = suitable[0]
        status = str(latest.get("status") or "")
        conclusion = str(latest.get("conclusion") or "")
        if status == "completed" and conclusion == "success":
            return True, f"Game List Action başarılı • run #{latest.get('run_number')}"
        if status == "completed":
            return False, f"Game List Action tamamlandı ama sonuç: {conclusion or '?'}"
        return False, f"Game List Action çalışıyor: {status or '?'}"

    def _check(self, client: GitHubClient) -> tuple[bool, list[str]]:
        p = self.params
        title = p["title"]
        platform = slugify(p["platform"])
        channel = slugify(p["channel"])
        version = p["version"]
        game_id = slugify(title)
        messages: list[str] = []

        release = client.release_by_tag(self.tag)
        release_ok = bool(release and not release.get("draft"))
        messages.append(("✓" if release_ok else "○") + " GitHub Release görünür")

        catalog = load_catalog(client)
        game = next(
            (
                g
                for g in catalog.get("games", [])
                if g.get("id") == game_id and g.get("platform") == platform
            ),
            None,
        )
        channel_data = ((game or {}).get("channels") or {}).get(channel) or {}
        catalog_ok = (
            str(channel_data.get("tag") or "") == self.tag
            and str(channel_data.get("version") or "") == str(version)
        )
        messages.append(("✓" if catalog_ok else "○") + " catalog.json build kaydı")

        manifest = None
        manifest_path = str(channel_data.get("manifest_path") or "")
        if manifest_path:
            try:
                manifest = client.raw_json(manifest_path)
            except Exception:
                manifest = None
        manifest_ok = bool(manifest and str((manifest.get("release") or {}).get("tag") or "") == self.tag)
        messages.append(("✓" if manifest_ok else "○") + " raw manifest")

        assets_ok = False
        if release_ok and manifest_ok:
            expected = {
                str(chunk.get("name") or ""): int(chunk.get("size") or 0)
                for chunk in manifest.get("chunks") or []
                if chunk.get("name")
            }
            actual = {
                str(asset.get("name") or ""): int(asset.get("size") or 0)
                for asset in release.get("assets") or []
            }
            assets_ok = (
                "manifest.json" in actual
                and bool(expected)
                and all(name in actual and actual[name] == size for name, size in expected.items())
            )
            messages.append(
                ("✓" if assets_ok else "○")
                + f" Release assetleri {sum(1 for name in expected if name in actual)}/{len(expected)}"
            )
        else:
            messages.append("○ Release assetleri bekleniyor")

        game_list_ok = False
        raw = client.raw_content("game-list.md")
        if raw:
            text = raw.decode("utf-8", errors="replace")
            game_list_ok = self.tag in text and title in text and str(version) in text
        messages.append(("✓" if game_list_ok else "○") + " game-list.md build satırı")

        action_ok, action_text = self._workflow_success(client)
        messages.append(("✓ " if action_ok else "○ ") + action_text)

        return release_ok and catalog_ok and manifest_ok and assets_ok and game_list_ok and action_ok, messages

    def run(self):
        try:
            p = self.params
            client = GitHubClient(p["token"], p["owner"], p["repo"], p["branch"])
            client.repo_info()
            started = time.monotonic()
            timeout = 10 * 60
            last_messages: list[str] = []
            while not self.cancelled and time.monotonic() - started < timeout:
                ok, messages = self._check(client)
                last_messages = messages
                elapsed = time.monotonic() - started
                progress = sum(1 for text in messages if text.startswith("✓")) / max(len(messages), 1)
                self.status.emit({
                    "phase": "remote_verify",
                    "done": int(progress * 1000),
                    "total": 1000,
                    "progress": progress,
                    "speed": 0.0,
                    "average_speed": 0.0,
                    "elapsed": elapsed,
                    "eta": None,
                    "detail": " • ".join(messages),
                })
                for message in messages:
                    self.log.emit(message)
                if ok:
                    self.done.emit({"tag": self.tag, "checks": messages})
                    return
                time.sleep(8)
            if self.cancelled:
                raise RuntimeError("Remote doğrulama iptal edildi.")
            raise RuntimeError(
                "10 dakika içinde tüm remote doğrulama kapıları geçilemedi. "
                "Yerel oyun dosyaları KORUNDU.\n\n" + "\n".join(last_messages)
            )
        except Exception as exc:
            self.error.emit(str(exc))


class Manager(previous.Manager):
    """Release Manager v11: URL preparation, live statistics, test-gated cleanup and remote-verified cleanup."""

    def __init__(self):
        self.prep_thread = None
        self.prep_worker = None
        self.prepared_game: PreparedGame | None = None
        self.test_timer = None
        self.test_started_at = 0.0
        self.test_window_seen = False
        self.remote_thread = None
        self.remote_worker = None
        self._publish_started_epoch = 0.0
        self._last_publish_params: dict | None = None
        super().__init__()
        self.setWindowTitle(
            f"Drowned Release Manager {APP_VERSION} • Automated Preparation + Verified Cleanup"
        )
        tabs = self.centralWidget()
        if isinstance(tabs, QTabWidget):
            tabs.insertTab(0, self._automation_tab(), "Otomatik Hazırlama")

    def _automation_tab(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(16, 16, 16, 18)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Oyun indir • çıkart • test et • yayınla")
        title.setStyleSheet("font-size:28px;font-weight:800;color:white")
        self.new_game_button = QPushButton("Yeni oyun")
        self.new_game_button.clicked.connect(self.reset_for_new_game)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.new_game_button)
        outer.addLayout(header)

        note = QLabel(
            "Verdiğin doğrudan HTTP/HTTPS URL seçtiğin klasöre indirilir. Range destekleniyorsa paralel "
            "segmentler ve resume kullanılır. Arşiv aynı disk içinde çıkartılır. Oyun otomatik açılır; "
            "RAR/ZIP/7Z ancak sen BAŞARILI dedikten sonra silinir. Yerel oyun dosyaları ise yalnız GitHub "
            "Release + manifest + catalog + Game List Action + game-list.md birlikte doğrulandıktan sonra silinir."
        )
        note.setWordWrap(True)
        note.setObjectName("cardHint")
        outer.addWidget(note)

        source_card = QFrame()
        source_card.setObjectName("infoCard")
        form = QFormLayout(source_card)
        self.prep_title = QLineEdit()
        self.prep_title.setPlaceholderText("Oyun adı")
        self.prep_urls = QPlainTextEdit()
        self.prep_urls.setPlaceholderText("Her satıra bir doğrudan HTTP/HTTPS dosya URL'si")
        self.prep_urls.setMaximumHeight(90)
        self.prep_download_dir = QLineEdit()
        self.prep_download_dir.setReadOnly(True)
        choose_download = QPushButton("İndirme klasörü seç")
        choose_download.clicked.connect(self.pick_download_dir)
        download_row = QHBoxLayout()
        download_row.setContentsMargins(0, 0, 0, 0)
        download_row.addWidget(self.prep_download_dir, 1)
        download_row.addWidget(choose_download)
        download_widget = QWidget()
        download_widget.setLayout(download_row)

        self.prep_connections = QComboBox()
        self.prep_connections.addItem("Otomatik", 0)
        for count in (4, 8, 16, 24, 32):
            self.prep_connections.addItem(str(count), count)

        form.addRow("Oyun adı", self.prep_title)
        form.addRow("URL / URL'ler", self.prep_urls)
        form.addRow("İndir + çıkart klasörü", download_widget)
        form.addRow("Paralel bağlantı", self.prep_connections)
        outer.addWidget(source_card)

        action_row = QHBoxLayout()
        self.prepare_button = QPushButton("İNDİR + ÇIKART + EXE BUL + OYUNU AÇ")
        self.prepare_button.setObjectName("primary")
        self.prepare_button.clicked.connect(self.start_preparation)
        self.cancel_prepare_button = QPushButton("İptal")
        self.cancel_prepare_button.setObjectName("danger")
        self.cancel_prepare_button.setEnabled(False)
        self.cancel_prepare_button.clicked.connect(self.cancel_preparation)
        action_row.addWidget(self.prepare_button, 1)
        action_row.addWidget(self.cancel_prepare_button)
        outer.addLayout(action_row)

        self.prep_monitor = PreparationTelemetryPanel()
        outer.addWidget(self.prep_monitor)

        test_card = QFrame()
        test_card.setObjectName("infoCard")
        test_layout = QVBoxLayout(test_card)
        test_header = QHBoxLayout()
        test_title = QLabel("OYUN TESTİ")
        test_title.setObjectName("cardTitle")
        self.test_state = QLabel("Henüz oyun hazırlanmadı")
        self.test_state.setObjectName("cardHint")
        test_header.addWidget(test_title)
        test_header.addStretch()
        test_header.addWidget(self.test_state)
        test_layout.addLayout(test_header)
        self.test_detail = QLabel("EXE tespit edildikten sonra oyun otomatik çalıştırılacak.")
        self.test_detail.setWordWrap(True)
        self.test_detail.setObjectName("muted")
        test_layout.addWidget(self.test_detail)
        test_buttons = QHBoxLayout()
        self.test_success_button = QPushButton("BAŞARILI • Arşivleri sil")
        self.test_success_button.setObjectName("primary")
        self.test_success_button.setEnabled(False)
        self.test_success_button.clicked.connect(self.confirm_game_success)
        self.test_fail_button = QPushButton("BAŞARISIZ • Dosyaları koru")
        self.test_fail_button.setObjectName("danger")
        self.test_fail_button.setEnabled(False)
        self.test_fail_button.clicked.connect(self.confirm_game_failure)
        self.retry_test_button = QPushButton("Oyunu tekrar aç")
        self.retry_test_button.setEnabled(False)
        self.retry_test_button.clicked.connect(self.start_game_test)
        test_buttons.addWidget(self.test_success_button)
        test_buttons.addWidget(self.test_fail_button)
        test_buttons.addWidget(self.retry_test_button)
        test_buttons.addStretch()
        test_layout.addLayout(test_buttons)
        outer.addWidget(test_card)

        upload_card = QFrame()
        upload_card.setObjectName("infoCard")
        upload_form = QFormLayout(upload_card)
        self.auto_upload_source = QLineEdit()
        self.auto_upload_source.setReadOnly(True)
        self.choose_upload_button = QPushButton("Yüklenecek klasörü seç")
        self.choose_upload_button.setEnabled(False)
        self.choose_upload_button.clicked.connect(self.pick_upload_source)
        upload_row = QHBoxLayout()
        upload_row.setContentsMargins(0, 0, 0, 0)
        upload_row.addWidget(self.auto_upload_source, 1)
        upload_row.addWidget(self.choose_upload_button)
        upload_widget = QWidget()
        upload_widget.setLayout(upload_row)
        self.upload_cleanup_state = QLabel(
            "Final otomatik silme yalnız bu job'ın oluşturduğu extraction ağacındaki bir klasör yüklenirse aktif olur."
        )
        self.upload_cleanup_state.setWordWrap(True)
        self.upload_cleanup_state.setObjectName("muted")
        self.open_publish_button = QPushButton("Yeni Yayın sekmesine aktar")
        self.open_publish_button.setEnabled(False)
        self.open_publish_button.clicked.connect(self.open_publish_tab)
        upload_form.addRow("Upload klasörü", upload_widget)
        upload_form.addRow("Final cleanup", self.upload_cleanup_state)
        upload_form.addRow("", self.open_publish_button)
        outer.addWidget(upload_card)

        self.prep_logs = QPlainTextEdit()
        self.prep_logs.setReadOnly(True)
        self.prep_logs.setMinimumHeight(135)
        self.prep_logs.setMaximumHeight(190)
        outer.addWidget(self.prep_logs)
        outer.addStretch()
        return page

    def pick_download_dir(self):
        path = QFileDialog.getExistingDirectory(self, "İndirme ve extraction klasörü")
        if path:
            self.prep_download_dir.setText(path)

    def start_preparation(self):
        if self.prep_worker is not None:
            return
        title = self.prep_title.text().strip()
        urls = [line.strip() for line in self.prep_urls.toPlainText().splitlines() if line.strip()]
        target = self.prep_download_dir.text().strip()
        if not title or not urls or not target:
            QMessageBox.warning(
                self,
                "Eksik bilgi",
                "Oyun adı, en az bir HTTP/HTTPS URL ve indirme klasörü gerekli.",
            )
            return
        if any(not (url.startswith("http://") or url.startswith("https://")) for url in urls):
            QMessageBox.warning(self, "URL geçersiz", "Tüm URL'ler http:// veya https:// ile başlamalı.")
            return

        self._clear_current_test_process()
        self.prepared_game = None
        self.auto_upload_source.clear()
        self.open_publish_button.setEnabled(False)
        self.choose_upload_button.setEnabled(False)
        self.test_success_button.setEnabled(False)
        self.test_fail_button.setEnabled(False)
        self.retry_test_button.setEnabled(False)
        self.test_state.setText("Hazırlanıyor")
        self.test_detail.setText("İndirme ve extraction tamamlandıktan sonra oyun otomatik açılacak.")
        self.prep_monitor.reset()
        self.prep_logs.clear()
        self.prep_logs.appendPlainText(f"Yeni job: {title}")
        self.prep_logs.appendPlainText(f"Hedef: {target}")
        self.prepare_button.setEnabled(False)
        self.cancel_prepare_button.setEnabled(True)
        self.new_game_button.setEnabled(False)

        self.prep_thread = QThread()
        self.prep_worker = PreparationWorker(
            title,
            urls,
            target,
            int(self.prep_connections.currentData() or 0),
        )
        self.prep_worker.moveToThread(self.prep_thread)
        self.prep_thread.started.connect(self.prep_worker.run)
        self.prep_worker.telemetry.connect(self.prep_monitor.update_snapshot)
        self.prep_worker.log.connect(self.prep_logs.appendPlainText)
        self.prep_worker.done.connect(self._preparation_done)
        self.prep_worker.error.connect(self._preparation_error)
        self.prep_worker.done.connect(self.prep_thread.quit)
        self.prep_worker.error.connect(self.prep_thread.quit)
        self.prep_thread.start()

    def cancel_preparation(self):
        if self.prep_worker is not None:
            self.prep_worker.cancelled = True
            self.prep_logs.appendPlainText("İptal istendi; mevcut parça state'i resume için korunacak.")

    def _preparation_done(self, prepared: PreparedGame):
        self.prep_worker = None
        self.prepare_button.setEnabled(True)
        self.cancel_prepare_button.setEnabled(False)
        self.new_game_button.setEnabled(True)
        self.prepared_game = prepared
        self.prep_logs.appendPlainText(f"✓ Hazırlama tamamlandı: {prepared.game_root}")
        self.prep_logs.appendPlainText(f"✓ EXE: {prepared.executable}")
        self.test_state.setText("EXE bulundu • oyun açılıyor")
        self.retry_test_button.setEnabled(True)
        self.start_game_test()

    def _preparation_error(self, message: str):
        self.prep_worker = None
        self.prepare_button.setEnabled(True)
        self.cancel_prepare_button.setEnabled(False)
        self.new_game_button.setEnabled(True)
        self.test_state.setText("Hazırlama başarısız")
        self.prep_logs.appendPlainText(f"HATA: {message}")
        QMessageBox.critical(self, "Oyun hazırlama hatası", message)

    def start_game_test(self):
        if not self.prepared_game:
            return
        self._clear_current_test_process()
        try:
            pid = launch_game(self.prepared_game.executable)
        except Exception as exc:
            self.test_state.setText("Oyun başlatılamadı")
            self.test_detail.setText(str(exc))
            self.test_fail_button.setEnabled(True)
            return

        self.prepared_game.test_pid = pid
        save_job(self.prepared_game)
        self.test_started_at = time.monotonic()
        self.test_window_seen = False
        self.test_success_button.setEnabled(False)
        self.test_fail_button.setEnabled(True)
        self.retry_test_button.setEnabled(False)
        self.test_state.setText(f"Çalışıyor • PID {pid}")
        self.prep_logs.appendPlainText(f"Oyun başlatıldı • PID {pid}")

        self.test_timer = QTimer(self)
        self.test_timer.setInterval(1000)
        self.test_timer.timeout.connect(self._poll_game_test)
        self.test_timer.start()
        self._poll_game_test()

    def _poll_game_test(self):
        if not self.prepared_game or not self.prepared_game.test_pid:
            return
        elapsed = max(0.0, time.monotonic() - self.test_started_at)
        snap = process_snapshot(self.prepared_game.test_pid)
        alive = bool(snap.get("alive"))
        window = bool(snap.get("window"))
        self.test_window_seen = self.test_window_seen or window
        memory = int(snap.get("memory") or 0)
        cpu = float(snap.get("cpu") or 0.0)
        children = int(snap.get("children") or 0)

        self.prep_monitor.update_snapshot({
            "phase": "test",
            "done": int(min(elapsed, 30)),
            "total": 30,
            "progress": min(1.0, elapsed / 30.0),
            "speed": 0.0,
            "average_speed": 0.0,
            "elapsed": elapsed,
            "eta": max(0.0, 30.0 - elapsed),
            "detail": (
                f"PID {self.prepared_game.test_pid} • Process {'çalışıyor' if alive else 'kapandı'} • "
                f"Window {'var' if self.test_window_seen else 'bekleniyor'} • "
                f"Child {children} • RAM {format_bytes(memory)} • CPU %{cpu:.1f}"
            ),
            "disk_free": 0,
        })
        self.test_detail.setText(
            f"EXE: {self.prepared_game.executable}\n"
            f"Process: {'✓ çalışıyor' if alive else '✕ kapandı'} • "
            f"Pencere: {'✓ bulundu' if self.test_window_seen else '○ henüz yok'} • "
            f"Child process: {children} • RAM: {format_bytes(memory)} • CPU: %{cpu:.1f} • "
            f"Süre: {_duration(elapsed)}"
        )

        if not alive:
            self.test_state.setText("Process kapandı • başarısız görünüyor")
            self.test_success_button.setEnabled(False)
            self.retry_test_button.setEnabled(True)
            if self.test_timer:
                self.test_timer.stop()
            return

        if elapsed >= 5:
            self.test_success_button.setEnabled(True)
        if elapsed >= 30:
            self.test_state.setText(
                "30 sn smoke test geçti • görsel kontrolüne göre BAŞARILI / BAŞARISIZ seç"
            )
        elif self.test_window_seen:
            self.test_state.setText("Oyun penceresi bulundu • görsel kontrol bekleniyor")
        else:
            self.test_state.setText("Process çalışıyor • pencere bekleniyor")

    def confirm_game_success(self):
        if not self.prepared_game:
            return
        self.test_success_button.setEnabled(False)
        self.test_fail_button.setEnabled(False)
        self.retry_test_button.setEnabled(False)
        try:
            freed = confirm_test_success(self.prepared_game, self.prep_logs.appendPlainText)
        except Exception as exc:
            QMessageBox.critical(self, "Cleanup hatası", str(exc))
            return
        self._clear_current_test_process()
        self.test_state.setText("✓ Kullanıcı oyunu başarılı doğruladı")
        self.test_detail.setText(
            f"İndirilen arşiv/temp temizliği tamamlandı. Geri kazanılan alan: {format_bytes(freed)}.\n"
            f"Oyun dosyaları korunuyor: {self.prepared_game.game_root}"
        )
        self.prep_monitor.update_snapshot({
            "phase": "cleanup",
            "done": freed,
            "total": freed,
            "progress": 1.0,
            "speed": 0.0,
            "average_speed": 0.0,
            "elapsed": 0.0,
            "eta": 0.0,
            "detail": f"Test sonrası arşiv/temp cleanup • {format_bytes(freed)} geri kazanıldı",
            "disk_free": 0,
        })
        self.choose_upload_button.setEnabled(True)
        self.game_title.setText(self.prepared_game.title)

    def confirm_game_failure(self):
        if not self.prepared_game:
            return
        self._clear_current_test_process()
        self.test_state.setText("Başarısız olarak işaretlendi")
        self.test_detail.setText(
            "Arşiv ve oyun dosyaları KORUNDU. EXE seçimini/dosyaları kontrol edip tekrar test edebilirsin."
        )
        self.test_success_button.setEnabled(False)
        self.test_fail_button.setEnabled(False)
        self.retry_test_button.setEnabled(True)
        self.prep_logs.appendPlainText("Test kullanıcı tarafından başarısız işaretlendi; hiçbir dosya silinmedi.")

    def _clear_current_test_process(self):
        if self.test_timer is not None:
            self.test_timer.stop()
            self.test_timer.deleteLater()
            self.test_timer = None
        if self.prepared_game and self.prepared_game.test_pid:
            terminate_process_tree(self.prepared_game.test_pid)
            self.prepared_game.test_pid = None
            try:
                save_job(self.prepared_game)
            except Exception:
                pass

    def pick_upload_source(self):
        if not self.prepared_game or not self.prepared_game.user_confirmed:
            QMessageBox.warning(self, "Test onayı gerekli", "Önce oyunu BAŞARILI olarak onayla.")
            return
        path = QFileDialog.getExistingDirectory(
            self,
            "GitHub'a yüklenecek klasör",
            self.prepared_game.game_root,
        )
        if not path:
            return
        self.auto_upload_source.setText(path)
        self._apply_publish_source(path)
        extraction = Path(self.prepared_game.extraction_root).resolve()
        source = Path(path).resolve()
        try:
            source.relative_to(extraction)
            cleanup_ok = extraction != Path(self.prepared_game.download_dir).resolve()
        except ValueError:
            cleanup_ok = False
        if cleanup_ok:
            self.upload_cleanup_state.setText(
                "✓ Bu klasör v11 job'ının oluşturduğu extraction ağacında. "
                "Remote release + catalog + manifest + Game List Action + game-list.md doğrulanırsa "
                "extraction kökü otomatik silinecek."
            )
        else:
            self.upload_cleanup_state.setText(
                "⚠ Bu klasör job-owned extraction ağacında değil. Güvenlik nedeniyle yayın sonrası otomatik silinmeyecek."
            )
        self.open_publish_button.setEnabled(True)

    def _apply_publish_source(self, path: str):
        self.source.setText(path)
        try:
            probe = ChunkBuilder(Path(path))
            plan = choose_upload_plan(probe.total_size)
            chunks = int(plan["chunk_count"])
            waves = int(plan["waves"])
            workers = int(plan["workers"])
            chunk_size = int(plan["chunk_size"])
            wave_text = "tek dalga" if waves == 1 else f"{waves} tam dalga"
            self.plan.setText(
                f"<b>✓ Upload klasörü hazır</b><br>"
                f"Kaynak: {format_bytes(probe.total_size)} • Chunk: {chunks} • "
                f"Hedef chunk: {format_bytes(chunk_size)}<br>"
                f"Balanced plan: <b>{workers} paralel stream × {wave_text}</b> • Temp BIN: 0 B"
            )
        except Exception as exc:
            self.plan.setText(f"Upload plan hatası: {exc}")

    def open_publish_tab(self):
        tabs = self.centralWidget()
        if isinstance(tabs, QTabWidget):
            for index in range(tabs.count()):
                if tabs.tabText(index) == "Yeni Yayın":
                    tabs.setCurrentIndex(index)
                    break

    def reset_for_new_game(self):
        if self.prep_worker is not None:
            return
        self._clear_current_test_process()
        self.prepared_game = None
        self.prep_title.clear()
        self.prep_urls.clear()
        self.prep_download_dir.clear()
        self.auto_upload_source.clear()
        self.prep_logs.clear()
        self.prep_monitor.reset()
        self.test_state.setText("Henüz oyun hazırlanmadı")
        self.test_detail.setText("EXE tespit edildikten sonra oyun otomatik çalıştırılacak.")
        self.test_success_button.setEnabled(False)
        self.test_fail_button.setEnabled(False)
        self.retry_test_button.setEnabled(False)
        self.choose_upload_button.setEnabled(False)
        self.open_publish_button.setEnabled(False)
        self.upload_cleanup_state.setText(
            "Final otomatik silme yalnız bu job'ın oluşturduğu extraction ağacındaki bir klasör yüklenirse aktif olur."
        )

        self.game_title.clear()
        self.version.setText("1.0.0")
        self.description.clear()
        self.source.clear()
        self.progress.setValue(0)
        self.logs.clear()
        if hasattr(self, "upload_monitor"):
            self.upload_monitor.reset()
        self.plan.setText("Kaynak klasörü seçildiğinde plan hesaplanır.")
        self._steam_app_id = None
        for attr in ("hero", "cover", "logo", "icon", "screenshots", "trailer_panel"):
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            if hasattr(widget, "reset"):
                try:
                    widget.reset()
                    continue
                except TypeError:
                    pass
            if hasattr(widget, "path"):
                widget.path = ""
            if hasattr(widget, "paths"):
                try:
                    widget.paths.clear()
                except Exception:
                    widget.paths = []
            if hasattr(widget, "trailers"):
                try:
                    widget.trailers.clear()
                except Exception:
                    widget.trailers = []
        self.prep_logs.appendPlainText(
            "Yeni oyun formu açıldı; önceki oyunun UI bilgileri temizlendi. Diskteki kullanıcı dosyalarına dokunulmadı."
        )

    def publish(self):
        self._publish_started_epoch = time.time()
        self._last_publish_params = {
            **self._params(),
            "source": self.source.text().strip(),
            "title": self.game_title.text().strip(),
            "platform": self.platform.currentText(),
            "channel": self.channel.currentText(),
            "version": self.version.text().strip(),
        }
        super().publish()

    def on_done(self, tag):
        super().on_done(tag)
        if not self.prepared_game or not self.prepared_game.user_confirmed:
            return
        source = self.source.text().strip()
        extraction = Path(self.prepared_game.extraction_root).resolve()
        try:
            Path(source).resolve().relative_to(extraction)
            owned_source = extraction != Path(self.prepared_game.download_dir).resolve()
        except (ValueError, OSError):
            owned_source = False
        if not owned_source:
            self.prep_logs.appendPlainText(
                "Yayın tamamlandı ancak kaynak job-owned extraction ağacında değil; otomatik final cleanup yapılmayacak."
            )
            return
        if not self._last_publish_params:
            return
        self._start_remote_verification(tag)

    def _start_remote_verification(self, tag: str):
        if self.remote_worker is not None:
            return
        self.prep_logs.appendPlainText("Remote yayın doğrulaması başladı; yerel oyun henüz silinmeyecek.")
        self.remote_thread = QThread()
        self.remote_worker = RemoteVerifyWorker(
            dict(self._last_publish_params or {}),
            tag,
            self._publish_started_epoch,
        )
        self.remote_worker.moveToThread(self.remote_thread)
        self.remote_thread.started.connect(self.remote_worker.run)
        self.remote_worker.status.connect(self.prep_monitor.update_snapshot)
        self.remote_worker.log.connect(self.prep_logs.appendPlainText)
        self.remote_worker.done.connect(self._remote_verify_done)
        self.remote_worker.error.connect(self._remote_verify_error)
        self.remote_worker.done.connect(self.remote_thread.quit)
        self.remote_worker.error.connect(self.remote_thread.quit)
        self.remote_thread.start()

    def _remote_verify_done(self, result: dict):
        self.remote_worker = None
        if not self.prepared_game:
            return
        try:
            freed = cleanup_after_verified_publish(
                self.prepared_game,
                self.source.text().strip(),
                self.prep_logs.appendPlainText,
            )
        except Exception as exc:
            self.prep_logs.appendPlainText(f"Final cleanup yapılmadı: {exc}")
            QMessageBox.warning(
                self,
                "Yayın doğrulandı ancak cleanup yapılmadı",
                f"Remote yayın doğrulandı fakat güvenli local cleanup koşulu sağlanmadı:\n\n{exc}",
            )
            return
        self.prep_monitor.update_snapshot({
            "phase": "complete",
            "done": freed,
            "total": freed,
            "progress": 1.0,
            "speed": 0.0,
            "average_speed": 0.0,
            "elapsed": 0.0,
            "eta": 0.0,
            "detail": f"Remote doğrulandı • yerel oyun temizlendi • {format_bytes(freed)} geri kazanıldı",
            "disk_free": 0,
        })
        self.test_state.setText("✓ Yayın doğrulandı ve yerel oyun temizlendi")
        self.prep_logs.appendPlainText(
            f"✓ Release + manifest + catalog + Game List Action + game-list.md doğrulandı. "
            f"Yerel cleanup: {format_bytes(freed)}"
        )
        QMessageBox.information(
            self,
            "Yayın tamamen doğrulandı",
            f"{result.get('tag')} uzak tarafta tamamen doğrulandı.\n\n"
            f"Yerel oyun dosyaları otomatik temizlendi: {format_bytes(freed)}",
        )

    def _remote_verify_error(self, message: str):
        self.remote_worker = None
        self.prep_logs.appendPlainText(f"REMOTE DOĞRULAMA: {message}")
        QMessageBox.warning(
            self,
            "Yerel dosyalar korundu",
            "GitHub tarafındaki tüm doğrulama kapıları geçilemediği için yerel oyun dosyaları SİLİNMEDİ.\n\n"
            + message,
        )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Release Manager")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")

    style_module = previous
    visited = set()
    while style_module and id(style_module) not in visited:
        visited.add(id(style_module))
        if hasattr(style_module, "MODERN_STYLE"):
            app.setStyleSheet(style_module.MODERN_STYLE)
            break
        style_module = getattr(style_module, "previous", None)

    win = Manager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
