; DGHub SDK Packer — Inno Setup 安装脚本（每用户安装）
; 由 build.py 调用：ISCC installer.iss /DMyVersion=<x.y.z>
; 打包 onedir（bin\dghub-sdk-packer\）为安装器，装到 LocalAppData。
; 纯 GUI 工具（CLI 已移除）：仅 dgpacker-gui.exe，无需 PATH 注册。

#ifndef MyVersion
  #define MyVersion "0.0.0"
#endif

#define MyAppName "DGHub SDK Packer"
#define MyGuiExe "dgpacker-gui.exe"

[Setup]
AppId={{A7C3E1F2-5B9D-4E8A-9C2F-1D3B6E4A8F70}
AppName={#MyAppName}
AppVersion={#MyVersion}
AppPublisher=DGHub
DefaultDirName={localappdata}\dghub-sdk-packer
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=dghub-sdk-packer-setup
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyGuiExe}
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; onedir 全部内容（dgpacker-gui.exe + 共享 _internal/）
Source: "bin\dghub-sdk-packer\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyGuiExe}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyGuiExe}"; Tasks: desktopicon
