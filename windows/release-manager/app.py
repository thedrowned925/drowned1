from __future__ import annotations
import sys
from pathlib import Path
import keyring
from PySide6.QtCore import QObject, QSettings, QThread, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import *
from drowned_shared.chunking import ChunkBuilder
from drowned_shared.constants import CHUNK_SIZE_MIB, MAX_DATA_ASSETS, MAX_RELEASE_DATA_BYTES
from drowned_shared.deletion import delete_channel, delete_game
from drowned_shared.github_client import GitHubClient
from drowned_shared.metadata import load_catalog
from drowned_shared.publish import publish_project
from drowned_shared.util import format_bytes

STYLE = """
QWidget{background:#080b12;color:#edf2f7;font-family:'Segoe UI';font-size:14px}
QLineEdit,QComboBox,QTextEdit,QPlainTextEdit,QTreeWidget{background:#101622;border:1px solid #263247;border-radius:10px;padding:9px}
QPushButton{background:#172033;border:1px solid #2a3851;border-radius:10px;padding:10px 16px;font-weight:600}
QPushButton:hover{background:#202d45} QPushButton#primary{background:#5d6bff;border-color:#7681ff}
QPushButton#danger{background:#3a1519;border-color:#7a2831;color:#ffd9dc} QPushButton#danger:hover{background:#551d24}
QProgressBar{background:#101622;border:1px solid #263247;border-radius:8px;text-align:center;height:16px}
QProgressBar::chunk{background:#5d6bff;border-radius:7px}
QTabBar::tab{padding:12px 20px;background:#101622;margin:4px;border-radius:9px} QTabBar::tab:selected{background:#202d45}
QTreeWidget::item{padding:7px} QTreeWidget::item:selected{background:#263653}
"""
SERVICE = "DrownedReleaseManager"
ACCOUNT = "github_pat"

class PublishWorker(QObject):
    log = Signal(str); progress = Signal(int); done = Signal(str); error = Signal(str)
    def __init__(self, params):
        super().__init__(); self.params = params; self.cancelled = False
    def run(self):
        try:
            p=self.params
            client=GitHubClient(p['token'],p['owner'],p['repo'],p['branch']); client.repo_info()
            manifest=publish_project(client,Path(p['source']),p['title'],p['platform'],p['channel'],p['version'],p['description'],p['artwork'],progress=lambda sent,total:self.progress.emit(int(sent*100/max(total,1))),log=self.log.emit,cancelled=lambda:self.cancelled)
            self.done.emit(manifest['release']['tag'])
        except Exception as exc:
            self.error.emit(str(exc))

class DeleteWorker(QObject):
    log=Signal(str); done=Signal(str); error=Signal(str)
    def __init__(self,params,mode,record):
        super().__init__(); self.params=params; self.mode=mode; self.record=record
    def run(self):
        try:
            p=self.params; r=self.record
            client=GitHubClient(p['token'],p['owner'],p['repo'],p['branch']); client.repo_info()
            if self.mode=="channel":
                result=delete_channel(client,r['game_id'],r['platform'],r['channel'],log=self.log.emit)
            else:
                result=delete_game(client,r['game_id'],r['platform'],log=self.log.emit)
            self.done.emit(f"Silme tamamlandı • Release: {result['releases_deleted']} • Manifest: {result['manifests_deleted']} • Artwork: {len(result['artwork_deleted'])}")
        except Exception as exc:
            self.error.emit(str(exc))

class ArtworkPicker(QWidget):
    def __init__(self, label):
        super().__init__(); self.path=""; layout=QVBoxLayout(self)
        self.preview=QLabel(label); self.preview.setAlignment(Qt.AlignCenter); self.preview.setFixedHeight(105); self.preview.setStyleSheet("background:#05070c;border:1px dashed #33415b;border-radius:12px;color:#8390a3")
        button=QPushButton(label+" seç"); button.clicked.connect(self.pick); layout.addWidget(self.preview); layout.addWidget(button)
    def pick(self):
        path,_=QFileDialog.getOpenFileName(self,"Görsel seç","","Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.path=path; pix=QPixmap(path)
            if not pix.isNull(): self.preview.setPixmap(pix.scaled(self.preview.size(),Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation))

class Manager(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Drowned Release Manager"); self.resize(1160,860)
        self.settings=QSettings("Drowned","ReleaseManager"); self.thread=None; self.worker=None
        tabs=QTabWidget(); tabs.addTab(self._publish_tab(),"Yeni Yayın"); tabs.addTab(self._manage_tab(),"Yayınları Yönet"); tabs.addTab(self._settings_tab(),"GitHub"); self.setCentralWidget(tabs)

    def _params(self):
        return {'token':self.token.text(),'owner':self.owner.text().strip(),'repo':self.repo.text().strip(),'branch':self.branch.text().strip() or 'main'}

    def _settings_tab(self):
        w=QWidget(); v=QVBoxLayout(w); title=QLabel("GitHub Bağlantısı"); title.setStyleSheet("font-size:28px;font-weight:800"); v.addWidget(title)
        form=QFormLayout(); self.owner=QLineEdit(self.settings.value("owner","thedrowned925")); self.repo=QLineEdit(self.settings.value("repo","drowned1")); self.branch=QLineEdit(self.settings.value("branch","main")); self.token=QLineEdit(keyring.get_password(SERVICE,ACCOUNT) or ""); self.token.setEchoMode(QLineEdit.Password)
        form.addRow("Owner",self.owner); form.addRow("Repository",self.repo); form.addRow("Branch",self.branch); form.addRow("Fine-grained PAT",self.token); v.addLayout(form)
        row=QHBoxLayout(); save=QPushButton("Güvenli kaydet"); test=QPushButton("Bağlantıyı test et"); save.clicked.connect(self.save_settings); test.clicked.connect(self.test_connection); row.addWidget(save); row.addWidget(test); row.addStretch(); v.addLayout(row)
        note=QLabel("Token yalnızca işletim sistemi keyring/Windows Credential Manager içinde saklanır; kaynak koda yazılmaz. Okuma işlemlerinde katalog/manifest/artwork için raw.githubusercontent.com tercih edilir; REST API yalnızca yönetim yazmaları için kullanılır."); note.setWordWrap(True); note.setStyleSheet("color:#8d99aa"); v.addWidget(note); v.addStretch(); return w

    def _publish_tab(self):
        w=QWidget(); v=QVBoxLayout(w); title=QLabel("Yeni dağıtım"); title.setStyleSheet("font-size:28px;font-weight:800"); v.addWidget(title); v.addWidget(QLabel(f"RAR/ZIP yok • {CHUNK_SIZE_MIB} MiB streaming chunk • 999 veri asset + manifest"))
        form=QFormLayout(); self.game_title=QLineEdit(); self.platform=QComboBox(); self.platform.addItems(["PC","PS2","PS3","PS4","PS5","PSP","PS Vita","Xbox","Xbox 360","Xbox One","Xbox Series","Nintendo Switch","Android","Other"]); self.channel=QComboBox(); self.channel.addItems(["stable","beta","dev","nightly","archive"]); self.version=QLineEdit("1.0.0"); self.description=QTextEdit(); self.description.setFixedHeight(70); self.source=QLineEdit(); self.source.setReadOnly(True); choose=QPushButton("Klasör seç"); choose.clicked.connect(self.pick_source); source_row=QHBoxLayout(); source_row.addWidget(self.source); source_row.addWidget(choose); source_widget=QWidget(); source_widget.setLayout(source_row)
        form.addRow("Proje / oyun",self.game_title); form.addRow("Platform",self.platform); form.addRow("Kanal",self.channel); form.addRow("Sürüm",self.version); form.addRow("Kaynak",source_widget); form.addRow("Açıklama",self.description); v.addLayout(form)
        arts=QHBoxLayout(); self.hero=ArtworkPicker("Hero"); self.cover=ArtworkPicker("Cover"); self.logo=ArtworkPicker("Logo"); arts.addWidget(self.hero); arts.addWidget(self.cover); arts.addWidget(self.logo); v.addLayout(arts)
        self.plan=QLabel("Kaynak klasörü seçildiğinde plan hesaplanır."); self.plan.setStyleSheet("background:#101622;border:1px solid #202c40;border-radius:12px;padding:14px"); v.addWidget(self.plan); self.progress=QProgressBar(); v.addWidget(self.progress); self.logs=QPlainTextEdit(); self.logs.setReadOnly(True); self.logs.setFixedHeight(150); v.addWidget(self.logs); self.publish_button=QPushButton("GitHub’a taslak oluştur ve yayınla"); self.publish_button.setObjectName("primary"); self.publish_button.clicked.connect(self.publish); v.addWidget(self.publish_button); return w

    def _manage_tab(self):
        w=QWidget(); v=QVBoxLayout(w); title=QLabel("Yayınları yönet"); title.setStyleSheet("font-size:28px;font-weight:800"); v.addWidget(title)
        info=QLabel("Silme sırası: GitHub Release + tüm chunk assetleri → raw manifest → gerekiyorsa artwork → catalog.json. Katalog yalnızca uzak dosya temizliği tamamlandıktan sonra güncellenir. Yarıda kalan işlem tekrar güvenle çalıştırılabilir."); info.setWordWrap(True); info.setStyleSheet("color:#9aa7ba;background:#101622;border:1px solid #202c40;border-radius:12px;padding:13px"); v.addWidget(info)
        row=QHBoxLayout(); refresh=QPushButton("Raw katalogdan yenile"); refresh.clicked.connect(self.refresh_catalog); row.addWidget(refresh); row.addStretch(); v.addLayout(row)
        self.manage_tree=QTreeWidget(); self.manage_tree.setHeaderLabels(["Oyun","Platform","Kanal","Sürüm","Boyut / Tag"]); self.manage_tree.setAlternatingRowColors(True); v.addWidget(self.manage_tree,1)
        actions=QHBoxLayout(); self.delete_channel_button=QPushButton("Seçili sürümü / kanalı sil"); self.delete_channel_button.setObjectName("danger"); self.delete_game_button=QPushButton("Oyunu tamamen sil"); self.delete_game_button.setObjectName("danger"); self.delete_channel_button.clicked.connect(self.confirm_delete_channel); self.delete_game_button.clicked.connect(self.confirm_delete_game); actions.addWidget(self.delete_channel_button); actions.addWidget(self.delete_game_button); actions.addStretch(); v.addLayout(actions)
        self.delete_logs=QPlainTextEdit(); self.delete_logs.setReadOnly(True); self.delete_logs.setFixedHeight(135); v.addWidget(self.delete_logs); return w

    def pick_source(self):
        path=QFileDialog.getExistingDirectory(self,"Kaynak klasörü")
        if not path: return
        self.source.setText(path); builder=ChunkBuilder(Path(path)); status="Tek Release’e sığıyor" if builder.chunk_count<=MAX_DATA_ASSETS else "Tek Release’e sığmıyor"; self.plan.setText(f"<b>{status}</b><br>Kaynak: {format_bytes(builder.total_size)} • Chunk: {builder.chunk_count}/{MAX_DATA_ASSETS}<br>Tek Release veri tavanı: {format_bytes(MAX_RELEASE_DATA_BYTES)}")

    def save_settings(self):
        for key,widget in (("owner",self.owner),("repo",self.repo),("branch",self.branch)): self.settings.setValue(key,widget.text().strip())
        if self.token.text().strip(): keyring.set_password(SERVICE,ACCOUNT,self.token.text().strip())
        QMessageBox.information(self,"Kaydedildi","GitHub ayarları kaydedildi.")

    def test_connection(self):
        try:
            data=GitHubClient(self.token.text(),self.owner.text(),self.repo.text(),self.branch.text()).repo_info(); QMessageBox.information(self,"Bağlantı başarılı",data['full_name'])
        except Exception as exc: QMessageBox.critical(self,"GitHub hatası",str(exc))

    def publish(self):
        if not self.source.text() or not self.game_title.text().strip(): QMessageBox.warning(self,"Eksik","Proje adı ve kaynak klasörü gerekli."); return
        params={**self._params(),'source':self.source.text(),'title':self.game_title.text().strip(),'platform':self.platform.currentText(),'channel':self.channel.currentText(),'version':self.version.text().strip(),'description':self.description.toPlainText(),'artwork':{'hero':self.hero.path,'cover':self.cover.path,'logo':self.logo.path}}
        self.publish_button.setEnabled(False); self.logs.clear(); self.thread=QThread(); self.worker=PublishWorker(params); self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run); self.worker.log.connect(self.logs.appendPlainText); self.worker.progress.connect(self.progress.setValue); self.worker.done.connect(self.on_done); self.worker.error.connect(self.on_error); self.worker.done.connect(self.thread.quit); self.worker.error.connect(self.thread.quit); self.thread.start()

    def refresh_catalog(self):
        try:
            catalog=load_catalog(GitHubClient(self.token.text(),self.owner.text(),self.repo.text(),self.branch.text()))
            self.manage_tree.clear()
            for game in sorted(catalog.get('games',[]),key=lambda g:(g.get('platform',''),g.get('title','').lower())):
                channels=game.get('channels') or {}; total=sum(int(c.get('size',0)) for c in channels.values())
                parent=QTreeWidgetItem([game.get('title','?'),game.get('platform','').upper(),"Tümü",f"{len(channels)} yayın",format_bytes(total)])
                parent.setData(0,Qt.UserRole,{'kind':'game','game_id':game.get('id'),'platform':game.get('platform'),'title':game.get('title'),'channels':list(channels)})
                self.manage_tree.addTopLevelItem(parent)
                for channel,data in sorted(channels.items()):
                    child=QTreeWidgetItem(["",game.get('platform','').upper(),channel,data.get('version','?'),f"{format_bytes(int(data.get('size',0)))} • {data.get('tag','')}"])
                    child.setData(0,Qt.UserRole,{'kind':'channel','game_id':game.get('id'),'platform':game.get('platform'),'title':game.get('title'),'channel':channel,'version':data.get('version'),'tag':data.get('tag')})
                    parent.addChild(child)
                parent.setExpanded(True)
            self.delete_logs.appendPlainText(f"Raw katalog yenilendi: {len(catalog.get('games',[]))} oyun")
        except Exception as exc:
            QMessageBox.critical(self,"Katalog hatası",str(exc))

    def _selected_record(self):
        item=self.manage_tree.currentItem()
        return item.data(0,Qt.UserRole) if item else None

    def confirm_delete_channel(self):
        record=self._selected_record()
        if not record or record.get('kind')!='channel': QMessageBox.warning(self,"Seçim gerekli","Silmek istediğin kanal/sürüm satırını seç."); return
        prompt=f"{record['title']} • {record['platform'].upper()} • {record['channel']} • v{record.get('version')}\n\nRelease ve tüm chunk dosyaları, raw manifest ve katalog kaydı silinecek.\n\nDevam etmek için SİL yaz:"
        text,ok=QInputDialog.getText(self,"Sürümü kalıcı sil",prompt)
        if not ok or text.strip().upper()!="SİL": return
        self._start_delete("channel",record)

    def confirm_delete_game(self):
        record=self._selected_record()
        if not record: QMessageBox.warning(self,"Seçim gerekli","Silmek istediğin oyunu veya altındaki bir sürümü seç."); return
        prompt=f"{record['title']} ({record['platform'].upper()}) tamamen silinecek.\n\nTÜM kanalların Release/chunk dosyaları, manifestleri, artwork dosyaları ve katalog kaydı kaldırılacak.\n\nOnaylamak için oyun adını aynen yaz:\n{record['title']}"
        text,ok=QInputDialog.getText(self,"Oyunu tamamen sil",prompt)
        if not ok or text.strip()!=record['title']: QMessageBox.warning(self,"İptal","Oyun adı eşleşmedi; hiçbir şey silinmedi."); return
        self._start_delete("game",record)

    def _start_delete(self,mode,record):
        self.delete_channel_button.setEnabled(False); self.delete_game_button.setEnabled(False); self.delete_logs.clear()
        self.thread=QThread(); self.worker=DeleteWorker(self._params(),mode,record); self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run); self.worker.log.connect(self.delete_logs.appendPlainText); self.worker.done.connect(self.on_delete_done); self.worker.error.connect(self.on_delete_error); self.worker.done.connect(self.thread.quit); self.worker.error.connect(self.thread.quit); self.thread.start()

    def on_done(self,tag):
        self.publish_button.setEnabled(True); self.progress.setValue(100); QMessageBox.information(self,"Yayınlandı",tag)
        if hasattr(self,'manage_tree'): self.refresh_catalog()
    def on_error(self,message): self.publish_button.setEnabled(True); QMessageBox.critical(self,"Yayınlama hatası",message)
    def on_delete_done(self,message):
        self.delete_channel_button.setEnabled(True); self.delete_game_button.setEnabled(True); self.delete_logs.appendPlainText(message); self.refresh_catalog(); QMessageBox.information(self,"Silme tamamlandı",message)
    def on_delete_error(self,message):
        self.delete_channel_button.setEnabled(True); self.delete_game_button.setEnabled(True); self.delete_logs.appendPlainText("HATA: "+message); QMessageBox.critical(self,"Silme tamamlanamadı","Katalog güvenlik nedeniyle son adıma kadar değiştirilmez. İşlemi tekrar çalıştırabilirsin.\n\n"+message)

def main():
    app=QApplication(sys.argv); app.setStyleSheet(STYLE); win=Manager(); win.show(); sys.exit(app.exec())
if __name__ == "__main__": main()
