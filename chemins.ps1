# Où sont Python et Stremio : sur le PC de développement (uv) ou sur un PC installé par l'installeur (python\ fourni).
# S'utilise avec « . (Join-Path $PSScriptRoot 'chemins.ps1') ».

# Commande Python : le Python fourni par l'installeur s'il est là, sinon uv.
function Get-PythonCommand {
    $embedded = Join-Path $PSScriptRoot 'python\python.exe'
    if (Test-Path $embedded) { return , @($embedded) }
    return , @('uv', 'run', 'python')
}

# stremio-shell-ng.exe (Stremio 5) : dossier habituel, sinon celui que son installation a inscrit dans Windows.
function Find-Stremio {
    $dirs = @("$env:LOCALAPPDATA\Programs\Stremio")
    $keys = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    $dirs += Get-ItemProperty $keys -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like 'Stremio*' -and $_.InstallLocation } |
        ForEach-Object { $_.InstallLocation }
    foreach ($dir in $dirs) {
        $exe = Join-Path $dir 'stremio-shell-ng.exe'
        if (Test-Path $exe) { return $exe }
    }
    return $null
}
