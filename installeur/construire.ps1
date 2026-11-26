# Fabrique l'installeur Windows (StremioSmartFilter-Setup-<version>.exe) dans tmp\installeur\sortie.
# Usage : powershell -ExecutionPolicy Bypass -File installeur\construire.ps1 -Version 0.1.0 [-Donnees tmp\paquet\donnees-AAAA-MM-JJ.zip]
# Avant : interface compilée (stremio-web\build) et paquet de données (uv run python installeur\paquet.py).
# Ne publie rien : le paquet de données est à joindre à la Release « donnees-AAAA-MM-JJ » du dépôt public.
param([string]$Version = '0.1.0', [string]$Donnees)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$work = Join-Path $root 'tmp\installeur'
$app = Join-Path $work 'app'
$repo = 'https://github.com/garybouvet/stremio-smart-filter'
$pythonVersion = '3.13.15'  # même version que le Python de développement
$iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }

Step 'Paquet de données'
if (-not $Donnees) {
    $Donnees = Get-ChildItem (Join-Path $root 'tmp\paquet') -Filter 'donnees-*.zip' | Sort-Object Name | Select-Object -Last 1 -ExpandProperty FullName
}
if (-not $Donnees -or -not (Test-Path $Donnees)) { throw 'Paquet de données absent : lancer uv run python installeur\paquet.py' }
$dataName = Split-Path $Donnees -Leaf
$dataSha = (Get-FileHash $Donnees -Algorithm SHA256).Hash.ToLower()
$dataUrl = "$repo/releases/download/$([IO.Path]::GetFileNameWithoutExtension($dataName))/$dataName"
Write-Host "$dataName ($([math]::Round((Get-Item $Donnees).Length / 1MB)) Mo)"

Step 'Fichiers de l''application'
if (Test-Path $app) { Remove-Item $app -Recurse -Force }
New-Item -ItemType Directory -Force (Join-Path $app 'engine') | Out-Null
Get-ChildItem (Join-Path $root 'engine') -Filter '*.py' | Where-Object { $_.Name -notlike 'test_*' } |
    Copy-Item -Destination (Join-Path $app 'engine')
'chemins.ps1', 'lancer.ps1', 'moteur.ps1', 'reprendre.ps1' | ForEach-Object { Copy-Item (Join-Path $root $_) $app }
Copy-Item (Join-Path $PSScriptRoot 'arreter.ps1') $app

$build = Join-Path $root 'stremio-web\build'
if (-not (Test-Path (Join-Path $build 'index.html'))) { throw 'Interface non compilée : npx -y pnpm@11.8.0 run build dans stremio-web' }
robocopy $build (Join-Path $app 'stremio-web\build') /E /XF *.map /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw 'copie de l''interface' }

Step "Python $pythonVersion embarquable (python.org)"
$cache = Join-Path $work 'cache'
New-Item -ItemType Directory -Force $cache | Out-Null
$zip = Join-Path $cache "python-$pythonVersion-embed-amd64.zip"
if (-not (Test-Path $zip)) {
    Invoke-WebRequest "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-embed-amd64.zip" -OutFile $zip -UseBasicParsing
}
$python = Join-Path $app 'python'
Expand-Archive $zip $python -Force
$signature = Get-AuthenticodeSignature (Join-Path $python 'python.exe')
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
    throw 'python.exe n''est pas signé par la Python Software Foundation'
}
# Le dossier de l'application doit être dans le chemin de Python pour « -m engine.server ».
$pth = Get-ChildItem $python -Filter 'python*._pth' | Select-Object -First 1
Add-Content $pth.FullName '..'

Step 'Installeur'
$out = Join-Path $work 'sortie'
& $iscc /Q "/DAppVersion=$Version" "/DSourceDir=$app" "/DOutputDir=$out" "/DDataUrl=$dataUrl" "/DDataName=$dataName" "/DDataSha256=$dataSha" (Join-Path $PSScriptRoot 'stremio-smart-filter.iss')
if ($LASTEXITCODE -ne 0) { throw 'compilation de l''installeur' }
$exe = Join-Path $out "StremioSmartFilter-Setup-$Version.exe"
Write-Host "$exe ($([math]::Round((Get-Item $exe).Length / 1MB)) Mo)" -ForegroundColor Green
Write-Host "SHA-256 : $((Get-FileHash $exe -Algorithm SHA256).Hash.ToLower())"
Write-Host "Données attendues à : $dataUrl"
