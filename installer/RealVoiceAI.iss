#define MyAppName "Real Voice AI"
#define MyAppVersion "4.1.0"
#define MyAppPublisher "Real Voice AI"
#define MyAppExeName "RealVoiceAI.exe"

[Setup]
AppId={{D9E9A0D4-2E13-4E0C-9F21-4A1D45A7B440}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Real Voice AI
DefaultGroupName={#MyAppName}
OutputDir=..\installer-output
OutputBaseFilename=RealVoiceAI-Setup-v4.1
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
DisableProgramGroupPage=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные задачи:"; Flags: unchecked

[Files]
Source: "..\dist\RealVoiceAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Real Voice AI"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Real Voice AI"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить Real Voice AI"; Flags: postinstall nowait skipifsilent
