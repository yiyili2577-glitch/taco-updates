#define MyAppName "TACO 智慧採購助理"
#define MyAppVersion "6.6.0"
#define MyAppPublisher "TACO"
#define MyAppExeName "TACO.exe"

[Setup]
AppId={{4E1ED02D-71F3-4C46-A91A-D6C0A5776510}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\TACO
DefaultGroupName=TACO 智慧採購助理
OutputDir=Output
OutputBaseFilename=TACO_Setup_6.6.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\desktop_app\resources\taco.ico
UninstallDisplayIcon={app}\TACO.exe
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes

[Files]
Source: "..\dist\TACO\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{commonappdata}\TACO"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{commonappdata}\TACO\Data"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{commonappdata}\TACO\Backups"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{commonappdata}\TACO\AuditLogs"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{commonappdata}\TACO\Logs"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{commonappdata}\TACO\Config"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{commonappdata}\TACO\Exports"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{commonappdata}\TACO\Updates"; Permissions: users-modify; Flags: uninsneveruninstall

[Icons]
Name: "{autoprograms}\TACO 智慧採購助理"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\TACO 智慧採購助理"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "啟動 TACO 智慧採購助理"; Flags: nowait postinstall skipifsilent


[UninstallRun]
; 解除安裝前先確保 TACO / Updater 不再占用 Program Files 內的 EXE/DLL。
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM TACO.exe /T >nul 2>&1"; Flags: runhidden; RunOnceId: "KillTACO"
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM TACOUpdater.exe /T >nul 2>&1"; Flags: runhidden; RunOnceId: "KillTACOUpdater"

[UninstallDelete]
; Program Files\TACO 是專用程式目錄，解除安裝時必須完整移除。
Type: filesandordirs; Name: "{app}"
; 故意不刪除 {commonappdata}\TACO：解除安裝也保留公司資料、備份、稽核。
