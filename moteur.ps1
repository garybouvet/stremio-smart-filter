# Démarre le moteur local en arrière-plan s'il ne tourne pas déjà (addons Filtres et Langues, interface modifiée).
# Renvoie le processus démarré, ou rien s'il tournait déjà.
$root = $PSScriptRoot
$port = 11480
. (Join-Path $root 'chemins.ps1')

if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { return }
# ffprobe est livré avec Stremio : il lit les pistes réelles des liens.
$stremio = Find-Stremio
if ($stremio -and -not $env:FFPROBE) { $env:FFPROBE = Join-Path (Split-Path $stremio) 'ffprobe.exe' }
$python = Get-PythonCommand
$arguments = @($python | Select-Object -Skip 1) + '-m', 'engine.server'
$engine = Start-Process $python[0] -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -PassThru
foreach ($i in 1..40) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { break }
    Start-Sleep -Milliseconds 250
}
$engine
