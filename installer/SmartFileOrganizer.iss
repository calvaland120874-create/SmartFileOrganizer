#define MyAppName "Smart File Organizer"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Smart File Organizer"
#define MyAppExeName "SmartFileOrganizer.exe"

[Setup]
AppId={{69CC7876-85A7-4EA8-8E2D-DA108CCF7B44}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Smart File Organizer
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\outputs
OutputBaseFilename=SmartFileOrganizerSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayName={#MyAppName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SmartFileOrganizer"; ValueData: """{app}\{#MyAppExeName}"" --background"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\Smart File Organizer"
