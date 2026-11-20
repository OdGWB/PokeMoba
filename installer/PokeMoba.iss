; Installer di PokéMoba (Inno Setup 6).
; Lo crea la GitHub Action (.github/workflows/release.yml) dopo l'exe:
;   iscc /DAppVersion=3.0.N installer\PokeMoba.iss
; In locale: crea_installer.bat (serve Inno Setup 6 installato).
;
; Installazione PER UTENTE in %LOCALAPPDATA%\Programs\PokeMoba, senza permessi
; di amministratore: l'aggiornamento automatico (game/updater.py) sostituisce
; PokeMoba.exe nella sua cartella, quindi deve poterci scrivere (in Program Files
; non potrebbe). Profilo e impostazioni restano in %APPDATA%\PokeMoba e non si
; toccano disinstallando.

#ifndef AppVersion
  #define AppVersion "3.0 dev"
#endif
; Numero per le proprieta' del file: "3.0.N" -> "3.0.N.0" ("3.0 dev" -> "0.0.0.0").
#if Pos(" ", AppVersion) > 0
  #define FileVersion "0.0.0.0"
#else
  #define FileVersion AppVersion + ".0"
#endif

#define AppName "PokéMoba"
#define AppExe "PokeMoba.exe"

[Setup]
; AppId fisso: non cambiarlo, o Windows vedrebbe un'altra applicazione.
AppId={{0C9E9176-62A4-451F-85CD-829548767599}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=PokéMoba
AppPublisherURL=https://github.com/okgf2002-a11y/PokeMoba
AppSupportURL=https://github.com/okgf2002-a11y/PokeMoba/issues
AppUpdatesURL=https://github.com/okgf2002-a11y/PokeMoba/releases
VersionInfoVersion={#FileVersion}
DefaultDirName={localappdata}\Programs\PokeMoba
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=PokeMoba-Setup
SetupIconFile=..\assets\ui\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Se il gioco e' aperto, l'installer chiede di chiuderlo.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Resti di un aggiornamento automatico interrotto.
Type: files; Name: "{app}\{#AppExe}.new"
Type: files; Name: "{app}\{#AppExe}.part"
Type: files; Name: "{app}\{#AppExe}.old"
