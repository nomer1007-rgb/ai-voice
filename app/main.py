import os, sys, json, shutil, subprocess
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QProgressBar,
    QGroupBox)

APP_NAME = "Real Voice AI"
def data_root():
    p = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "RealVoiceAI"
    (p/"models").mkdir(parents=True, exist_ok=True)
    return p

def resource(name):
    # Support both PyInstaller's bundled data directory and the explicit
    # {app}\scripts copy installed by Inno Setup.
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / name)
    exe_dir = Path(sys.executable).resolve().parent
    candidates.append(exe_dir / name)
    candidates.append(exe_dir / "_internal" / name)
    candidates.append(exe_dir / "scripts" / Path(name).name)
    candidates.append(exe_dir.parent / "scripts" / Path(name).name)
    candidates.append(Path(__file__).resolve().parent / name)
    candidates.append(Path(__file__).resolve().parent / "scripts" / Path(name).name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # Return the primary expected path so the error dialog remains informative.
    return candidates[0] if candidates else Path(name)

class EngineWorker(QThread):
    output = Signal(str)
    done = Signal(bool, str)
    def __init__(self, script):
        super().__init__()
        self.script = script
    def run(self):
        try:
            proc = subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.script)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            for line in proc.stdout:
                self.output.emit(line.rstrip())
            code = proc.wait()
            self.done.emit(code == 0, "Движок установлен." if code == 0 else f"Установка завершилась с кодом {code}.")
        except Exception as e:
            self.done.emit(False, str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Real Voice AI — V5.4")
        self.resize(940, 690)
        self.root = data_root()
        self.models = self.root/"models"
        self.engine = self.root/"engine"
        self.worker = None
        self.engine_process = None
        self.settings_file = self.root/"settings.json"
        try: self.settings = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except: self.settings = {}
        self.active = self.settings.get("active_model", "")
        w = QWidget(); self.setCentralWidget(w)
        layout = QVBoxLayout(w); layout.setContentsMargins(24,20,24,20); layout.setSpacing(12)
        top = QHBoxLayout()
        title = QLabel("REAL VOICE AI"); title.setObjectName("title")
        top.addWidget(title); top.addStretch()
        v = QLabel("V5.4 • RVC REALTIME"); v.setObjectName("muted"); top.addWidget(v)
        layout.addLayout(top)
        sub = QLabel("Нейросетевое преобразование голоса в реальном времени")
        sub.setObjectName("subtitle"); layout.addWidget(sub)
        self.status = QLabel("Сначала установи RVC-движок. Для установки нужны интернет и несколько гигабайт свободного места.")
        self.status.setObjectName("status"); self.status.setWordWrap(True); layout.addWidget(self.status)
        body = QHBoxLayout()
        left = QGroupBox("Твои голосовые модели"); ll = QVBoxLayout(left)
        self.list = QListWidget(); ll.addWidget(self.list)
        row = QHBoxLayout()
        b = QPushButton("Импортировать .pth / .index"); b.clicked.connect(self.import_model); row.addWidget(b)
        b = QPushButton("Удалить"); b.clicked.connect(self.delete_model); row.addWidget(b)
        ll.addLayout(row)
        self.active_label = QLabel(); self.active_label.setObjectName("muted"); ll.addWidget(self.active_label)
        b = QPushButton("Сделать выбранную активной"); b.clicked.connect(self.choose_model); ll.addWidget(b)
        body.addWidget(left, 3)
        right = QGroupBox("RVC движок"); rl = QVBoxLayout(right)
        self.install_btn = QPushButton("1. Установить / обновить движок")
        self.install_btn.clicked.connect(self.install_engine); rl.addWidget(self.install_btn)
        self.progress = QProgressBar(); self.progress.setRange(0,0); self.progress.hide(); rl.addWidget(self.progress)
        self.log = QLabel("Загрузка RVC + Python 3.12 + PyTorch CUDA 12.8. Установка может занять продолжительное время. Журнал: %LOCALAPPDATA%\\RealVoiceAI\\engine-install.log")
        self.log.setWordWrap(True); self.log.setObjectName("muted"); rl.addWidget(self.log)
        self.launch_btn = QPushButton("2. Запустить RVC Real-Time")
        self.launch_btn.clicked.connect(self.launch_engine); rl.addWidget(self.launch_btn)
        self.stop_btn = QPushButton("Остановить движок"); self.stop_btn.clicked.connect(self.stop_engine); rl.addWidget(self.stop_btn)
        rl.addStretch(); body.addWidget(right,2); layout.addLayout(body,1)
        self.warning = QLabel("Важно: V5 подключает настоящий RVC Real-Time, но его панель настроек открывается отдельным окном. В этом окне выбери свою модель, микрофон, выход и параметры F0. Формат .onnx в этой версии не поддерживается — используются RVC .pth и соответствующие .index.")
        self.warning.setObjectName("warning"); self.warning.setWordWrap(True); layout.addWidget(self.warning)
        foot = QHBoxLayout()
        b = QPushButton("Обновить список"); b.clicked.connect(self.refresh); foot.addWidget(b)
        foot.addStretch()
        layout.addLayout(foot)
        self.setStyleSheet("""
        QMainWindow{background:#11151d;color:#eef2f7} QWidget{color:#eef2f7;font-size:14px}
        QLabel#title{font-size:27px;font-weight:800;letter-spacing:2px}
        QLabel#subtitle{font-size:18px;color:#c6d2e1} QLabel#muted{color:#91a0b4}
        QLabel#status{background:#1b2635;border:1px solid #30445c;border-radius:9px;padding:12px}
        QLabel#warning{background:#342b1c;color:#f4d69b;border-radius:9px;padding:12px}
        QGroupBox{border:1px solid #2c394a;border-radius:10px;margin-top:10px;padding:12px;font-weight:600}
        QListWidget{background:#171e29;border:1px solid #2c394a;border-radius:9px;padding:8px}
        QPushButton{background:#273448;border:1px solid #3b4d65;border-radius:9px;padding:11px}
        QPushButton:hover{background:#344963} QPushButton:disabled{color:#778394;background:#1a202a}
        """)
        self.refresh()
        self.update_engine_state()
    def update_engine_state(self):
        bat = self.engine/"go-realtime_gui.bat"
        py = self.engine/"runtime"/"python.exe"
        hubert = self.engine/"assets"/"hubert_base"/"config.json"
        rmvpe = self.engine/"assets"/"rmvpe"/"rmvpe.pt"
        if bat.exists() and py.exists() and hubert.exists() and rmvpe.exists():
            self.log.setText("RVC-движок и Python runtime найдены. Нажми «Запустить RVC Real-Time».")
            self.launch_btn.setEnabled(True)
        else:
            self.log.setText("RVC ещё не установлен. Нажми «Установить / обновить движок». Нужны интернет и несколько гигабайт свободного места.")
            self.launch_btn.setEnabled(False)
    def save(self):
        self.settings["active_model"] = self.active
        self.settings_file.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
    def refresh(self):
        self.list.clear()
        files = sorted(self.models.glob("*.pth"))
        for p in files:
            item = QListWidgetItem(("✓ " if p.name == self.active else "") + p.name)
            item.setData(256, p.name); self.list.addItem(item)
        self.active_label.setText("Активная модель: " + (self.active or "не выбрана"))
    def import_model(self):
        fs,_ = QFileDialog.getOpenFileNames(self, "Импорт моделей", str(Path.home()), "RVC модели (*.pth *.index)")
        for f in fs:
            src=Path(f); dst=self.models/src.name
            if src.resolve()!=dst.resolve(): shutil.copy2(src,dst)
        self.refresh()
        self.status.setText(f"Импортировано файлов: {len(fs)}. .index хранится отдельно и должен соответствовать модели.")
    def selected(self):
        it=self.list.currentItem()
        return self.models/it.data(256) if it and it.data(256) else None
    def choose_model(self):
        p=self.selected()
        if not p or not p.exists(): return
        self.active=p.name; self.save(); self.refresh()
        self.status.setText(f"Активная модель: {p.name}. При запуске RVC выбери её в списке моделей.")
    def delete_model(self):
        p=self.selected()
        if not p or not p.exists(): return
        if QMessageBox.question(self,"Удалить",f"Удалить {p.name}?") != QMessageBox.StandardButton.Yes: return
        p.unlink()
        if self.active==p.name: self.active=""; self.save()
        self.refresh()
    def install_engine(self):
        script=resource("scripts/install_rvc.ps1")
        if not script.exists():
            QMessageBox.critical(self,"Нет установщика движка",f"Не найден файл: {script}"); return
        self.install_btn.setEnabled(False); self.progress.show()
        self.worker=EngineWorker(script); self.worker.output.connect(self.on_log); self.worker.done.connect(self.install_done); self.worker.start()
    def on_log(self,s):
        self.log.setText(s[-450:])
    def install_done(self,ok,msg):
        self.progress.hide(); self.install_btn.setEnabled(True); self.status.setText(msg)
        if not ok: QMessageBox.warning(self,"Установка RVC",msg+" Проверь журнал установки и интернет.")
        else:
            self.sync_models()
            self.update_engine_state()
    def sync_models(self):
        weights=self.engine/"assets"/"weights"; indices=self.engine/"assets"/"indices"
        weights.mkdir(parents=True,exist_ok=True); indices.mkdir(parents=True,exist_ok=True)
        for p in self.models.glob("*.pth"):
            shutil.copy2(p,weights/p.name)
        for p in self.models.glob("*.index"):
            shutil.copy2(p,indices/p.name)
    def launch_engine(self):
        bat=self.engine/"go-realtime_gui.bat"
        if not bat.exists():
            QMessageBox.information(self,"RVC не установлен","Сначала нажми «Установить / обновить движок»."); return
        self.sync_models()
        try:
            # The upstream batch file starts Python with -I (isolated mode).
            # On current Python this prevents imports from the RVC project root,
            # causing "No module named tools". Remove only that flag, preserving
            # the upstream console setup, PATH and pause behavior.
            launcher_text = bat.read_text(encoding="utf-8-sig")
            fixed_text = launcher_text.replace(
                "runtime\\python.exe -I realtime_gui.py",
                "runtime\\python.exe realtime_gui.py",
            )
            if fixed_text != launcher_text:
                bat.write_text(fixed_text, encoding="utf-8")
            python = self.engine / "runtime" / "python.exe"
            if not python.is_file():
                raise FileNotFoundError(f"Не найден Python движка: {python}")
            env = os.environ.copy()
            env["PATH"] = str(self.engine / "runtime") + os.pathsep + env.get("PATH", "")
            self.engine_process=subprocess.Popen(["cmd.exe","/c",str(bat)],cwd=str(self.engine),env=env)
            self.status.setText("RVC Real-Time запускается. В отдельном окне выбери модель, микрофон и выход. Для Discord укажи виртуальный аудиокабель как микрофон.")
        except Exception as e: QMessageBox.critical(self,"Ошибка запуска",str(e))
    def stop_engine(self):
        # The official RVC GUI may spawn child processes; close its window normally.
        if self.engine_process and self.engine_process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(self.engine_process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.status.setText("Запрос на остановку отправлен. Если окно RVC осталось, закрой его отдельно.")

if __name__=="__main__":
    app=QApplication(sys.argv); win=MainWindow(); win.show(); sys.exit(app.exec())
