#define AppName "FitterCalcs"
#define AppVersion "2.32"
#define AppPublisher "macski777"
#define AppURL "https://github.com/macski777/fittercalcs"

[Setup]
AppId={{7C3E9A12-4B8F-4E2A-9D71-A91B4C0DE529}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
DefaultDirName={localappdata}\FitterCalcs
DefaultGroupName=FitterCalcs
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=FitterCalcs-{#AppVersion}-Setup
SetupIconFile=fittercalcs.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\FitterCalcs.exe
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Extra shortcuts:"

[Files]
Source: "dist\FitterCalcs\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\FitterCalcs"; Filename: "{app}\FitterCalcs.exe"
Name: "{autodesktop}\FitterCalcs"; Filename: "{app}\FitterCalcs.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FitterCalcs.exe"; Description: "Open FitterCalcs"; Flags: nowait postinstall skipifsilent
