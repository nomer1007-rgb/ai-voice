#define MyAppName "AI Voice Changer RTX"
#define MyAppVersion "3.0.0"
#define MyAppPublisher "AI Voice Changer RTX"
#define MyAppExeName "AIVoiceChangerRTX.exe"

[Setup]
AppId={{A7F1A5B2-6F2A-4D5E-9C11-RTX507000003}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\AI Voice Changer RTX
DefaultGroupName={#MyAppName}
OutputDir=..\release
OutputBaseFilename=AI-Voice-Changer-RTX-Setup-v3
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=
DisableProgramGroupPage=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные задачи:"; Flags: unchecked

[Files]
Source: "..\dist\AIVoiceChangerRTX\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AI Voice Changer RTX"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\AI Voice Changer RTX"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить AI Voice Changer RTX"; Flags: postinstall nowait skipifsilent
