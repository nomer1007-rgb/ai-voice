import os, sys, json, shutil, zipfile, subprocess, threading, urllib.request, urllib.error
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QTextEdit, QMessageBox, QFrame)
from PySide6.QtWebEngineWidgets import QWebEngineView

APP_NAME = "AI Voice Changer RTX"
HF_API = "https://huggingface.co/api/models/wok000/vcclient000/tree/main?recursive=true&expand=false"
HF_BASE = "https://huggingface.co/wok000/vcclient000/resolve/main/"
LOCAL_URL = "http://127.0.0.1:18888/"

def app_dir():
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    p = Path(base) / "AIVoiceChangerRTX"
    p.mkdir(parents=True, exist_ok=True)
    return p

def bundled_path(*parts):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)

class SetupWorker(QThread):
    progress = Signal(int)
    message = Signal(str)
    done = Signal(bool, str)

    def run(self):
        target = app_dir() / "engine"
        target.mkdir(parents=True, exist_ok=True)
        marker = target / ".installed"
        if marker.exists():
            self.done.emit(True, "Движок уже установлен.")
            return
        try:
            self.message.emit("Проверяю доступную CUDA-сборку движка…")
            req = urllib.request.Request(HF_API, headers={"User-Agent": "AI-Voice-Changer-RTX/3.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                listing = json.loads(r.read().decode("utf-8"))
            names = [x.get("path", "") for x in listing if x.get("type") == "file"]
            candidates = [n for n in names if n.lower().endswith(".zip") and "vcclient_win_cuda_" in n.lower()]
            if not candidates:
                candidates = [n for n in names if n.lower().endswith(".zip") and "vcclient_win_" in n.lower() and "cuda" in n.lower()]
            if not candidates:
                raise RuntimeError("Не нашёл Windows CUDA-архив в официальном каталоге VCClient.")
            # Version names are sortable in the upstream repository's naming convention.
            archive_name = sorted(candidates)[-1]
            url = HF_BASE + urllib.parse.quote(archive_name)
            archive = target / "engine.zip"
            self.message.emit("Скачиваю CUDA-движок: " + archive_name)
            req = urllib.request.Request(url, headers={"User-Agent": "AI-Voice-Changer-RTX/3.0"})
            with urllib.request.urlopen(req, timeout=90) as response, open(archive, "wb") as out:
                total = int(response.headers.get("Content-Length", "0") or 0)
                got = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk: break
                    out.write(chunk); got += len(chunk)
                    if total: self.progress.emit(min(95, int(got * 95 / total)))
            self.message.emit("Распаковываю движок…")
            with zipfile.ZipFile(archive) as z:
                z.extractall(target)
            archive.unlink(missing_ok=True)
            marker.write_text(archive_name, encoding="utf-8")
            self.progress.emit(100)
            self.done.emit(True, "Движок установлен.")
        except Exception as e:
            self.done.emit(False, str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME + " — V3")
        self.resize(1180, 760)
        self.engine_proc = None
        self.worker = None
        self.root = QWidget(); self.setCentralWidget(self.root)
        layout = QVBoxLayout(self.root); layout.setContentsMargins(20,18,20,18); layout.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("AI VOICE CHANGER"); title.setObjectName("title")
        ver = QLabel("V3  •  NVIDIA CUDA"); ver.setObjectName("muted")
        top.addWidget(title); top.addStretch(); top.addWidget(ver)
        layout.addLayout(top)

        self.status = QLabel("Проверка компонентов…"); self.status.setObjectName("status")
        layout.addWidget(self.status)
        self.progress = QProgressBar(); self.progress.setRange(0,100); self.progress.setValue(0)
        self.progress.setTextVisible(False); layout.addWidget(self.progress)

        row = QHBoxLayout()
        self.install_btn = QPushButton("Установить / проверить движок")
        self.install_btn.clicked.connect(self.install_engine)
        self.start_btn = QPushButton("Запустить преобразование")
        self.start_btn.setObjectName("primary"); self.start_btn.clicked.connect(self.start_engine)
        self.stop_btn = QPushButton("Остановить")
        self.stop_btn.clicked.connect(self.stop_engine)
        row.addWidget(self.install_btn); row.addWidget(self.start_btn); row.addWidget(self.stop_btn)
        layout.addLayout(row)

        self.web = QWebEngineView()
        self.web.setUrl(QUrl("about:blank"))
        self.web.setMinimumHeight(470)
        layout.addWidget(self.web, 1)

        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(90)
        self.log.setPlaceholderText("Сообщения программы…")
        layout.addWidget(self.log)

        self.setStyleSheet("""
            QWidget { background:#111318; color:#e9edf5; font-family:'Segoe UI'; font-size:14px; }
            QLabel#title { font-size:23px; font-weight:700; letter-spacing:1px; }
            QLabel#muted { color:#929baa; }
            QLabel#status { color:#b9c6d8; padding:8px 0; }
            QPushButton { background:#242a35; border:1px solid #343c4b; border-radius:9px; padding:12px 16px; }
            QPushButton:hover { background:#30394a; }
            QPushButton#primary { background:#5268e8; border:0; font-weight:700; }
            QPushButton#primary:hover { background:#6478f1; }
            QProgressBar { background:#252a34; border:0; border-radius:5px; height:8px; }
            QProgressBar::chunk { background:#6478f1; border-radius:5px; }
            QTextEdit { background:#171b22; border:1px solid #2b313d; border-radius:8px; padding:8px; color:#aeb8c8; }
        """)
        self.log_line("Готово к первому запуску. Для работы требуется интернет при загрузке движка.")
        self.install_engine()

    def log_line(self, text):
        self.log.append(text)

    def install_engine(self):
        if self.worker and self.worker.isRunning(): return
        self.install_btn.setEnabled(False)
        self.status.setText("Подготовка движка преобразования голоса…")
        self.progress.setValue(0)
        self.worker = SetupWorker()
        self.worker.message.connect(self.log_line)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.done.connect(self.install_finished)
        self.worker.start()

    def install_finished(self, ok, msg):
        self.install_btn.setEnabled(True)
        self.log_line(msg)
        if ok:
            self.status.setText("Движок готов. Нажми «Запустить преобразование».")
            self.progress.setValue(100)
        else:
            self.status.setText("Не удалось подготовить движок.")
            QMessageBox.warning(self, "Ошибка установки", msg + "\nПроверь интернет и повтори попытку.")

    def find_start_script(self):
        engine = app_dir() / "engine"
        scripts = list(engine.rglob("start_http.bat")) + list(engine.rglob("start.bat"))
        return scripts[0] if scripts else None

    def start_engine(self):
        script = self.find_start_script()
        if not script:
            QMessageBox.information(self, "Нужен движок", "Сначала установи или проверь движок.")
            return
        if self.engine_proc and self.engine_proc.poll() is None:
            self.web.setUrl(QUrl(LOCAL_URL)); return
        try:
            self.log_line("Запускаю движок преобразования…")
            self.engine_proc = subprocess.Popen(["cmd.exe", "/c", str(script)],
                cwd=str(script.parent), creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            self.status.setText("Движок запускается. Интерфейс откроется здесь через несколько секунд.")
            self.web.setUrl(QUrl(LOCAL_URL))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка запуска", str(e))

    def stop_engine(self):
        if self.engine_proc and self.engine_proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(self.engine_proc.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.log_line("Процесс движка остановлен.")
        self.status.setText("Движок остановлен.")

    def closeEvent(self, event):
        # Keep engine alive only if user explicitly chooses; default closes it with the app.
        self.stop_engine()
        event.accept()

if __name__ == "__main__":
    import urllib.parse
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    w = MainWindow(); w.show()
    sys.exit(app.exec())
