# Relance en fond les tâches de récupération arrêtées (veille, redémarrage). Elles reprennent là où elles en étaient.
# Une tâche finie se repose 7 jours (data\fini-<nom>.txt) : l'aspiration et tout TMDB se relisent en entier.
$root = $PSScriptRoot
$rest = 7
. (Join-Path $root 'chemins.ps1')
function Quote($text) { "'" + ($text -replace "'", "''") + "'" }  # chemin avec apostrophe (nom d'utilisateur)
$tasks = [ordered]@{
    tmdb     = 'engine.imdb_index --download --weekly', 'engine.tmdb --min-votes 0', 'engine.tmdb_all', 'engine.tmdb_links', 'engine.merge', 'engine.wikidata', 'engine.names'  # chacune a besoin des données de la précédente
    harvest  = , 'engine.harvest'
    mdblist  = , 'engine.mdblist'
    playable = , 'engine.playable'
}
$python = (@(Get-PythonCommand) | ForEach-Object { $_ } | ForEach-Object { Quote $_ }) -join ' '
# Seulement les tâches de CE dossier : une autre installation sur le même PC a les siennes.
$busy = (Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='powershell.exe'" | ForEach-Object { $_.CommandLine } |
    Where-Object { $_ -and $_.Contains($root) }) -join "`n"

foreach ($name in $tasks.Keys) {
    $done = Join-Path $root "data\fini-$name.txt"
    if ((Test-Path $done) -and (Get-Item $done).LastWriteTime -gt (Get-Date).AddDays(-$rest)) { continue }
    if ($tasks[$name] | Where-Object { $busy.Contains("-m $_") }) { continue }
    $steps = ($tasks[$name] | ForEach-Object { "& $python -u -W ignore -m $_; if (`$LASTEXITCODE -ne 0) { exit 1 }" }) -join '; '
    $command = "Set-Location $(Quote $root); $steps; Set-Content $(Quote $done) (Get-Date -Format s)"
    Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile', '-Command', $command
    "relancé : $name"
}
