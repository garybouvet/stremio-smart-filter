; Installeur Windows de Stremio Smart Filter. Fabriqué par installeur\construire.ps1, qui fournit les #define ci-dessous.
; Ne demande pas de droits administrateur : tout va dans %LOCALAPPDATA%\Programs\Stremio Smart Filter.
; Test sans téléchargement : StremioSmartFilter-Setup.exe /DONNEES="chemin\du\paquet.zip"
; Installation silencieuse : /VERYSILENT /TMDB=<clé> [/MDBLIST=<clé>] (sans /TMDB : moteur sans clé, pour les tests)

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\tmp\installeur\app"
#endif
#ifndef OutputDir
  #define OutputDir "..\tmp\installeur\sortie"
#endif
#ifndef DataUrl
  #error DataUrl manque : lancer installeur\construire.ps1
#endif
#define AppName "Stremio Smart Filter"
#define Repo "https://github.com/garybouvet/stremio-smart-filter"

[Setup]
AppId={{0565C26B-CD9E-4356-984D-E0CEC602FFCA}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName} (projet personnel, non affilié à Stremio)
AppPublisherURL={#Repo}
AppSupportURL={#Repo}/issues
DefaultDirName={localappdata}\Programs\{#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes
OutputDir={#OutputDir}
OutputBaseFilename=StremioSmartFilter-Setup-{#AppVersion}
UninstallDisplayName={#AppName}
SetupLogging=yes

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Messages]
fr.FinishedLabel=Stremio Smart Filter est installé. Lance-le avec le raccourci « Stremio Smart Filter » du Bureau.%n%nAu premier lancement, connecte-toi à ton compte Stremio dans la fenêtre qui s'ouvre : elle ne partage pas la session de l'application Stremio habituelle.

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
; conhost --headless : aucune fenêtre de console, même un instant (Windows Terminal ne sait pas cacher PowerShell).
Name: "{userdesktop}\{#AppName}"; Filename: "{sys}\conhost.exe"; \
  Parameters: "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""{app}\lancer.ps1"""; \
  WorkingDir: "{app}"; IconFilename: "{code:StremioExe}"; Comment: "Stremio avec les filtres et le choix des liens par langue"
Name: "{userprograms}\{#AppName}"; Filename: "{sys}\conhost.exe"; \
  Parameters: "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""{app}\lancer.ps1"""; \
  WorkingDir: "{app}"; IconFilename: "{code:StremioExe}"

[Run]
Filename: "{sys}\conhost.exe"; \
  Parameters: "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""{app}\lancer.ps1"""; \
  WorkingDir: "{app}"; Description: "Lancer Stremio Smart Filter maintenant"; Flags: postinstall nowait skipifsilent runhidden

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\arreter.ps1"""; RunOnceId: "arreter"; Flags: runhidden waituntilterminated

[UninstallDelete]
; Données, clés (.env) et caches : tout ce qui est dans le dossier de l'application, rien ailleurs.
Type: filesandordirs; Name: "{app}"

[Code]
const
  StremioKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{DD3870DA-AF3C-4C73-B010-72944AB610C6}_is1';
  KeyChars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-';

var
  KeysPage: TInputQueryWizardPage;
  DownloadPage: TDownloadWizardPage;
  Stremio, DataFile: String;

{ Stremio 5 : dossier habituel, sinon celui que son installeur a inscrit dans Windows. }
function FindStremio: String;
var
  Dir: String;
begin
  Result := ExpandConstant('{localappdata}\Programs\Stremio\stremio-shell-ng.exe');
  if FileExists(Result) then exit;
  if RegQueryStringValue(HKCU, StremioKey, 'InstallLocation', Dir) or RegQueryStringValue(HKLM, StremioKey, 'InstallLocation', Dir) then begin
    Result := AddBackslash(Dir) + 'stremio-shell-ng.exe';
    if FileExists(Result) then exit;
  end;
  Result := '';
end;

function StremioExe(Param: String): String;
begin
  Result := Stremio;
end;

function AppFile(Name: String): String;
begin
  Result := AddBackslash(WizardDirValue) + Name;
end;

{ Mise à jour d'une installation : clés et données déjà là, on ne les redemande pas. }
function HasKeys: Boolean;
begin
  Result := FileExists(AppFile('.env'));
end;

function HasData: Boolean;
begin
  Result := FileExists(AppFile('data\tmdb.db')) and FileExists(AppFile('data\index.db'));
end;

function InitializeSetup: Boolean;
var
  Code: Integer;
begin
  Stremio := FindStremio;
  Result := Stremio <> '';
  if not Result then
    if SuppressibleMsgBox('Stremio 5 n''est pas installé sur ce PC.' + #13#10 +
        'Stremio Smart Filter s''ajoute à Stremio : installe-le d''abord, puis relance cet installeur.' + #13#10#13#10 +
        'Ouvrir la page de téléchargement de Stremio ?', mbConfirmation, MB_YESNO, IDNO) = IDYES then
      ShellExec('open', 'https://www.stremio.com/downloads', '', '', SW_SHOWNORMAL, ewNoWait, Code);
end;

procedure OpenUrl(Url: String);
var
  Code: Integer;
begin
  ShellExec('open', Url, '', '', SW_SHOWNORMAL, ewNoWait, Code);
end;

procedure OpenTmdb(Sender: TObject);
begin
  OpenUrl('https://www.themoviedb.org/settings/api');
end;

procedure OpenMdblist(Sender: TObject);
begin
  OpenUrl('https://mdblist.com/preferences/');
end;

function AddLink(Top: Integer; Caption: String; OnClick: TNotifyEvent): Integer;
var
  Link: TNewStaticText;
begin
  Link := TNewStaticText.Create(KeysPage);
  Link.Parent := KeysPage.Surface;
  Link.Caption := Caption;
  Link.Top := Top;
  Link.Cursor := crHand;
  Link.Font.Color := clHighlight;
  Link.Font.Style := [fsUnderline];
  Link.OnClick := OnClick;
  Result := Top + Link.Height + ScaleY(6);
end;

procedure InitializeWizard;
var
  Top: Integer;
begin
  KeysPage := CreateInputQueryPage(wpWelcome, 'Tes clés',
    'Elles restent sur ce PC, dans le dossier de l''application.',
    'TMDB fournit les titres français, pays, langues, plateformes et bandes-annonces. ' +
    'MDBList ajoute les notes Rotten Tomatoes, Metacritic, Letterboxd et Trakt. Les deux sont gratuites.');
  KeysPage.Add('Clé API TMDB (obligatoire) :', False);
  KeysPage.Add('Clé API MDBList (facultative) :', False);
  KeysPage.Values[0] := ExpandConstant('{param:TMDB|}');
  KeysPage.Values[1] := ExpandConstant('{param:MDBLIST|}');
  Top := KeysPage.Edits[1].Top + KeysPage.Edits[1].Height + ScaleY(14);
  Top := AddLink(Top, 'Obtenir une clé TMDB : themoviedb.org > Paramètres > API', @OpenTmdb);
  AddLink(Top, 'Obtenir une clé MDBList : mdblist.com > Preferences > API key', @OpenMdblist);

  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), 'Téléchargement des données (environ 100 Mo)', nil);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = KeysPage.ID) and HasKeys;
end;

function ValidKey(Key: String): Boolean;
var
  I: Integer;
begin
  Result := Length(Key) > 0;
  for I := 1 to Length(Key) do
    if Pos(Key[I], KeyChars) = 0 then Result := False;
end;

{ Code HTTP de TMDB pour cette clé (clé v3 ou jeton v4, comme le moteur), 0 si TMDB est injoignable. }
function TmdbStatus(Key: String): Integer;
var
  Http: Variant;
begin
  try
    Http := CreateOleObject('WinHttp.WinHttpRequest.5.1');
    if Length(Key) > 40 then begin
      Http.Open('GET', 'https://api.themoviedb.org/3/configuration', False);
      Http.SetRequestHeader('Authorization', 'Bearer ' + Key);
    end else
      Http.Open('GET', 'https://api.themoviedb.org/3/configuration?api_key=' + Key, False);
    Http.Send('');
    Result := Http.Status;
  except
    Result := 0;
  end;
end;

function KeysOk: Boolean;
var
  Tmdb, Mdb: String;
  Status: Integer;
begin
  Tmdb := Trim(KeysPage.Values[0]);
  Mdb := Trim(KeysPage.Values[1]);
  Result := False;
  if not ValidKey(Tmdb) then
    MsgBox('Colle ta clé API TMDB : elle est obligatoire.', mbError, MB_OK)
  else if (Mdb <> '') and not ValidKey(Mdb) then
    MsgBox('La clé MDBList contient des caractères inattendus : vérifie-la.', mbError, MB_OK)
  else begin
    Status := TmdbStatus(Tmdb);
    if Status = 200 then
      Result := True
    else if Status = 0 then
      Result := MsgBox('TMDB ne répond pas : la clé n''a pas pu être vérifiée. Continuer quand même ?', mbConfirmation, MB_YESNO) = IDYES
    else
      MsgBox('TMDB refuse cette clé (code ' + IntToStr(Status) + '). Vérifie-la sur themoviedb.org.', mbError, MB_OK);
  end;
end;

function DataReady: Boolean;
begin
  Result := False;
  DataFile := ExpandConstant('{param:DONNEES|}');
  if DataFile = '' then begin
    DownloadPage.Clear;
    DownloadPage.Add('{#DataUrl}', '{#DataName}', '{#DataSha256}');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
        DataFile := ExpandConstant('{tmp}\{#DataName}');
        Result := True;
      except
        if not DownloadPage.AbortedByUser then
          SuppressibleMsgBox('Téléchargement des données impossible : ' + GetExceptionMessage, mbCriticalError, MB_OK, IDOK);
      end;
    finally
      DownloadPage.Hide;
    end;
  end else if not FileExists(DataFile) then
    MsgBox('Paquet de données introuvable : ' + DataFile, mbError, MB_OK)
  else if GetSHA256OfFile(DataFile) <> '{#DataSha256}' then
    MsgBox('Ce paquet de données ne correspond pas à cette version de l''installeur.', mbError, MB_OK)
  else
    Result := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = KeysPage.ID) and WizardSilent then
    Result := ((KeysPage.Values[0] = '') or ValidKey(KeysPage.Values[0])) and ((KeysPage.Values[1] = '') or ValidKey(KeysPage.Values[1]))
  else if CurPageID = KeysPage.ID then
    Result := KeysOk
  else if (CurPageID = wpReady) and not HasData then
    Result := DataReady;
end;

function PowerShell: String;
begin
  Result := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
end;

{ Mise à jour : le moteur de l'ancienne version tient des fichiers ouverts. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  Result := '';
  { Installation silencieuse (/VERYSILENT) : la page « Prêt » n'a pas été validée, les données restent à chercher. }
  if (DataFile = '') and not HasData and not DataReady then begin
    Result := 'Données indisponibles.';
    exit;
  end;
  if FileExists(AppFile('arreter.ps1')) then
    Exec(PowerShell, '-NoProfile -ExecutionPolicy Bypass -File "' + AppFile('arreter.ps1') + '"', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function RandomToken: String;
begin
  Result := Copy(GetSHA256OfString(GetDateTimeString('yyyymmddhhnnsszzz', #0, #0) + IntToStr(Random(2147483647)) +
    IntToStr(Random(2147483647)) + ExpandConstant('{tmp}')), 1, 32);
end;

procedure WriteSettings;
var
  Lines: String;
begin
  { Fichier écrit en ANSI par Inno Setup : rien que de l'ASCII, le moteur le lit en UTF-8. }
  Lines := '# Reglages de Stremio Smart Filter, ecrits par l''installeur. Ne pas partager : contient tes cles.' + #13#10 +
    'TMDB_API_KEY=' + Trim(KeysPage.Values[0]) + #13#10 +
    'MDBLIST_API_KEY=' + Trim(KeysPage.Values[1]) + #13#10 +
    'ADDON_TOKEN=' + RandomToken + #13#10 +
    'LANGUES_LANG=fr' + #13#10 +
    'HARVEST_PAUSE=2' + #13#10;
  if not SaveStringToFile(ExpandConstant('{app}\.env'), Lines, False) then
    RaiseException('Impossible d''écrire les réglages');
end;

procedure ShowProgress(const S: String; const Error, FirstLine: Boolean);
begin
  if Trim(S) <> '' then begin
    WizardForm.StatusLabel.Caption := S;
    Log('Préparation des données : ' + S);
  end;
end;

{ Déballe le paquet, télécharge IMDb, construit l'index : quelques minutes. }
procedure PrepareData;
var
  Code: Integer;
begin
  WizardForm.ProgressGauge.Style := npbstMarquee;
  WizardForm.StatusLabel.Caption := 'Préparation des données (quelques minutes)…';
  try
    ExecAndLogOutput(ExpandConstant('{app}\python\python.exe'), '-X utf8 -u -W ignore -m engine.setup_data "' + DataFile + '"',
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code, @ShowProgress);
  except
    Code := -1;
    Log(GetExceptionMessage);
  end;
  WizardForm.ProgressGauge.Style := npbstNormal;
  if Code <> 0 then
    SuppressibleMsgBox('La préparation des données a échoué (code ' + IntToStr(Code) + '). ' +
      'Vérifie ta connexion à Internet, puis relance l''installeur.', mbCriticalError, MB_OK, IDOK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    if not HasKeys then
      WriteSettings;
    if DataFile <> '' then
      PrepareData;
  end;
end;
