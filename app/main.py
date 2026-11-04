import json, os, shutil, sys, urllib.request, urllib.parse
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QLineEdit, QProgressBar, QGroupBox
)

APP_NAME = "Real Voice AI"
MODEL_EXTENSIONS = {".pth", ".onnx"}
INDEX_EXTENSION = ".index"


def app_data_dir():
    base = Path(os.getenv("LOCALAPPDATA", str(Path.home())))
    root = base / "RealVoiceAI"
    (root / "models").mkdir(parents=True, exist_ok=True)
    return root


class DownloadWorker(QThread):
    progress = Signal(int)
    completed = Signal(bool, str)

    def __init__(self, url: str, target: Path):
        super().__init__()
        self.url, self.target = url, target

    def run(self):
        try:
            request = urllib.request.Request(
                self.url, headers={"User-Agent": "RealVoiceAI/4.1"}
            )
            with urllib.request.urlopen(request, timeout=60) as response, self.target.open("wb") as out:
                total = int(response.headers.get("Content-Length", "0") or 0)
                downloaded = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        self.progress.emit(min(100, int(downloaded * 100 / total)))
            if self.target.stat().st_size < 1024:
                raise RuntimeError("Файл пустой или слишком маленький. Нужна прямая ссылка на файл модели.")
            self.completed.emit(True, f"Файл сохранён: {self.target.name}")
        except Exception as exc:
            self.target.unlink(missing_ok=True)
            self.completed.emit(False, str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Real Voice AI — V4.1")
        self.resize(980, 700)
        self.root = app_data_dir()
        self.models_dir = self.root / "models"
        self.settings_path = self.root / "settings.json"
        self.worker = None
        self.active_model = self.load_active_model()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(13)

        header = QHBoxLayout()
        title = QLabel("REAL VOICE AI")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        version = QLabel("V4.1  •  MODEL MANAGER")
        version.setObjectName("muted")
        header.addWidget(version)
        layout.addLayout(header)

        subtitle = QLabel("Голосовые модели — импорт, выбор и управление")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)

        self.status = QLabel("Добавь совместимую RVC-модель, затем выбери её в списке.")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        body = QHBoxLayout()
        body.setSpacing(16)

        left_box = QGroupBox("Мои голосовые модели")
        left_layout = QVBoxLayout(left_box)
        self.model_list = QListWidget()
        self.model_list.currentItemChanged.connect(self.on_model_selected)
        left_layout.addWidget(self.model_list)
        self.active_label = QLabel("Активная модель: не выбрана")
        self.active_label.setObjectName("muted")
        left_layout.addWidget(self.active_label)
        model_actions = QHBoxLayout()
        self.select_btn = QPushButton("Выбрать модель")
        self.select_btn.clicked.connect(self.select_model)
        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.clicked.connect(self.delete_model)
        model_actions.addWidget(self.select_btn)
        model_actions.addWidget(self.delete_btn)
        left_layout.addLayout(model_actions)
        body.addWidget(left_box, 3)

        right_box = QGroupBox("Добавить голос")
        right_layout = QVBoxLayout(right_box)
        self.import_btn = QPushButton("＋  Импортировать модель")
        self.import_btn.clicked.connect(self.import_files)
        right_layout.addWidget(self.import_btn)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Прямая HTTPS-ссылка на .pth, .onnx или .index")
        right_layout.addWidget(self.url_input)
        self.download_btn = QPushButton("Скачать по ссылке")
        self.download_btn.clicked.connect(self.download_model)
        right_layout.addWidget(self.download_btn)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        right_layout.addWidget(self.progress)

        help_text = QLabel(
            "Основная модель: .pth или .onnx\n"
            "Дополнительный индекс RVC: .index\n\n"
            "Важно: расширение файла не гарантирует совместимость. "
            "Не импортируй неизвестные .pth-файлы из непроверенных источников."
        )
        help_text.setObjectName("muted")
        help_text.setWordWrap(True)
        right_layout.addWidget(help_text)
        right_layout.addStretch()
        body.addWidget(right_box, 2)
        layout.addLayout(body, 1)

        self.engine_notice = QLabel(
            "Нейросетевой realtime-движок пока не подключён. "
            "Выбор модели здесь сохраняется, но звук ещё не преобразуется. "
            "Кнопка запуска станет доступна после интеграции и проверки inference/audio backend."
        )
        self.engine_notice.setObjectName("warning")
        self.engine_notice.setWordWrap(True)
        layout.addWidget(self.engine_notice)

        footer = QHBoxLayout()
        refresh_btn = QPushButton("Обновить список")
        refresh_btn.clicked.connect(self.refresh_models)
        footer.addWidget(refresh_btn)
        footer.addStretch()
        self.start_btn = QPushButton("Запуск преобразования — пока недоступен")
        self.start_btn.setEnabled(False)
        footer.addWidget(self.start_btn)
        layout.addLayout(footer)

        self.setStyleSheet("""
            QMainWindow { background:#11151d; color:#eef2f7; }
            QWidget { color:#eef2f7; font-size:14px; }
            QLabel#title { font-size:27px; font-weight:800; letter-spacing:2px; }
            QLabel#subtitle { font-size:18px; color:#c6d2e1; }
            QLabel#muted { color:#91a0b4; }
            QLabel#status { background:#1b2635; border:1px solid #30445c; border-radius:10px; padding:12px; }
            QLabel#warning { background:#342b1c; color:#f4d69b; border-radius:9px; padding:12px; }
            QGroupBox { border:1px solid #2c394a; border-radius:10px; margin-top:10px; padding:12px; font-weight:600; }
            QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 5px; }
            QListWidget { background:#171e29; border:1px solid #2c394a; border-radius:9px; padding:8px; }
            QPushButton { background:#273448; border:1px solid #3b4d65; border-radius:9px; padding:11px; }
            QPushButton:hover { background:#344963; }
            QPushButton:disabled { color:#778394; background:#1a202a; }
            QLineEdit { background:#171e29; border:1px solid #3b4d65; border-radius:8px; padding:11px; }
            QProgressBar { background:#202a38; border:0; border-radius:5px; height:9px; }
            QProgressBar::chunk { background:#49b98c; border-radius:5px; }
        """)
        self.refresh_models()

    def load_active_model(self):
        try:
            return json.loads(self.settings_path.read_text(encoding="utf-8")).get("active_model")
        except Exception:
            return None

    def save_active_model(self):
        self.settings_path.write_text(
            json.dumps({"active_model": self.active_model}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def refresh_models(self):
        self.model_list.clear()
        files = sorted(p for p in self.models_dir.iterdir()
                       if p.is_file() and p.suffix.lower() in MODEL_EXTENSIONS)
        for path in files:
            size_mb = path.stat().st_size / (1024 * 1024)
            has_index = path.with_suffix(INDEX_EXTENSION).exists()
            suffix = "  •  INDEX" if has_index else ""
            item = QListWidgetItem(f"{path.name}  •  {size_mb:.1f} MB{suffix}")
            item.setData(256, path.name)
            if path.name == self.active_model:
                item.setText("✓  " + item.text())
            self.model_list.addItem(item)
        if not files:
            self.model_list.addItem("Пока нет моделей — импортируй .pth или .onnx")
        self.active_label.setText(
            f"Активная модель: {self.active_model}" if self.active_model else "Активная модель: не выбрана"
        )

    def selected_path(self):
        item = self.model_list.currentItem()
        if not item:
            return None
        name = item.data(256)
        return self.models_dir / name if name else None

    def on_model_selected(self, current, previous):
        path = self.selected_path()
        self.select_btn.setEnabled(path is not None and path.exists())

    def select_model(self):
        path = self.selected_path()
        if not path or not path.exists():
            return
        self.active_model = path.name
        self.save_active_model()
        self.refresh_models()
        self.status.setText(f"Выбрана модель: {path.name}. Реальное преобразование станет доступно после подключения движка.")

    def import_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выбери файлы модели", str(Path.home()),
            "Файлы моделей (*.pth *.onnx *.index)"
        )
        if not files:
            return
        copied = 0
        for filename in files:
            src = Path(filename)
            if src.suffix.lower() not in MODEL_EXTENSIONS | {INDEX_EXTENSION}:
                continue
            dst = self.models_dir / src.name
            if src.resolve() != dst.resolve():
                shutil.copy2(src, dst)
            copied += 1
        self.refresh_models()
        self.status.setText(f"Импортировано файлов: {copied}. Совместимость ещё должна быть проверена inference-движком.")

    def download_model(self):
        url = self.url_input.text().strip()
        if not url.startswith(("https://", "http://")):
            QMessageBox.warning(self, "Ссылка", "Вставь прямую HTTP(S)-ссылку на файл.")
            return
        filename = Path(urllib.parse.urlparse(url).path).name
        if not filename or Path(filename).suffix.lower() not in MODEL_EXTENSIONS | {INDEX_EXTENSION}:
            QMessageBox.warning(self, "Формат", "Ссылка должна вести на .pth, .onnx или .index.")
            return
        self.download_btn.setEnabled(False)
        self.progress.setValue(0)
        self.worker = DownloadWorker(url, self.models_dir / filename)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.completed.connect(self.download_completed)
        self.worker.start()

    def download_completed(self, success, message):
        self.download_btn.setEnabled(True)
        self.status.setText(message)
        self.refresh_models()
        if not success:
            QMessageBox.warning(self, "Ошибка загрузки", message)

    def delete_model(self):
        path = self.selected_path()
        if not path or not path.exists():
            return
        answer = QMessageBox.question(self, "Удалить модель", f"Удалить {path.name}?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        path.unlink()
        if self.active_model == path.name:
            self.active_model = None
            self.save_active_model()
        self.refresh_models()
        self.status.setText(f"Модель удалена: {path.name}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
