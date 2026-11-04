import os, sys, json, shutil, subprocess, ctypes
from pathlib import Path
from PySide6.QtCore import QThread, Signal, QTimer, Qt
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QProgressBar,
    QGroupBox, QFrame)

APP_NAME = "Real Voice AI"

def data_root():
    p = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "RealVoiceAI"
    (p / "models").mkdir(parents=True, exist_ok=True)
    return p

def resource(name):
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass: candidates.append(Path(meipass) / name)
    exe = Path(sys.executable).resolve().parent
    candidates += [exe / name, exe / "_internal" / name, exe / "scripts" / Path(name).name,
                   exe.parent / "scripts" / Path(name).name,
                   Path(__file__).resolve().parent / name,
                   Path(__file__).resolve().parent / "scripts" / Path(name).name]
    return next((p for p in candidates if p.is_file()), candidates[0])

class EngineWorker(QThread):
    output = Signal(str)
    done = Signal(bool, str)
    def __init__(self, script):
        super().__init__(); self.script = script
    def run(self):
        try:
            proc = subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.script)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for line in proc.stdout: self.output.emit(line.rstrip())
            code = proc.wait()
            self.done.emit(code == 0, "Движок установлен." if code == 0 else f"Ошибка установки (код {code}).")
        except Exception as e: self.done.emit(False, str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Real Voice AI")
        self.resize(1120, 860)
        self.setMinimumSize(900, 700)
        self.root = data_root(); self.models = self.root / "models"; self.engine = self.root / "engine"
        self.worker = None; self.engine_process = None; self.embedded_hwnd = None
        self.settings_file = self.root / "settings.json"
        try: self.settings = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except Exception: self.settings = {}
        self.active = self.settings.get("active_model", "")
        self.embed_timer = QTimer(self); self.embed_timer.setInterval(400); self.embed_timer.timeout.connect(self.try_embed)
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(22,18,22,18); root.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("REAL VOICE AI"); title.setObjectName("title"); header.addWidget(title)
        header.addStretch()
        self.state_badge = QLabel("ГОТОВО К НАСТРОЙКЕ"); self.state_badge.setObjectName("pill"); header.addWidget(self.state_badge)
        root.addLayout(header)
        subtitle = QLabel("Преобразование голоса в реальном времени • NVIDIA CUDA"); subtitle.setObjectName("subtitle"); root.addWidget(subtitle)
        top = QHBoxLayout()
        models_box = QGroupBox("1. МОДЕЛЬ ГОЛОСА"); ml = QVBoxLayout(models_box)
        self.list = QListWidget(); self.list.setMinimumHeight(105); ml.addWidget(self.list)
        actions = QHBoxLayout()
        b = QPushButton("＋ Импортировать модель"); b.clicked.connect(self.import_model); actions.addWidget(b)
        b = QPushButton("Удалить"); b.clicked.connect(self.delete_model); actions.addWidget(b)
        b = QPushButton("Выбрать активную"); b.setObjectName("primary"); b.clicked.connect(self.choose_model); actions.addWidget(b)
        ml.addLayout(actions)
        self.active_label = QLabel("Активная модель: не выбрана"); self.active_label.setObjectName("muted"); ml.addWidget(self.active_label)
        root.addWidget(models_box)
        engine_box = QGroupBox("2. ДВИЖОК И ПРЕОБРАЗОВАНИЕ"); el = QVBoxLayout(engine_box)
        toolbar = QHBoxLayout()
        self.install_btn = QPushButton("Установить движок"); self.install_btn.clicked.connect(self.install_engine); toolbar.addWidget(self.install_btn)
        self.launch_btn = QPushButton("Запустить панель"); self.launch_btn.setObjectName("primary"); self.launch_btn.clicked.connect(self.launch_engine); toolbar.addWidget(self.launch_btn)
        self.stop_btn = QPushButton("Остановить"); self.stop_btn.clicked.connect(self.stop_engine); toolbar.addWidget(self.stop_btn)
        toolbar.addStretch(); el.addLayout(toolbar)
        self.progress = QProgressBar(); self.progress.setRange(0,0); self.progress.hide(); el.addWidget(self.progress)
        self.log = QLabel("Проверка компонентов…"); self.log.setObjectName("muted"); self.log.setWordWrap(True); el.addWidget(self.log)
        self.engine_panel = QFrame(); self.engine_panel.setObjectName("enginePanel"); self.engine_panel.setMinimumHeight(440)
        self.engine_panel.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        pl = QVBoxLayout(self.engine_panel); pl.setContentsMargins(8,8,8,8)
        self.panel_hint = QLabel("Панель RVC появится здесь после запуска.\nВыбери модель, микрофон и устройство вывода, затем нажми «Начать аудио преобразование».")
        self.panel_hint.setObjectName("hint"); self.panel_hint.setAlignment(Qt.AlignmentFlag.AlignCenter); pl.addWidget(self.panel_hint)
        el.addWidget(self.engine_panel, 1)
        root.addWidget(engine_box, 1)
        self.status = QLabel("Подсказка: для Discord выбери виртуальный аудиокабель как устройство вывода RVC, а его виртуальный микрофон — в Discord.")
        self.status.setObjectName("status"); self.status.setWordWrap(True); root.addWidget(self.status)
        self.setStyleSheet("""
        QMainWindow,QWidget{background:#10151e;color:#edf2f8;font-size:13px}
        QLabel#title{font-size:26px;font-weight:800;letter-spacing:2px}
        QLabel#subtitle{font-size:15px;color:#aebdd0}
        QLabel#muted{color:#9aa9bb} QLabel#pill{background:#1d3440;color:#80d8c3;border-radius:12px;padding:7px 12px;font-weight:700}
        QLabel#status{background:#1b2938;border:1px solid #31465e;border-radius:8px;padding:10px;color:#c4d2e1}
        QLabel#hint{color:#9aabc0;font-size:14px}
        QGroupBox{border:1px solid #2c3b4e;border-radius:10px;margin-top:8px;padding:10px;font-weight:700}
        QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 5px;color:#9fc5f5}
        QListWidget,QFrame#enginePanel{background:#151e2a;border:1px solid #2d3c50;border-radius:8px}
        QPushButton{background:#26364a;border:1px solid #3a506b;border-radius:8px;padding:9px 13px}
        QPushButton:hover{background:#344b65} QPushButton#primary{background:#2463a6;border-color:#367fc8;font-weight:700}
        QPushButton#primary:hover{background:#2e78c5} QPushButton:disabled{color:#718096;background:#1a222d}
        QProgressBar{border:0;background:#202b3a;border-radius:4px;height:7px} QProgressBar::chunk{background:#3986d7;border-radius:4px}
        """)
        self.refresh(); self.update_engine_state()

    def save(self):
        self.settings["active_model"] = self.active
        self.settings_file.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")

    def refresh(self):
        self.list.clear()
        for p in sorted(self.models.glob("*.pth")):
            item = QListWidgetItem(("✓  " if p.name == self.active else "") + p.name)
            item.setData(Qt.ItemDataRole.UserRole, p.name); self.list.addItem(item)
        self.active_label.setText("Активная модель: " + (self.active or "не выбрана"))

    def selected(self):
        item = self.list.currentItem()
        return self.models / item.data(Qt.ItemDataRole.UserRole) if item else None

    def import_model(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Импортировать файлы модели", str(Path.home()), "Файлы RVC (*.pth *.index)")
        if not files: return
        for file in files:
            src = Path(file); dst = self.models / src.name
            if src.resolve() != dst.resolve(): shutil.copy2(src, dst)
        self.refresh(); self.status.setText(f"Импортировано файлов: {len(files)}. Файл .index должен соответствовать выбранному .pth.")

    def choose_model(self):
        p = self.selected()
        if not p or not p.exists(): return
        self.active = p.name; self.save(); self.refresh()
        self.sync_models()
        self.status.setText(f"Активная модель: {p.name}. Она скопирована в папку весов движка.")

    def delete_model(self):
        p = self.selected()
        if not p or not p.exists(): return
        if QMessageBox.question(self, "Удалить модель", f"Удалить {p.name}?") != QMessageBox.StandardButton.Yes: return
        p.unlink()
        if self.active == p.name: self.active = ""; self.save()
        self.refresh()

    def sync_models(self):
        weights = self.engine / "assets" / "weights"; indices = self.engine / "assets" / "indices"
        weights.mkdir(parents=True, exist_ok=True); indices.mkdir(parents=True, exist_ok=True)
        for p in self.models.glob("*.pth"): shutil.copy2(p, weights / p.name)
        for p in self.models.glob("*.index"): shutil.copy2(p, indices / p.name)

    def update_engine_state(self):
        ready = all(p.exists() for p in [self.engine/"go-realtime_gui.bat", self.engine/"runtime"/"python.exe",
            self.engine/"assets"/"hubert_base"/"config.json", self.engine/"assets"/"rmvpe"/"rmvpe.pt"])
        self.launch_btn.setEnabled(ready)
        if ready:
            self.log.setText("Движок RVC и CUDA-компоненты найдены. Можно запускать панель.")
            self.state_badge.setText("ДВИЖОК УСТАНОВЛЕН")
        else:
            self.log.setText("Движок пока не установлен. Установка выполняется один раз.")
            self.state_badge.setText("НУЖНА УСТАНОВКА")

    def install_engine(self):
        script = resource("scripts/install_rvc.ps1")
        if not script.exists():
            QMessageBox.critical(self, "Установщик не найден", str(script)); return
        self.install_btn.setEnabled(False); self.progress.show()
        self.worker = EngineWorker(script); self.worker.output.connect(lambda s: self.log.setText(s[-300:]))
        self.worker.done.connect(self.install_done); self.worker.start()

    def install_done(self, ok, message):
        self.progress.hide(); self.install_btn.setEnabled(True); self.status.setText(message)
        if not ok: QMessageBox.warning(self, "Установка движка", message + " Подробности в engine-install.log.")
        self.update_engine_state()

    def launch_engine(self):
        bat = self.engine / "go-realtime_gui.bat"
        if not bat.exists():
            QMessageBox.information(self, "Нет движка", "Сначала установи RVC-движок."); return
        self.sync_models()
        try:
            launcher = bat.read_text(encoding="utf-8-sig")
            fixed = launcher.replace("runtime\\python.exe -I realtime_gui.py", "runtime\\python.exe realtime_gui.py")
            if fixed != launcher: bat.write_text(fixed, encoding="utf-8")
            py = self.engine / "runtime" / "python.exe"
            if not py.is_file(): raise FileNotFoundError(f"Не найден Python движка: {py}")
            env = os.environ.copy(); env["PATH"] = str(self.engine/"runtime") + os.pathsep + env.get("PATH", "")
            self.engine_process = subprocess.Popen(["cmd.exe", "/c", str(bat)], cwd=str(self.engine), env=env)
            self.panel_hint.setText("Подключаю окно RVC к главной панели…")
            self.embed_timer.start()
            self.status.setText("RVC запускается внутри главного окна. Если окно не появится, проверь журнал движка.")
        except Exception as e: QMessageBox.critical(self, "Ошибка запуска", str(e))

    def try_embed(self):
        if os.name != "nt": return
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "RVC - GUI")
        if hwnd:
            parent = int(self.engine_panel.winId())
            GWL_STYLE = -16; WS_POPUP = 0x80000000; WS_CHILD = 0x40000000; WS_VISIBLE = 0x10000000
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            user32.SetWindowLongW(hwnd, GWL_STYLE, (style & ~WS_POPUP) | WS_CHILD | WS_VISIBLE)
            user32.SetParent(hwnd, parent)
            self.embedded_hwnd = hwnd
            self.panel_hint.hide()
            self.resize_embedded()
            self.embed_timer.stop()
            self.state_badge.setText("RVC ПОДКЛЮЧЁН")
        elif self.engine_process and self.engine_process.poll() is not None:
            self.embed_timer.stop()
            self.panel_hint.setText("RVC завершился до подключения. Проверь, что модель .pth существует и поддерживается.")
            self.panel_hint.show()

    def resize_embedded(self):
        if self.embedded_hwnd and os.name == "nt":
            r = self.engine_panel.contentsRect()
            ctypes.windll.user32.MoveWindow(self.embedded_hwnd, 4, 4, max(100, r.width()-8), max(100, r.height()-8), True)

    def resizeEvent(self, event):
        super().resizeEvent(event); self.resize_embedded()

    def stop_engine(self):
        if self.engine_process and self.engine_process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(self.engine_process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.embedded_hwnd = None; self.embed_timer.stop()
        self.panel_hint.setText("Движок остановлен. Нажми «Запустить панель», чтобы начать снова.")
        self.panel_hint.show(); self.state_badge.setText("ОСТАНОВЛЕН")

    def closeEvent(self, event):
        self.stop_engine()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv); window = MainWindow(); window.show(); sys.exit(app.exec())
