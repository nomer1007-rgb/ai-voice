import json, os, shutil, sys, urllib.request, urllib.parse
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QLineEdit,
    QProgressBar, QFrame)

APP_NAME = "Real Voice AI"
SUPPORTED = {".pth", ".onnx"}


def data_dir():
    p = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "RealVoiceAI"
    (p / "models").mkdir(parents=True, exist_ok=True)
    return p


class DownloadWorker(QThread):
    progress = Signal(int)
    done = Signal(bool, str)
    def __init__(self, url, target):
        super().__init__(); self.url=url; self.target=target
    def run(self):
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent":"RealVoiceAI/4.0"})
            with urllib.request.urlopen(req, timeout=40) as r, open(self.target, "wb") as f:
                total = int(r.headers.get("Content-Length", "0") or 0); got=0
                while True:
                    b=r.read(1024*1024)
                    if not b: break
                    f.write(b); got += len(b)
                    if total: self.progress.emit(min(100, int(got*100/total)))
            if self.target.stat().st_size < 1024:
                self.target.unlink(missing_ok=True); raise RuntimeError("Скачанный файл слишком маленький или пустой.")
            self.done.emit(True, "Модель скачана. Проверьте её совместимость перед использованием.")
        except Exception as e:
            self.target.unlink(missing_ok=True); self.done.emit(False, str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Real Voice AI — V4"); self.resize(900, 650)
        self.root=data_dir(); self.models=self.root/"models"; self.worker=None
        w=QWidget(); self.setCentralWidget(w); lay=QVBoxLayout(w); lay.setContentsMargins(26,22,26,22); lay.setSpacing(14)
        head=QHBoxLayout(); title=QLabel("REAL VOICE AI"); title.setObjectName("title"); head.addWidget(title); head.addStretch(); badge=QLabel("V4 • NVIDIA RTX"); badge.setObjectName("muted"); head.addWidget(badge); lay.addLayout(head)
        intro=QLabel("Твои голосовые модели в одном месте"); intro.setObjectName("subtitle"); lay.addWidget(intro)
        self.status=QLabel("Менеджер моделей готов. Движок преобразования пока не подключён."); self.status.setObjectName("status"); self.status.setWordWrap(True); lay.addWidget(self.status)
        row=QHBoxLayout(); self.list=QListWidget(); self.list.setMinimumWidth(430); row.addWidget(self.list,2)
        right=QVBoxLayout(); right.addWidget(QLabel("Добавить голос"))
        self.add_file=QPushButton("＋  Импортировать файл модели"); self.add_file.clicked.connect(self.import_file); right.addWidget(self.add_file)
        self.url=QLineEdit(); self.url.setPlaceholderText("https://.../voice.pth или voice.onnx"); right.addWidget(self.url)
        self.add_url=QPushButton("Скачать модель по ссылке"); self.add_url.clicked.connect(self.download_model); right.addWidget(self.add_url)
        self.progress=QProgressBar(); self.progress.setValue(0); right.addWidget(self.progress)
        right.addSpacing(14); right.addWidget(QLabel("Форматы")); fmt=QLabel("Основная модель: .pth или .onnx\nДополнительный индекс: .index\nИндекс не заменяет основную модель."); fmt.setObjectName("muted"); right.addWidget(fmt)
        right.addStretch(); self.remove=QPushButton("Удалить выбранную модель"); self.remove.clicked.connect(self.remove_model); right.addWidget(self.remove)
        row.addLayout(right,3); lay.addLayout(row)
        bottom=QHBoxLayout(); self.refresh=QPushButton("Обновить список"); self.refresh.clicked.connect(self.refresh_models); bottom.addWidget(self.refresh); bottom.addStretch(); self.start=QPushButton("Преобразование голоса — пока недоступно"); self.start.setEnabled(False); bottom.addWidget(self.start); lay.addLayout(bottom)
        note=QLabel("Важно: V4 сейчас содержит новый интерфейс и менеджер моделей. Реальное преобразование в микрофон ещё не реализовано; эта сборка не выдаёт простой Pitch за смену голоса."); note.setObjectName("warning"); note.setWordWrap(True); lay.addWidget(note)
        self.setStyleSheet('''QMainWindow{background:#11151d;color:#eef2f7} QWidget{color:#eef2f7;font-size:14px} QLabel#title{font-size:27px;font-weight:800;letter-spacing:2px} QLabel#subtitle{font-size:18px;color:#c6d2e1} QLabel#muted{color:#91a0b4} QLabel#status{background:#1b2635;border:1px solid #30445c;border-radius:10px;padding:12px} QLabel#warning{background:#342b1c;color:#f4d69b;border-radius:9px;padding:12px} QListWidget{background:#171e29;border:1px solid #2c394a;border-radius:12px;padding:8px} QPushButton{background:#273448;border:1px solid #3b4d65;border-radius:9px;padding:12px} QPushButton:hover{background:#344963} QPushButton:disabled{color:#778394;background:#1a202a} QLineEdit{background:#171e29;border:1px solid #3b4d65;border-radius:8px;padding:11px} QProgressBar{background:#202a38;border:0;border-radius:5px;height:9px} QProgressBar::chunk{background:#49b98c;border-radius:5px}''')
        self.refresh_models()

    def refresh_models(self):
        self.list.clear()
        for p in sorted(self.models.iterdir()):
            if p.is_file() and p.suffix.lower() in SUPPORTED:
                idx = p.with_suffix('.index')
                label=f"{p.name}   •   {p.stat().st_size/1024/1024:.1f} MB" + ("   •   INDEX" if idx.exists() else "")
                self.list.addItem(QListWidgetItem(label))
        if self.list.count()==0: self.list.addItem("Пока нет моделей — добавь .pth или .onnx")

    def import_file(self):
        files,_=QFileDialog.getOpenFileNames(self,"Выбери модель RVC",str(Path.home()),"Модели (*.pth *.onnx *.index)")
        if not files: return
        for name in files:
            src=Path(name)
            if src.suffix.lower() not in SUPPORTED and src.suffix.lower() != '.index': continue
            dest=self.models/src.name
            if src.resolve()!=dest.resolve(): shutil.copy2(src,dest)
        self.refresh_models(); self.status.setText("Файлы добавлены. Совместимость архитектуры модели ещё нужно проверить движком.")

    def download_model(self):
        url=self.url.text().strip()
        if not url.startswith(('https://','http://')):
            QMessageBox.warning(self,"Ссылка","Вставь прямую HTTP(S)-ссылку на файл модели."); return
        name=Path(urllib.parse.urlparse(url).path).name
        if not name or Path(name).suffix.lower() not in SUPPORTED | {'.index'}:
            QMessageBox.warning(self,"Формат","Ссылка должна вести напрямую на файл .pth, .onnx или .index."); return
        target=self.models/name
        self.add_url.setEnabled(False); self.progress.setValue(0); self.status.setText("Скачивание модели…")
        self.worker=DownloadWorker(url,target); self.worker.progress.connect(self.progress.setValue); self.worker.done.connect(self.download_done); self.worker.start()
    def download_done(self,ok,msg):
        self.add_url.setEnabled(True); self.status.setText(msg); self.refresh_models()
        if not ok: QMessageBox.warning(self,"Ошибка загрузки",msg)
    def remove_model(self):
        item=self.list.currentItem()
        if not item: return
        name=item.text().split('   •')[0]
        p=self.models/name
        if p.exists() and p.is_file():
            p.unlink(); self.refresh_models(); self.status.setText("Файл модели удалён.")

if __name__=='__main__':
    app=QApplication(sys.argv); win=MainWindow(); win.show(); sys.exit(app.exec())
