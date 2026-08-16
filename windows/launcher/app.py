from __future__ import annotations
import sys
from pathlib import Path
import requests
from PySide6.QtCore import QObject, QSettings, QThread, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import *
from drowned_shared.install import fetch_json, install_manifest
from drowned_shared.util import format_bytes

STYLE="""
QWidget{background:#070a10;color:#eef2f7;font-family:'Segoe UI';font-size:14px}
QLineEdit,QComboBox,QPlainTextEdit{background:#101622;border:1px solid #263247;border-radius:10px;padding:9px}
QPushButton{background:#182238;border:1px solid #2b3a55;border-radius:10px;padding:10px 15px;font-weight:600} QPushButton#primary{background:#5d6bff;border-color:#7580ff}
QFrame#card{background:#101622;border:1px solid #202c40;border-radius:16px}
QProgressBar{background:#101622;border:1px solid #263247;border-radius:8px;text-align:center;height:16px} QProgressBar::chunk{background:#5d6bff;border-radius:7px}
"""

class InstallWorker(QObject):
    progress=Signal(int,str); done=Signal(); error=Signal(str); log=Signal(str)
    def __init__(self,url,target): super().__init__(); self.url=url; self.target=Path(target); self.cancelled=False
    def run(self):
        try:
            manifest=fetch_json(self.url); install_manifest(manifest,self.target,lambda d,t:self.progress.emit(int(d*100/max(t,1)),f"{format_bytes(d)} / {format_bytes(t)}"),self.log.emit,lambda:self.cancelled); self.done.emit()
        except Exception as exc: self.error.emit(str(exc))

class GameCard(QFrame):
    install=Signal(dict,str)
    def __init__(self,game,channel):
        super().__init__(); self.setObjectName("card"); self.setMinimumWidth(245); layout=QVBoxLayout(self)
        hero=QLabel("DROWNED"); hero.setFixedHeight(115); hero.setAlignment(Qt.AlignCenter); hero.setStyleSheet("background:#05070c;border-radius:11px;color:#728099;font-weight:800")
        url=game.get('artwork',{}).get('hero')
        if url:
            try:
                response=requests.get(url,timeout=8); pix=QPixmap(); pix.loadFromData(response.content); hero.setPixmap(pix.scaled(320,115,Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation))
            except Exception: pass
        data=game['channels'][channel]; title=QLabel(game['title']); title.setStyleSheet("font-size:18px;font-weight:800"); meta=QLabel(f"{game['platform'].upper()} • {channel} • v{data['version']}\n{format_bytes(data['size'])}"); meta.setStyleSheet("color:#8d99aa"); button=QPushButton("İndir / Kur"); button.setObjectName("primary"); button.clicked.connect(lambda:self.install.emit(game,channel)); layout.addWidget(hero); layout.addWidget(title); layout.addWidget(meta); layout.addWidget(button)

class Launcher(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Drowned Launcher"); self.resize(1180,820); self.settings=QSettings("Drowned","Launcher"); self.catalog={'games':[]}; self.worker=None; self.thread=None
        root=QWidget(); self.setCentralWidget(root); layout=QVBoxLayout(root); top=QHBoxLayout(); logo=QLabel("DROWNED"); logo.setStyleSheet("font-size:27px;font-weight:900;letter-spacing:3px"); self.owner=QLineEdit(self.settings.value('owner','thedrowned925')); self.repo=QLineEdit(self.settings.value('repo','drowned1')); self.branch=QLineEdit(self.settings.value('branch','main')); refresh=QPushButton("Yenile"); refresh.clicked.connect(self.load_catalog); top.addWidget(logo); top.addStretch(); top.addWidget(self.owner); top.addWidget(self.repo); top.addWidget(self.branch); top.addWidget(refresh); layout.addLayout(top)
        filters=QHBoxLayout(); self.platform=QComboBox(); self.platform.addItem("Tümü"); self.channel=QComboBox(); self.channel.addItems(["stable","beta","dev","nightly","archive"]); self.platform.currentTextChanged.connect(self.render); self.channel.currentTextChanged.connect(self.render); filters.addWidget(QLabel("Platform")); filters.addWidget(self.platform); filters.addWidget(QLabel("Kanal")); filters.addWidget(self.channel); filters.addStretch(); layout.addLayout(filters)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); layout.addWidget(self.scroll,1); self.progress=QProgressBar(); self.status=QLabel("Hazır"); self.status.setStyleSheet("color:#8d99aa"); self.logs=QPlainTextEdit(); self.logs.setReadOnly(True); self.logs.setFixedHeight(90); layout.addWidget(self.progress); layout.addWidget(self.status); layout.addWidget(self.logs); self.load_catalog()
    def load_catalog(self):
        self.settings.setValue('owner',self.owner.text()); self.settings.setValue('repo',self.repo.text()); self.settings.setValue('branch',self.branch.text()); url=f"https://raw.githubusercontent.com/{self.owner.text()}/{self.repo.text()}/{self.branch.text() or 'main'}/catalog.json"
        try:
            response=requests.get(url,timeout=20); response.raise_for_status(); self.catalog=response.json(); platforms=sorted({g['platform'].upper() for g in self.catalog.get('games',[])}); self.platform.blockSignals(True); self.platform.clear(); self.platform.addItem("Tümü"); self.platform.addItems(platforms); self.platform.blockSignals(False); self.render(); self.status.setText("Katalog güncel")
        except Exception as exc: self.status.setText("Katalog yüklenemedi: "+str(exc)); self.render()
    def render(self):
        host=QWidget(); grid=QGridLayout(host); p=self.platform.currentText(); ch=self.channel.currentText(); games=[g for g in self.catalog.get('games',[]) if (p=="Tümü" or g['platform'].upper()==p) and ch in g.get('channels',{})]
        if not games: grid.addWidget(QLabel("Bu filtrede yayın yok."),0,0)
        for i,game in enumerate(games):
            card=GameCard(game,ch); card.install.connect(self.install_game); grid.addWidget(card,i//3,i%3)
        self.scroll.setWidget(host)
    def install_game(self,game,channel):
        folder=QFileDialog.getExistingDirectory(self,"Kurulum klasörü")
        if not folder: return
        data=game['channels'][channel]; target=Path(folder)/game['title']; self.thread=QThread(); self.worker=InstallWorker(data['manifest_url'],target); self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run); self.worker.progress.connect(lambda p,t:(self.progress.setValue(p),self.status.setText(t))); self.worker.log.connect(self.logs.appendPlainText); self.worker.done.connect(lambda:QMessageBox.information(self,"Tamamlandı","Kurulum ve doğrulama tamamlandı.")); self.worker.error.connect(lambda e:QMessageBox.critical(self,"İndirme hatası",e)); self.worker.done.connect(self.thread.quit); self.worker.error.connect(self.thread.quit); self.thread.start()

def main():
    app=QApplication(sys.argv); app.setStyleSheet(STYLE); win=Launcher(); win.show(); sys.exit(app.exec())
if __name__ == "__main__": main()
