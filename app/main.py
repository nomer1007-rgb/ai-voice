import os, sys, json, shutil, subprocess, ctypes, re, urllib.request, urllib.parse
from pathlib import Path
from PySide6.QtCore import QThread, Signal, QTimer, Qt
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QProgressBar,
    QFrame, QLineEdit, QScrollArea, QGridLayout, QStackedWidget, QSizePolicy, QComboBox, QSlider, QCheckBox)

APP_NAME = "Real Voice AI"
API = "https://huggingface.co/api"

def data_root():
    p = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "RealVoiceAI"
    (p / "models").mkdir(parents=True, exist_ok=True)
    return p

def resource(name):
    candidates=[]
    meipass=getattr(sys,"_MEIPASS",None)
    if meipass: candidates.append(Path(meipass)/name)
    exe=Path(sys.executable).resolve().parent
    candidates += [exe/name,exe/"_internal"/name,exe/"scripts"/Path(name).name,
                   exe.parent/"scripts"/Path(name).name,Path(__file__).resolve().parent/name,
                   Path(__file__).resolve().parent/"scripts"/Path(name).name]
    return next((p for p in candidates if p.is_file()),candidates[0])

def get_json(url):
    req=urllib.request.Request(url,headers={"User-Agent":"RealVoiceAI/6.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=25) as r: return json.loads(r.read().decode("utf-8"))

class SearchWorker(QThread):
    results=Signal(list); failed=Signal(str); progress=Signal(str)
    def __init__(self,query): super().__init__(); self.query=query
    def run(self):
        found=[]; errors=[]; seen=set()
        # Search broad RVC repositories first. Category labels are hints, not
        # literal repository names, so always retain the RVC term.
        terms=[]
        raw=(self.query or "").strip()
        russian_category = raw == "__RUSSIAN_RVC__"
        if russian_category:
            terms=["Russian RVC","Russian voice RVC","русский RVC","ru RVC voice"]
        elif not raw or raw.lower() in ("rvc voice","all","все"):
            terms=["RVC"]
        else:
            terms=[raw, "RVC"]
        self.progress.emit("Ищу RVC-модели на Hugging Face…")
        for term in terms:
            try:
                q=urllib.parse.urlencode({"search":term,"limit":100,"sort":"downloads","direction":"-1","expand[]":"siblings"})
                items=get_json(API+"/models?"+q)
                for m in items:
                    mid=m.get("id","")
                    if not mid or mid in seen: continue
                    siblings=m.get("siblings",[]) or []
                    paths=[x.get("rfilename","") for x in siblings if isinstance(x,dict)]
                    pths=[p for p in paths if p.lower().endswith(".pth") and not Path(p).name.upper().startswith(("G_","D_"))]
                    if not pths: continue
                    idxs=[p for p in paths if p.lower().endswith(".index")]
                    seen.add(mid)
                    found.append({"id":mid,"source":"Hugging Face","downloads":m.get("downloads",0),"likes":m.get("likes",0),"pth_files":pths,"index_files":idxs})
            except Exception as e:
                errors.append("Hugging Face: "+str(e))
            if found and not russian_category: break
        # GitHub is a fallback only; avoid serially walking dozens of huge trees.
        if not found:
            self.progress.emit("На Hugging Face ничего не найдено. Проверяю GitHub…")
            try:
                github_query = "Russian RVC voice model" if russian_category else ((raw+" RVC") if raw else "RVC voice conversion")
                terms_q=urllib.parse.quote(github_query)
                repos=get_json("https://api.github.com/search/repositories?q="+terms_q+"&per_page=12&sort=stars")
                for repo in repos.get("items",[])[:12]:
                    owner=repo.get("owner",{}).get("login",""); name=repo.get("name",""); branch=repo.get("default_branch","main")
                    if not owner or not name: continue
                    try:
                        tree=get_json(f"https://api.github.com/repos/{owner}/{name}/git/trees/{urllib.parse.quote(branch,safe='')}?recursive=1")
                        paths=[x.get("path","") for x in tree.get("tree",[]) if x.get("type")=="blob"]
                        pths=[p for p in paths if p.lower().endswith(".pth") and not Path(p).name.upper().startswith(("G_","D_"))]
                        if not pths: continue
                        idxs=[p for p in paths if p.lower().endswith(".index")]
                        found.append({"id":f"{owner}/{name}","source":"GitHub","branch":branch,"downloads":repo.get("stargazers_count",0),"likes":repo.get("forks_count",0),"pth_files":pths,"index_files":idxs})
                    except Exception as e:
                        errors.append(f"GitHub {owner}/{name}: {e}")
            except Exception as e: errors.append("GitHub: "+str(e))
        if found: self.results.emit(found)
        elif errors: self.failed.emit("Не удалось загрузить каталог. "+"; ".join(errors[-3:]))
        else: self.results.emit([])

class InstallWorker(QThread):
    progress=Signal(str); done=Signal(bool,str,str)
    def __init__(self,model,folder): super().__init__(); self.model=model; self.folder=Path(folder)
    def run(self):
        try:
            source=self.model.get("source","Hugging Face"); repo=self.model["id"]
            self.progress.emit(f"Проверяю файлы модели ({source})…")
            if source=="GitHub":
                owner,name=repo.split("/",1); branch=self.model.get("branch","main")
                tree=get_json(f"https://api.github.com/repos/{owner}/{name}/git/trees/{urllib.parse.quote(branch,safe='')}?recursive=1")
                paths=[x.get("path","") for x in tree.get("tree",[]) if x.get("type")=="blob"]
            else:
                files=get_json(API+"/models/"+urllib.parse.quote(repo,safe="/")+"/tree/main?recursive=true&expand=false")
                paths=[x.get("path","") for x in files if x.get("type")=="file"]
            pths=[p for p in paths if p.lower().endswith(".pth") and not Path(p).name.upper().startswith(("G_","D_"))]
            idxs=[p for p in paths if p.lower().endswith(".index")]
            if not pths: raise RuntimeError("В репозитории не найден файл весов .pth.")
            pth=pths[0]; stem=Path(pth).stem.lower()
            idx=next((p for p in idxs if stem in Path(p).stem.lower() or Path(p).stem.lower() in stem),idxs[0] if idxs else "")
            chosen=[pth]+([idx] if idx else [])
            self.folder.mkdir(parents=True,exist_ok=True)
            for n,path in enumerate(chosen,1):
                name=Path(path).name; dest=self.folder/name
                if source=="GitHub": url=f"https://raw.githubusercontent.com/{repo}/{branch}/"+urllib.parse.quote(path,safe="/")
                else: url="https://huggingface.co/"+repo+"/resolve/main/"+urllib.parse.quote(path,safe="/")+"?download=true"
                self.progress.emit(f"Загрузка {n}/{len(chosen)}: {name}")
                req=urllib.request.Request(url,headers={"User-Agent":"RealVoiceAI/6.0"})
                with urllib.request.urlopen(req,timeout=120) as response, open(dest,"wb") as out: shutil.copyfileobj(response,out)
            self.done.emit(True,pth,idx)
        except Exception as e: self.done.emit(False,str(e),"")
class EngineWorker(QThread):
    output=Signal(str); done=Signal(bool,str)
    def __init__(self,script): super().__init__(); self.script=script
    def run(self):
        try:
            proc=subprocess.Popen(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(self.script)],
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",
                creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            for line in proc.stdout: self.output.emit(line.rstrip())
            code=proc.wait(); self.done.emit(code==0,"Движок установлен." if code==0 else f"Ошибка установки (код {code}).")
        except Exception as e: self.done.emit(False,str(e))

class VoiceCard(QFrame):
    clicked=Signal(dict)
    def __init__(self,data):
        super().__init__(); self.data=data; self.setObjectName("voiceCard"); self.setCursor(Qt.CursorShape.PointingHandCursor)
        l=QVBoxLayout(self); l.setContentsMargins(14,12,14,12); l.setSpacing(7)
        icon=QLabel("♫"); icon.setObjectName("voiceIcon"); icon.setAlignment(Qt.AlignmentFlag.AlignCenter); l.addWidget(icon)
        name=QLabel(data["id"].split("/")[-1]); name.setObjectName("voiceName"); name.setWordWrap(True); l.addWidget(name)
        owner=QLabel(data.get("source","Hugging Face")+" · "+data["id"]); owner.setObjectName("muted"); owner.setWordWrap(True); l.addWidget(owner)
        meta=QLabel(f"↓ {data.get('downloads',0):,}   ♥ {data.get('likes',0)}"); meta.setObjectName("muted"); l.addWidget(meta)
        self.setMinimumHeight(145); self.setMaximumHeight(175)
    def mousePressEvent(self,event): self.clicked.emit(self.data)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Real Voice AI"); self.resize(1280,850); self.setMinimumSize(980,700)
        self.root=data_root(); self.models=self.root/"models"; self.engine=self.root/"engine"
        self.worker=None; self.search_worker=None; self.search_workers=[]; self.install_worker=None; self.engine_process=None; self.embedded_hwnd=None; self.selected_voice=None
        self.settings_file=self.root/"settings.json"
        try:self.settings=json.loads(self.settings_file.read_text(encoding="utf-8"))
        except Exception:self.settings={}
        self.active=self.settings.get("active_model","")
        base=QWidget(); self.setCentralWidget(base); outer=QHBoxLayout(base); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        side=QFrame(); side.setObjectName("sidebar"); side.setFixedWidth(205); sl=QVBoxLayout(side); sl.setContentsMargins(18,22,18,18); sl.setSpacing(12)
        brand=QLabel("◉  MagicVoice"); brand.setObjectName("brand"); sl.addWidget(brand); sl.addSpacing(16)
        self.nav_voices=QPushButton("♫   Голоса"); self.nav_voices.setObjectName("navActive"); self.nav_voices.clicked.connect(lambda:self.pages.setCurrentIndex(0)); sl.addWidget(self.nav_voices)
        self.nav_models=QPushButton("▤   Мои модели"); self.nav_models.clicked.connect(lambda:self.pages.setCurrentIndex(1)); sl.addWidget(self.nav_models)
        self.nav_settings=QPushButton("⚙   Настройки RVC"); self.nav_settings.clicked.connect(lambda:self.pages.setCurrentIndex(2)); sl.addWidget(self.nav_settings)
        sl.addStretch()
        self.install_engine_btn=QPushButton("Установить движок"); self.install_engine_btn.clicked.connect(self.install_engine); sl.addWidget(self.install_engine_btn)
        self.engine_state=QLabel("Проверка движка…"); self.engine_state.setObjectName("muted"); self.engine_state.setWordWrap(True); sl.addWidget(self.engine_state)
        outer.addWidget(side)
        main=QWidget(); ml=QVBoxLayout(main); ml.setContentsMargins(22,18,22,14); ml.setSpacing(12); outer.addWidget(main,1)
        top=QHBoxLayout(); title=QLabel("ГОЛОСА"); title.setObjectName("heading"); top.addWidget(title); top.addStretch()
        self.search=QLineEdit(); self.search.setPlaceholderText("⌕   Найти голос или модель…"); self.search.setFixedWidth(350); self.search.returnPressed.connect(self.search_models); top.addWidget(self.search)
        searchbtn=QPushButton("Найти"); searchbtn.setObjectName("primary"); searchbtn.clicked.connect(self.search_models); top.addWidget(searchbtn)
        ml.addLayout(top)
        self.categories=QHBoxLayout()
        for label,query in [("Все","RVC voice"),("Русские","__RUSSIAN_RVC__"),("Популярные","RVC voice popular"),("Мужские","male RVC voice"),("Женские","female RVC voice"),("Персонажи","fictional character RVC")]:
            b=QPushButton(label); b.clicked.connect(lambda checked=False,q=query:self.load_category(q)); self.categories.addWidget(b)
        ml.addLayout(self.categories)
        self.pages=QStackedWidget(); ml.addWidget(self.pages,1)
        # catalogue page
        cat=QWidget(); cl=QVBoxLayout(cat); cl.setContentsMargins(0,0,0,0)
        catalog_head=QHBoxLayout()
        self.section=QLabel("Популярные голоса сообщества"); self.section.setObjectName("section"); catalog_head.addWidget(self.section); catalog_head.addStretch()
        self.sort_combo=QComboBox()
        self.sort_combo.addItem("Сначала популярные (скачивания)","downloads")
        self.sort_combo.addItem("По лайкам","likes")
        self.sort_combo.addItem("По названию","name")
        self.sort_combo.currentIndexChanged.connect(self.sort_results)
        catalog_head.addWidget(self.sort_combo)
        cl.addLayout(catalog_head)
        self.catalog_items=[]
        self.results_scroll=QScrollArea(); self.results_scroll.setWidgetResizable(True); self.results_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.results_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results_host=QWidget(); self.grid=QGridLayout(self.results_host); self.grid.setContentsMargins(2,8,8,8); self.grid.setSpacing(12)
        for col in range(3): self.grid.setColumnStretch(col,1)
        self.results_scroll.setWidget(self.results_host); cl.addWidget(self.results_scroll,1)
        self.search_status=QLabel("Ищу доступные RVC-модели на Hugging Face…"); self.search_status.setObjectName("muted"); cl.addWidget(self.search_status)
        self.pages.addWidget(cat)
        # local models page
        mine=QWidget(); vl=QVBoxLayout(mine); vl.setContentsMargins(0,0,0,0); vl.setSpacing(12)
        mine_head=QHBoxLayout(); mine_title=QLabel("Установленные голосовые модели"); mine_title.setObjectName("section"); mine_head.addWidget(mine_title); mine_head.addStretch()
        self.local_search=QLineEdit(); self.local_search.setPlaceholderText("⌕   Найти среди моих голосов…"); self.local_search.setFixedWidth(310); self.local_search.textChanged.connect(self.refresh_local); mine_head.addWidget(self.local_search)
        imp=QPushButton("Импортировать голос"); imp.setObjectName("primary"); imp.clicked.connect(self.import_model); mine_head.addWidget(imp); vl.addLayout(mine_head)
        self.local_scroll=QScrollArea(); self.local_scroll.setWidgetResizable(True); self.local_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.local_host=QWidget(); self.local_grid=QGridLayout(self.local_host); self.local_grid.setContentsMargins(2,8,2,8); self.local_grid.setSpacing(12); self.local_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.local_scroll.setWidget(self.local_host); vl.addWidget(self.local_scroll,1)
        self.local_count=QLabel("Голосов: 0"); self.local_count.setObjectName("muted"); vl.addWidget(self.local_count)
        self.pages.addWidget(mine)
        # settings page - RVC GUI hosted in one parent window
        sett=QWidget(); st=QVBoxLayout(sett); st.addWidget(QLabel("Аудиоустройства и виртуальный микрофон"))
        st.addWidget(QLabel("Выбери физический микрофон и виртуальный выход (например, CABLE Input или VoiceMeeter Input). Именно этот выход станет источником виртуального микрофона для Discord."))
        devices=QHBoxLayout()
        self.input_device=QComboBox(); self.input_device.setMinimumWidth(260)
        self.output_device=QComboBox(); self.output_device.setMinimumWidth(260)
        devices.addWidget(QLabel("Микрофон:")); devices.addWidget(self.input_device,1)
        devices.addWidget(QLabel("Виртуальный выход:")); devices.addWidget(self.output_device,1)
        refresh=QPushButton("Обновить устройства"); refresh.clicked.connect(self.refresh_audio_devices); devices.addWidget(refresh)
        applydev=QPushButton("Применить"); applydev.setObjectName("primary"); applydev.clicked.connect(self.apply_audio_devices); devices.addWidget(applydev)
        st.addLayout(devices)
        # Native, readable voice-tuning controls. Values are written to RVC config before launch.
        tune_title=QLabel("Качество и обработка голоса"); tune_title.setObjectName("section"); st.addWidget(tune_title)
        tune_card=QFrame(); tune_card.setObjectName("tuneCard")
        tune_grid=QGridLayout(tune_card); tune_grid.setContentsMargins(16,12,16,12); tune_grid.setHorizontalSpacing(22); tune_grid.setVerticalSpacing(10)
        self.tuning_sliders={}
        def add_tuning(row,col,key,title,minimum,maximum,default,scale=1,help_text=""):
            cell=QWidget(); box=QVBoxLayout(cell); box.setContentsMargins(0,0,0,0); box.setSpacing(3)
            head=QHBoxLayout(); name=QLabel(title); name.setObjectName("tuneLabel"); value=QLabel(); value.setObjectName("tuneValue"); head.addWidget(name); head.addStretch(); head.addWidget(value); box.addLayout(head)
            slider=QSlider(Qt.Orientation.Horizontal); slider.setRange(minimum,maximum); slider.setValue(default); slider.setObjectName("tuneSlider")
            slider.valueChanged.connect(lambda v,l=value,s=scale:l.setText(f"{v/ s:.2f}" if s>1 else str(v)))
            value.setText(f"{default/scale:.2f}" if scale>1 else str(default)); box.addWidget(slider)
            if help_text:
                hint=QLabel(help_text); hint.setObjectName("muted"); hint.setWordWrap(True); box.addWidget(hint)
            tune_grid.addWidget(cell,row,col); self.tuning_sliders[key]=(slider,scale)
        add_tuning(0,0,"pitch","Высота голоса", -12,12,0,1,"Ниже — более низкий голос, выше — более высокий")
        add_tuning(0,1,"index_rate","Сходство с моделью",0,100,50,100,"Выше — точнее тембр модели; слишком высокое значение может добавить артефакты")
        add_tuning(1,0,"rms_mix_rate","Баланс громкости",0,100,25,100,"Сохраняет естественную динамику исходного голоса")
        add_tuning(1,1,"threhold","Порог микрофона",-60,0,-45,1,"Игнорирует тихий фоновый шум; ближе к 0 — меньше чувствительность")
        add_tuning(2,0,"block_time","Отклик / задержка",5,50,25,100,"Меньше — быстрее отклик, но выше нагрузка и риск щелчков")
        add_tuning(2,1,"extra_time","Стабильность обработки",5,50,25,10,"Больше — устойчивее обработка, но может вырасти задержка")
        st.addWidget(tune_card)
        noise_row=QHBoxLayout()
        self.input_denoise=QCheckBox("Шумоподавление микрофона"); self.input_denoise.setChecked(True)
        self.output_denoise=QCheckBox("Очистка выходного звука"); self.output_denoise.setChecked(False)
        noise_row.addWidget(self.input_denoise); noise_row.addWidget(self.output_denoise); noise_row.addStretch(); st.addLayout(noise_row)
        noise_note=QLabel("Встроенный подавитель RVC снижает постоянный фоновый шум. Для сильного шума лучше использовать отдельный RNNoise/RTX Voice — встроенный фильтр не заменяет их.")
        noise_note.setObjectName("muted"); noise_note.setWordWrap(True); st.addWidget(noise_note)
        self.audio_hint=QLabel("Для Discord затем выбери в настройках ввода устройство соответствующее «CABLE Output» или выходу выбранного виртуального кабеля.")
        self.audio_hint.setObjectName("muted"); self.audio_hint.setWordWrap(True); st.addWidget(self.audio_hint)
        bar=QHBoxLayout(); launch=QPushButton("Запустить RVC"); launch.setObjectName("primary"); launch.clicked.connect(self.launch_engine); bar.addWidget(launch)
        stop=QPushButton("Остановить"); stop.clicked.connect(self.stop_engine); bar.addWidget(stop); bar.addStretch(); st.addLayout(bar)
        self.engine_status_card=QFrame(); self.engine_status_card.setObjectName("tuneCard"); status_layout=QHBoxLayout(self.engine_status_card)
        self.engine_status_dot=QLabel("●"); self.engine_status_dot.setStyleSheet("color:#8888aa;font-size:22px"); status_layout.addWidget(self.engine_status_dot)
        self.panel_hint=QLabel("Движок остановлен. Выбери голос и нажми «Запустить RVC»."); self.panel_hint.setObjectName("section"); status_layout.addWidget(self.panel_hint,1)
        st.addWidget(self.engine_status_card)
        self.pages.addWidget(sett)
        # bottom selected voice bar
        bottom=QFrame(); bottom.setObjectName("bottomBar"); bl=QHBoxLayout(bottom); bl.setContentsMargins(14,9,14,9)
        self.selected_icon=QLabel("♫"); self.selected_icon.setObjectName("voiceIconSmall"); bl.addWidget(self.selected_icon)
        self.selected_label=QLabel("Голос не выбран"); self.selected_label.setObjectName("bottomName"); bl.addWidget(self.selected_label); bl.addStretch()
        self.install_btn=QPushButton("Установить голос"); self.install_btn.setObjectName("primary"); self.install_btn.setEnabled(False); self.install_btn.clicked.connect(self.install_selected); bl.addWidget(self.install_btn)
        self.set_active_btn=QPushButton("Выбрать"); self.set_active_btn.clicked.connect(self.activate_selected); self.set_active_btn.setEnabled(False); bl.addWidget(self.set_active_btn)
        ml.addWidget(bottom)
        self.setStyleSheet("""
        QMainWindow,QWidget{background:#090b19;color:#eef0ff;font-size:13px}
        QFrame#sidebar{background:#080a18;border-right:1px solid #25243e}
        QLabel#brand{font-size:21px;font-weight:800;color:#fff;padding:8px 4px}
        QLabel#heading{font-size:25px;font-weight:800;letter-spacing:0px}
        QLabel#section{font-size:19px;font-weight:750;padding:10px 2px;color:#fff}
        QPushButton{background:#17182b;border:1px solid #292943;border-radius:10px;padding:10px 14px;color:#e7e7f5}
        QPushButton:hover{background:#282044;border-color:#8057ff}
        QPushButton#primary{background:#8044f5;border:1px solid #986aff;color:white;font-weight:750;padding:11px 16px}
        QPushButton#primary:hover{background:#955cff}
        QPushButton#navActive{background:#30205b;border:1px solid #8754ff;text-align:left}
        QLineEdit{background:#17172a;border:1px solid #302d50;border-radius:13px;padding:12px 14px;color:white}
        QComboBox{background:#17172a;border:1px solid #302d50;border-radius:8px;padding:8px;color:#f0efff}
        QFrame#voiceCard{background:#131526;border:1px solid #262943;border-radius:14px}
        QFrame#voiceCard:hover{background:#1c1a36;border:1px solid #895aff}
        QLabel#voiceIcon{background:#242344;border-radius:12px;color:#e7dfff;font-size:36px;min-height:64px;max-height:64px}
        QLabel#voiceName{font-weight:750;color:white;font-size:14px}
        QFrame#bottomBar{background:#141629;border:1px solid #292b49;border-radius:14px}
        QFrame#tuneCard{background:#131526;border:1px solid #292b49;border-radius:14px}
        QFrame#rvcPanel{background:#131526;border:1px solid #292b49;border-radius:12px}
        QFrame#voiceCard QPushButton{padding:9px 10px}
        QFrame#voiceCard QLabel#voiceIcon{min-height:64px;max-height:64px}
        QLabel#tuneLabel{font-weight:700;color:#e9e7ff}
        QLabel#tuneValue{color:#c5adff;font-weight:800;min-width:48px;background:#1c1c32;border-radius:6px;padding:4px}
        QSlider#tuneSlider{min-height:22px}
        QSlider#tuneSlider::groove:horizontal{height:6px;background:#302d4b;border-radius:3px}
        QSlider#tuneSlider::sub-page:horizontal{background:#8752ff;border-radius:3px}
        QSlider#tuneSlider::handle:horizontal{background:#fff;border:2px solid #9a75ff;width:16px;height:16px;margin:-7px 0;border-radius:8px}
        QCheckBox{spacing:9px;color:#eeeaff;font-weight:650;padding:7px}
        QCheckBox::indicator{width:18px;height:18px;border-radius:9px;background:#28283d;border:1px solid #665a90}
        QCheckBox::indicator:checked{background:#8752ff;border:1px solid #b39aff}
        QScrollArea{background:transparent;border:0}
        QListWidget{background:#101225;border:0}
        QLabel#heading{font-size:24px;font-weight:800;letter-spacing:2px}
        QLabel#section{font-size:18px;font-weight:700;padding:8px 2px;color:#fff}
        QLabel#muted{color:#8589a9;font-size:11px}
        QPushButton{background:#191936;border:1px solid #2a2a50;border-radius:9px;padding:9px 12px;color:#dfe1f8}
        QPushButton:hover{background:#292451;border-color:#7255ff}
        QPushButton#primary{background:#7952ff;border-color:#9276ff;color:white;font-weight:700}
        QPushButton#primary:hover{background:#8b6aff}
        QPushButton#navActive{background:#27204e;border:1px solid #7952ff;text-align:left}
        QLineEdit{background:#171632;border:1px solid #302c58;border-radius:14px;padding:11px 14px;color:white}
        QFrame#voiceCard{background:#171733;border:1px solid #27264c;border-radius:13px}
        QFrame#voiceCard:hover{background:#211e49;border:1px solid #8b65ff}
        QLabel#voiceIcon{background:#242344;border-radius:12px;color:#e7dfff;font-size:36px;min-height:64px;max-height:64px}
        QLabel#voiceIconSmall{background:#252044;border-radius:10px;color:#fff;font-size:24px;min-width:44px;max-width:44px;min-height:42px;max-height:42px;qproperty-alignment:AlignCenter}
        QLabel#voiceName{font-weight:700;color:white}
        QFrame#bottomBar{background:#171733;border:1px solid #2b2952;border-radius:12px}
        QLabel#bottomName{font-weight:700}
        QFrame#tuneCard{background:#171733;border:1px solid #302e55;border-radius:12px}
        QLabel#tuneLabel{font-weight:700;color:#e9e7ff}
        QLabel#tuneValue{color:#bbaaff;font-weight:800;min-width:42px}
        QSlider#tuneSlider{min-height:20px}
        QSlider#tuneSlider::groove:horizontal{height:6px;background:#343253;border-radius:3px}
        QSlider#tuneSlider::sub-page:horizontal{background:#805cff;border-radius:3px}
        QSlider#tuneSlider::handle:horizontal{background:#fff;border:2px solid #9a7cff;width:16px;height:16px;margin:-7px 0;border-radius:8px}
        QCheckBox{spacing:8px;color:#e8e7ff}
        QCheckBox::indicator{width:18px;height:18px;border-radius:5px;background:#252444;border:1px solid #6255a0}
        QCheckBox::indicator:checked{background:#805cff;border:1px solid #a58bff}
        QFrame#rvcPanel{background:#15162f;border:1px solid #302e55;border-radius:10px}
        QListWidget,QScrollArea{background:#101229;border:0}
        """)
        self.refresh_local(); self.update_engine_state(); self.load_category("RVC voice")

    def clear_cards(self):
        while self.grid.count():
            item=self.grid.takeAt(0); w=item.widget()
            if w:w.deleteLater()

    def show_results(self,items):
        self.catalog_items=list(items)
        self.sort_results()

    def sort_results(self,*_):
        self.clear_cards()
        items=list(self.catalog_items)
        key=self.sort_combo.currentData() if hasattr(self,"sort_combo") else "downloads"
        if key=="name":
            items.sort(key=lambda x:x.get("id","").split("/")[-1].casefold())
        else:
            items.sort(key=lambda x:int(x.get(key,0) or 0),reverse=True)
        if not items:
            self.search_status.setText("Модели не найдены. Попробуй «Все» или запрос RVC.")
            return
        for i,item in enumerate(items):
            card=VoiceCard(item); card.clicked.connect(self.select_voice)
            self.grid.addWidget(card,i//3,i%3)
        self.search_status.setText(f"Найдено RVC-моделей: {len(items)}. Сортировка: {self.sort_combo.currentText()}. Выбери карточку для установки.")

    def load_category(self,q):
        self.search.setText(q if q!="RVC voice" else "")
        self.section.setText(q.title()+" — каталог сообщества")
        self.search_status.setText("Поиск моделей…")
        self.search_worker=SearchWorker(q); self.search_workers.append(self.search_worker); self.search_worker.finished.connect(lambda w=self.search_worker: self.search_workers.remove(w) if w in self.search_workers else None); self.search_worker.progress.connect(self.search_status.setText); self.search_worker.results.connect(self.show_results); self.search_worker.failed.connect(lambda e:self.search_status.setText(e)); self.search_worker.start()

    def search_models(self):
        q=self.search.text().strip() or "RVC voice"
        self.section.setText("Результаты поиска: "+q); self.search_status.setText("Ищу модели…")
        self.search_worker=SearchWorker(q); self.search_workers.append(self.search_worker); self.search_worker.finished.connect(lambda w=self.search_worker: self.search_workers.remove(w) if w in self.search_workers else None); self.search_worker.progress.connect(self.search_status.setText); self.search_worker.results.connect(self.show_results); self.search_worker.failed.connect(lambda e:self.search_status.setText(e)); self.search_worker.start()

    def select_voice(self,data):
        self.selected_voice=data; self.selected_label.setText(data["id"]); self.install_btn.setEnabled(True)
        self.set_active_btn.setEnabled(False); self.search_status.setText("Выбран репозиторий. При установке программа проверит наличие .pth и подходящего .index.")

    def install_selected(self):
        if not self.selected_voice:return
        self.install_btn.setEnabled(False); self.search_status.setText("Подготовка установки…")
        self.install_worker=InstallWorker(self.selected_voice,self.models)
        self.install_worker.progress.connect(self.search_status.setText)
        self.install_worker.done.connect(self.install_done); self.install_worker.start()

    def install_done(self,ok,pth,idx):
        self.install_btn.setEnabled(True)
        if not ok:
            QMessageBox.warning(self,"Не удалось установить голос",pth); self.search_status.setText("Установка не выполнена."); return
        self.active=Path(pth).name; self.save(); self.sync_models(); self.refresh_local()
        msg="Модель установлена и выбрана активной: "+Path(pth).name
        if idx:msg+="\\nИндекс: "+Path(idx).name
        else:msg+="\\nИндекс не найден — голос можно попробовать без индекса."
        QMessageBox.information(self,"Голос установлен",msg)
        self.search_status.setText("Голос установлен. Открой «Мои модели» и сделай его активным.")

    def refresh_local(self):
        while self.local_grid.count():
            item=self.local_grid.takeAt(0); widget=item.widget()
            if widget: widget.deleteLater()
        files=sorted(self.models.glob("*.pth"),key=lambda p:p.name.lower())
        query=self.local_search.text().strip().lower() if hasattr(self,"local_search") else ""
        shown=[p for p in files if query in p.stem.lower()]
        for i,p in enumerate(shown):
            card=QFrame(); card.setObjectName("voiceCard"); card.setFixedSize(300,168); box=QVBoxLayout(card); box.setContentsMargins(12,10,12,10); box.setSpacing(5)
            head=QHBoxLayout(); icon=QLabel("♫"); icon.setObjectName("voiceIcon"); icon.setAlignment(Qt.AlignmentFlag.AlignCenter); icon.setFixedSize(42,42); head.addWidget(icon)
            name=QLabel(p.stem); name.setObjectName("voiceName"); name.setWordWrap(True); head.addWidget(name,1); box.addLayout(head)
            idx=next((x for x in self.models.glob("*.index") if p.stem.lower() in x.stem.lower() or x.stem.lower() in p.stem.lower()),None)
            size=p.stat().st_size/(1024*1024)
            meta=QLabel(f"RVC · .pth · {size:.1f} МБ"+(" · .index" if idx else "")); meta.setObjectName("muted"); box.addWidget(meta)
            active=QLabel("✓ Активный голос" if p.name==self.active else "Установленная модель"); active.setObjectName("muted"); box.addWidget(active)
            actions=QHBoxLayout()
            use=QPushButton("✓  Активен" if p.name==self.active else "Применить"); use.setObjectName("primary"); use.setEnabled(p.name!=self.active)
            use.clicked.connect(lambda checked=False,path=p:self.set_local_active(path)); actions.addWidget(use,1)
            remove=QPushButton("⋮"); remove.setFixedWidth(40); remove.setToolTip("Удалить модель"); remove.clicked.connect(lambda checked=False,path=p:self.delete_model_file(path)); actions.addWidget(remove)
            box.addLayout(actions); self.local_grid.addWidget(card,i//3,i%3,Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        if not shown:
            empty=QLabel("Пока нет установленных голосов." if not files else "По этому запросу ничего не найдено."); empty.setObjectName("muted"); self.local_grid.addWidget(empty,0,0)
        if hasattr(self,"local_count"): self.local_count.setText(f"Голосов: {len(files)}")

    def import_model(self):
        files,_=QFileDialog.getOpenFileNames(self,"Импорт файлов RVC",str(Path.home()),"RVC (*.pth *.index)")
        for f in files:
            src=Path(f); dst=self.models/src.name
            if src.resolve()!=dst.resolve():shutil.copy2(src,dst)
        self.refresh_local()

    def set_local_active(self,path):
        self.active=path.name; self.save(); self.refresh_local(); self.sync_models()
        if hasattr(self,"selected_label"): self.selected_label.setText(path.stem)
        if hasattr(self,"set_active_btn"): self.set_active_btn.setEnabled(False)
        self.search_status.setText(f"Активный голос: {path.stem}. Перезапусти RVC, если движок уже работает.")

    def choose_local(self):
        files=sorted(self.models.glob("*.pth"))
        if files:self.set_local_active(files[0])

    def activate_selected(self):
        if not self.selected_voice:return
        candidate=Path(self.selected_voice["id"].split("/")[-1])
        self.pages.setCurrentIndex(1)
        self.search_status.setText("После установки выбери файл модели в списке «Мои модели».")

    def delete_model_file(self,p):
        if QMessageBox.question(self,"Удалить модель",f"Удалить {p.name}?")!=QMessageBox.StandardButton.Yes:return
        try:
            p.unlink()
            if self.active==p.name:self.active=""; self.save()
            self.refresh_local()
        except Exception as e: QMessageBox.warning(self,"Не удалось удалить модель",str(e))

    def delete_local(self):
        files=sorted(self.models.glob("*.pth"))
        if files:self.delete_model_file(files[0])

    def save(self):
        self.settings["active_model"]=self.active; self.settings_file.write_text(json.dumps(self.settings,indent=2),encoding="utf-8")

    def sync_models(self):
        weights=self.engine/"assets"/"weights"; indices=self.engine/"assets"/"indices"
        weights.mkdir(parents=True,exist_ok=True); indices.mkdir(parents=True,exist_ok=True)
        for p in self.models.glob("*.pth"):shutil.copy2(p,weights/p.name)
        for p in self.models.glob("*.index"):shutil.copy2(p,indices/p.name)

    def update_engine_state(self):
        ready=all(p.exists() for p in [self.engine/"go-realtime_gui.bat",self.engine/"runtime"/"python.exe",self.engine/"assets"/"hubert_base"/"config.json",self.engine/"assets"/"rmvpe"/"rmvpe.pt"])
        self.engine_state.setText("RVC готов" if ready else "RVC ещё не установлен")
        self.install_engine_btn.setEnabled(not ready)
        if ready and hasattr(self,"input_device") and self.input_device.count()==0:self.refresh_audio_devices()

    def install_engine(self):
        script=resource("scripts/install_rvc.ps1")
        if not script.exists():QMessageBox.critical(self,"Нет установщика",str(script));return
        self.install_engine_btn.setEnabled(False)
        self.worker=EngineWorker(script); self.worker.output.connect(self.engine_state.setText); self.worker.done.connect(self.engine_done); self.worker.start()

    def engine_done(self,ok,msg):
        self.install_engine_btn.setEnabled(True); self.engine_state.setText(msg); self.update_engine_state()
        if not ok:QMessageBox.warning(self,"Установка RVC",msg)

    def refresh_audio_devices(self):
        py=self.engine/"runtime"/"python.exe"
        if not py.exists():
            self.audio_hint.setText("Сначала установи RVC-движок, чтобы обнаружить аудиоустройства.")
            return
        code="import sounddevice as sd,json; print(json.dumps({'devices':[{'name':d['name'],'inputs':d['max_input_channels'],'outputs':d['max_output_channels'],'hostapi':sd.query_hostapis()[d['hostapi']]['name']} for d in sd.query_devices()]}))"
        try:
            result=subprocess.run([str(py),"-c",code],cwd=str(self.engine),capture_output=True,text=True,timeout=20)
            if result.returncode: raise RuntimeError(result.stderr[-1200:])
            payload=json.loads(result.stdout.strip().splitlines()[-1])
            self.input_device.clear(); self.output_device.clear()
            for d in payload["devices"]:
                label=f'{d["name"]}  [{d["hostapi"]}]'
                if d["inputs"]>0:self.input_device.addItem(label,d)
                if d["outputs"]>0:self.output_device.addItem(label,d)
            self.audio_hint.setText(f'Найдено входов: {self.input_device.count()}, выходов: {self.output_device.count()}. Для Discord выбирай виртуальный выход кабеля, а в Discord — его парный CABLE Output.')
        except Exception as e:
            self.audio_hint.setText("Не удалось получить список устройств: "+str(e))

    def apply_audio_devices(self):
        if not self.input_device.currentData() or not self.output_device.currentData():
            QMessageBox.warning(self,"Аудиоустройства","Обнови список и выбери микрофон и виртуальный выход."); return
        if self.engine_process and self.engine_process.poll() is None:
            QMessageBox.information(self,"Перезапусти RVC","Останови RVC перед применением новых устройств, затем запусти снова."); return
        cfg=self.engine/"configs"/"config.json"
        try:
            try:data=json.loads(cfg.read_text(encoding="utf-8"))
            except Exception:data={}
            inp=self.input_device.currentData(); out=self.output_device.currentData()
            if inp["hostapi"]!=out["hostapi"]:
                QMessageBox.warning(self,"Несовместимые устройства","Выбери микрофон и виртуальный выход одного аудиодрайвера (обычно Windows WASAPI)."); return
            data["sg_hostapi"]=out["hostapi"]; data["sg_input_device"]=inp["name"]; data["sg_output_device"]=out["name"]
            cfg.parent.mkdir(parents=True,exist_ok=True); cfg.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
            self.audio_hint.setText("Устройства сохранены. Запусти RVC — преобразованный звук пойдёт в выбранный виртуальный выход.")
            QMessageBox.information(self,"Готово","Маршрут аудио сохранён. В Discord выбери парное устройство виртуального кабеля как устройство ввода.")
        except Exception as e:QMessageBox.critical(self,"Не удалось сохранить устройства",str(e))

    def save_rvc_tuning(self):
        cfg=self.engine/"configs"/"config.json"
        try:
            try:data=json.loads(cfg.read_text(encoding="utf-8"))
            except Exception:data={}
            data.setdefault("sr_type","sr_model")
            data.setdefault("f0method","rmvpe")
            for key,(slider,scale) in self.tuning_sliders.items():
                data[key]=slider.value()/scale
                if scale==1:data[key]=slider.value()
            data["I_noise_reduce"]=self.input_denoise.isChecked()
            data["O_noise_reduce"]=self.output_denoise.isChecked()
            active=next((p for p in self.models.glob("*.pth") if p.name==self.active and p.is_file() and p.stat().st_size>0),None)
            # Always overwrite these fields. Never let a stale model path survive
            # when the user has not selected an installed voice.
            data["pth_path"]=str(active.resolve()) if active else ""
            indices=list(self.models.glob("*.index")) if active else []
            match=next((p for p in indices if active.stem.lower() in p.stem.lower() or p.stem.lower() in active.stem.lower()),None) if active else None
            data["index_path"]=str(match.resolve()) if match else ""
            cfg.parent.mkdir(parents=True,exist_ok=True)
            cfg.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
            self.audio_hint.setText("Настройки качества сохранены. Запусти или перезапусти RVC, чтобы применить их.")
        except Exception as e:
            QMessageBox.warning(self,"Настройки RVC","Не удалось сохранить параметры: "+str(e))

    def launch_engine(self):
        bat=self.engine/"go-realtime_gui.bat"
        if not bat.exists():QMessageBox.information(self,"RVC не установлен","Сначала установи движок.");return
        active=next((p for p in self.models.glob("*.pth") if p.name==self.active and p.is_file() and p.stat().st_size>0),None)
        if not active:
            # Clear obsolete paths such as a model selected in an older session.
            self.active=""
            self.save()
            self.save_rvc_tuning()
            self.panel_hint.setText("Голос не выбран. Выбери установленную модель во вкладке «Мои модели».")
            self.engine_status_dot.setStyleSheet("color:#e05b75;font-size:22px")
            QMessageBox.warning(self,"Не выбран голос","Сначала выбери существующую модель .pth во вкладке «Мои модели». Старый путь к модели очищен.")
            return
        self.sync_models()
        self.save_rvc_tuning()
        try:
            # Upstream RVC GUI checkboxes must load the saved denoiser preferences.
            upstream=self.engine/"realtime_gui.py"
            if upstream.exists():
                cfg=self.engine/"configs"/"config.json"
                try: saved=json.loads(cfg.read_text(encoding="utf-8"))
                except Exception: saved={}
                source=upstream.read_text(encoding="utf-8")
                source=source.replace('key="I_noise_reduce",\n                                    enable_events=True,','key="I_noise_reduce",\n                                    default='+str(bool(saved.get("I_noise_reduce",False)))+',\n                                    enable_events=True,')
                source=source.replace('key="O_noise_reduce",\n                                    enable_events=True,','key="O_noise_reduce",\n                                    default='+str(bool(saved.get("O_noise_reduce",False)))+',\n                                    enable_events=True,')
                upstream.write_text(source,encoding="utf-8")
            text=bat.read_text(encoding="utf-8-sig"); fixed=text.replace("runtime\\python.exe -I realtime_gui.py","runtime\\python.exe realtime_gui.py")
            if fixed!=text:bat.write_text(fixed,encoding="utf-8")
            # Patch upstream RVC into a hidden worker and auto-start its real-time stream.
            upstream=self.engine/"realtime_gui.py"
            source=upstream.read_text(encoding="utf-8")
            # Previous releases could leave a malformed runtime patch behind.
            # Restore the upstream script if it no longer parses, then patch once.
            try:
                compile(source,str(upstream),"exec")
            except SyntaxError:
                req=urllib.request.Request("https://raw.githubusercontent.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/main/realtime_gui.py",headers={"User-Agent":"RealVoiceAI/6.0"})
                with urllib.request.urlopen(req,timeout=30) as response:
                    source=response.read().decode("utf-8")
                compile(source,str(upstream),"exec")
            # Match the window construction independently of whitespace and
            # surrounding event-loop formatting; upstream has multiple variants.
            window_pattern = r'(?m)^([ \t]*)self\.window\s*=\s*sg\.Window\("RVC - GUI",\s*layout=layout,\s*finalize=True\)\s*$'
            def make_hidden_window(match):
                indent = match.group(1)
                return (indent + 'if os.environ.get("REALVOICEAI_HEADLESS") == "1":\n'
                        + indent + '    self.window = sg.Window("RVC - GUI", layout=layout, finalize=True, alpha_channel=0)\n'
                        + indent + '    self.window.hide()\n'
                        + indent + '    self.window.write_event_value("start_vc", None)\n'
                        + indent + 'else:\n'
                        + indent + '    self.window = sg.Window("RVC - GUI", layout=layout, finalize=True)')
            source, count = re.subn(window_pattern, make_hidden_window, source, count=1)
            if count != 1 and not ('REALVOICEAI_HEADLESS' in source and 'self.window.write_event_value("start_vc", None)' in source):
                raise RuntimeError("Не удалось распознать создание окна RVC. Установленный файл не изменён.")
            source=source.replace('''            if len(values["index_path"].strip()) == 0:
                sg.popup(i18n("请选择index文件"))
                return False''','''            if len(values["index_path"].strip()) == 0:
                values["index_path"] = ""''',1)
            # Validate the generated script before touching the installed engine.
            compile(source,str(upstream),"exec")
            upstream.write_text(source,encoding="utf-8")
            py=self.engine/"runtime"/"python.exe"
            if not py.exists(): raise RuntimeError("Не найден Python внутри RVC.")
            env=os.environ.copy()
            env["PATH"]=str(self.engine/"runtime")+os.pathsep+env.get("PATH","")
            env["REALVOICEAI_HEADLESS"]="1"
            self.engine_log=open(self.root/"rvc-runtime.log","a",encoding="utf-8",buffering=1)
            self.engine_process=subprocess.Popen(
                [str(py),str(upstream)],cwd=str(self.engine),env=env,
                stdin=subprocess.DEVNULL,stdout=self.engine_log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0)
            )
            self.panel_hint.setText("Запускаю скрытый RVC и аудиопоток…")
            self.engine_status_dot.setStyleSheet("color:#f0b44d;font-size:22px")
            self.embed_timer=QTimer(self); self.embed_timer.timeout.connect(self.check_engine_process); self.embed_timer.start(1000)
        except Exception as e:
            self.engine_status_dot.setStyleSheet("color:#e05b75;font-size:22px")
            QMessageBox.critical(self,"Ошибка запуска RVC",str(e))

    def check_engine_process(self):
        if not self.engine_process:
            self.embed_timer.stop(); return
        code=self.engine_process.poll()
        if code is None:
            self.engine_status_dot.setStyleSheet("color:#36d982;font-size:22px")
            self.panel_hint.setText("RVC работает в фоне. Аудиопоток запущен.")
            return
        self.embed_timer.stop()
        self.engine_status_dot.setStyleSheet("color:#e05b75;font-size:22px")
        self.panel_hint.setText(f"RVC остановился (код {code}). Журнал: {self.root / 'rvc-runtime.log'}")
        if getattr(self,"engine_log",None):
            self.engine_log.close(); self.engine_log=None

    def stop_engine(self):
        if self.engine_process and self.engine_process.poll() is None:
            subprocess.run(["taskkill","/PID",str(self.engine_process.pid),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if hasattr(self,"embed_timer"):self.embed_timer.stop()
        if getattr(self,"engine_log",None):
            try:self.engine_log.close()
            except Exception:pass
            self.engine_log=None
        if hasattr(self,"engine_status_dot"):self.engine_status_dot.setStyleSheet("color:#8888aa;font-size:22px")
        self.panel_hint.setText("Движок остановлен. Выбери голос и нажми «Запустить RVC».")

    def closeEvent(self,event):
        self.stop_engine(); super().closeEvent(event)

if __name__=="__main__":
    app=QApplication(sys.argv); w=MainWindow(); w.show(); sys.exit(app.exec())
