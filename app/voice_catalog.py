import json, urllib.parse, urllib.request
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QSplitter)

API = "https://huggingface.co/api/models"

class SearchWorker(QThread):
    results = Signal(list); failed = Signal(str)
    def __init__(self, query):
        super().__init__(); self.query = query
    def run(self):
        try:
            params = urllib.parse.urlencode({"search": self.query or "RVC", "limit": 40, "full": "true", "sort": "downloads", "direction": "-1"})
            req = urllib.request.Request(API + "?" + params, headers={"User-Agent":"RealVoiceAI/6.0"})
            with urllib.request.urlopen(req, timeout=25) as response: data = json.loads(response.read().decode("utf-8"))
            items = []
            for model in data:
                files = [x.get("rfilename","") for x in model.get("siblings",[])]
                pths = [x for x in files if x.lower().endswith(".pth")]
                idx = [x for x in files if x.lower().endswith(".index")]
                if pths:
                    items.append({"id":model.get("id",""),"downloads":model.get("downloads",0),"likes":model.get("likes",0),
                                  "pth":pths,"index":idx,"tags":model.get("tags",[])})
            self.results.emit(items)
        except Exception as e: self.failed.emit(str(e))

class DownloadWorker(QThread):
    progress = Signal(int); done = Signal(bool, str)
    def __init__(self, repo, filename, target):
        super().__init__(); self.repo=repo; self.filename=filename; self.target=Path(target)
    def run(self):
        try:
            url = "https://huggingface.co/" + self.repo + "/resolve/main/" + urllib.parse.quote(self.filename, safe="/")
            req=urllib.request.Request(url, headers={"User-Agent":"RealVoiceAI/6.0"})
            self.target.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.target.with_suffix(self.target.suffix+".download")
            with urllib.request.urlopen(req,timeout=60) as response, open(tmp,"wb") as out:
                total=int(response.headers.get("Content-Length",0)); got=0
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk: break
                    out.write(chunk); got+=len(chunk)
                    if total: self.progress.emit(min(100,int(got*100/total)))
            tmp.replace(self.target); self.done.emit(True,str(self.target))
        except Exception as e:
            try:
                if tmp.exists(): tmp.unlink()
            except Exception: pass
            self.done.emit(False,str(e))

class VoiceCatalogDialog(QDialog):
    def __init__(self, model_dir, parent=None):
        super().__init__(parent); self.setWindowTitle("Каталог голосов — Real Voice AI"); self.resize(860,620)
        self.model_dir=Path(model_dir); self.results=[]; self.worker=None; self.downloads=[]
        layout=QVBoxLayout(self)
        title=QLabel("КАТАЛОГ ГОЛОСОВ"); title.setStyleSheet("font-size:22px;font-weight:800")
        layout.addWidget(title)
        note=QLabel("Поиск моделей RVC на Hugging Face. Перед установкой проверь описание, демо и лицензию модели.")
        note.setWordWrap(True); note.setStyleSheet("color:#9aa9bb"); layout.addWidget(note)
        bar=QHBoxLayout(); self.search=QLineEdit(); self.search.setPlaceholderText("Например: female voice, deep male, anime…")
        self.search.returnPressed.connect(self.search_models); bar.addWidget(self.search)
        b=QPushButton("Найти голоса"); b.clicked.connect(self.search_models); bar.addWidget(b); layout.addLayout(bar)
        split=QSplitter(Qt.Orientation.Horizontal)
        self.items=QListWidget(); self.items.currentRowChanged.connect(self.show_model); split.addWidget(self.items)
        right=QVBoxLayout(); panel=QDialog()
        self.details=QLabel("Введи запрос и нажми «Найти голоса»."); self.details.setWordWrap(True); self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right.addWidget(self.details)
        self.files=QListWidget(); right.addWidget(self.files)
        self.download_btn=QPushButton("Скачать выбранный файл"); self.download_btn.clicked.connect(self.download_selected); right.addWidget(self.download_btn)
        self.progress=QProgressBar(); self.progress.hide(); right.addWidget(self.progress)
        holder=QDialog(); holder.setLayout(right); split.addWidget(holder); split.setSizes([360,480]); layout.addWidget(split)
        foot=QHBoxLayout(); self.status=QLabel("Источник: Hugging Face"); self.status.setStyleSheet("color:#9aa9bb"); foot.addWidget(self.status); foot.addStretch()
        close=QPushButton("Закрыть"); close.clicked.connect(self.accept); foot.addWidget(close); layout.addLayout(foot)
        self.setStyleSheet("""
        QDialog{background:#10151e;color:#edf2f8} QLabel{color:#edf2f8}
        QLineEdit,QListWidget{background:#171f2c;border:1px solid #34445a;border-radius:7px;padding:8px;color:#edf2f8}
        QPushButton{background:#293a50;border:1px solid #405674;border-radius:7px;padding:9px 12px;color:#fff}
        QPushButton:hover{background:#385575} QProgressBar{background:#202b3a;border:0;height:8px}
        QProgressBar::chunk{background:#438ce0}
        """)
        self.search_models()

    def search_models(self):
        q=self.search.text().strip() or "RVC"
        self.status.setText("Ищу модели…"); self.items.clear(); self.details.setText("Загрузка каталога…"); self.files.clear()
        self.worker=SearchWorker(q); self.worker.results.connect(self.loaded); self.worker.failed.connect(lambda e:self.status.setText("Ошибка поиска: "+e)); self.worker.start()

    def loaded(self, data):
        self.results=data; self.items.clear()
        for x in data:
            item=QListWidgetItem(f'{x["id"]}\n⬇ {x["downloads"]:,}   ♥ {x["likes"]}')
            item.setData(Qt.ItemDataRole.UserRole,x); self.items.addItem(item)
        self.status.setText(f"Найдено моделей: {len(data)}" if data else "Не найдено моделей с файлами .pth. Попробуй другой запрос.")
        if data: self.items.setCurrentRow(0)

    def show_model(self,row):
        if row<0 or row>=len(self.results): return
        m=self.results[row]; self.files.clear()
        self.details.setText(f'{m["id"]}\nЗагрузок: {m["downloads"]:,} • Оценок: {m["likes"]}\nФайлы .pth — веса модели. Файлы .index улучшают сходство тембра, если идут в комплекте.')
        for f in m["pth"]+m["index"]:
            it=QListWidgetItem(f); it.setData(Qt.ItemDataRole.UserRole,f); self.files.addItem(it)

    def download_selected(self):
        row=self.items.currentRow(); file_item=self.files.currentItem()
        if row<0 or not file_item: return
        m=self.results[row]; filename=file_item.data(Qt.ItemDataRole.UserRole)
        target=self.model_dir/Path(filename).name
        if target.exists() and target.stat().st_size>0:
            QMessageBox.information(self,"Уже скачано",f"Файл уже есть: {target.name}"); return
        self.download_btn.setEnabled(False); self.progress.setValue(0); self.progress.show()
        worker=DownloadWorker(m["id"],filename,target); self.downloads.append(worker)
        worker.progress.connect(self.progress.setValue)
        worker.done.connect(lambda ok,msg:self.download_done(ok,msg,worker)); worker.start()

    def download_done(self,ok,msg,worker):
        self.download_btn.setEnabled(True); self.progress.hide()
        self.status.setText(("Скачано: " if ok else "Ошибка загрузки: ")+msg)
        if ok: QMessageBox.information(self,"Готово","Файл добавлен в «Мои модели». Если у модели есть .index, скачай его тем же способом.")
        else: QMessageBox.warning(self,"Не удалось скачать",msg)
        if worker in self.downloads: self.downloads.remove(worker)
