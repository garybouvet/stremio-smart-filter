# Arrête le moteur et les tâches de fond de CETTE installation : les processus du Python de son dossier python\.
# Lancé par l'installeur avant une mise à jour et par la désinstallation. Ne touche à aucun autre Python.
$python = Join-Path $PSScriptRoot 'python\'
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($python, [StringComparison]::OrdinalIgnoreCase) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
