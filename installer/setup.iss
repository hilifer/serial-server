; Inno Setup Script for 耀嵘光储充管理系统
; Download Inno Setup: https://jrsoftware.org/isdl.php
; Open this file in Inno Setup Compiler and click Build

[Setup]
AppName=耀嵘光储充管理系统
AppVersion=1.0
AppPublisher=耀嵘
DefaultDirName={autopf}\YaoRong-SerialServer
DefaultGroupName=耀嵘光储充
OutputDir=output
OutputBaseFilename=耀嵘光储充管理系统_Setup
Compression=lzma2
SolidCompression=yes
SetupIconFile=
PrivilegesRequired=admin
UninstallDisplayName=耀嵘光储充管理系统

[Files]
; Project files
Source: "..\server.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\serial_manager.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\meter.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\meter_api.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\parking.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\state.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\deps.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\colors.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.yaml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\web\*"; DestDir: "{app}\web"; Flags: ignoreversion recursesubdirs
Source: "..\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs
Source: "..\tests\*"; DestDir: "{app}\tests"; Flags: ignoreversion recursesubdirs

; Installer scripts
Source: "launch.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "create_shortcut.vbs"; DestDir: "{app}\installer"; Flags: ignoreversion

[Icons]
Name: "{group}\耀嵘光储充管理系统"; Filename: "{app}\launch.bat"; WorkingDir: "{app}"
Name: "{group}\卸载"; Filename: "{uninstallexe}"
Name: "{autodesktop}\耀嵘光储充管理系统"; Filename: "{app}\launch.bat"; WorkingDir: "{app}"

[Run]
; Post-install: create venv and install deps
Filename: "cmd.exe"; Parameters: "/c cd /d ""{app}"" && python -m venv venv && venv\Scripts\pip.exe install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple"; StatusMsg: "安装 Python 依赖..."; Flags: runhidden waituntilterminated
; Ask to launch
Filename: "{app}\launch.bat"; Description: "立即启动耀嵘光储充管理系统"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\venv"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\.nuxt"
Type: files; Name: "{app}\serial_server.log"
