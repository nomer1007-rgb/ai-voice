#define MyAppName "Real Voice AI"
#define MyAppVersion "4.0.0"
[Setup]
AppId={{D9E9A0D4-2E13-4E0C-9F21-4A1D45A7B440}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\Real Voice AI
DefaultGroupName=Real Voice AI
OutputDir=..\installer-output
OutputBaseFilename=RealVoiceAI-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
[Files]
Source: "..\dist\RealVoiceAI\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
[Icons]
Name: "{autoprograms}\Real Voice AI"; Filename: "{app}\RealVoiceAI.exe"
Name: "{autodesktop}\Real Voice AI"; Filename: "{app}\RealVoiceAI.exe"
