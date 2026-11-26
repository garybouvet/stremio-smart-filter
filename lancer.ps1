# Lance Stremio sur l'interface modifiée, avec le moteur (démarré par moteur.ps1 s'il ne tourne pas déjà).
# Le moteur s'arrête avec Stremio seulement si c'est ce lanceur qui l'a démarré.
$root = $PSScriptRoot
$port = 11480
. (Join-Path $root 'chemins.ps1')

$stremio = Find-Stremio
if (-not $stremio) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("Stremio 5 est introuvable. Installe-le depuis stremio.com, puis relance ce raccourci.", 'Stremio Smart Filter') | Out-Null
    exit 1
}

$engine = & (Join-Path $root 'moteur.ps1')
& (Join-Path $root 'reprendre.ps1') | Out-Null

# Serveur de streaming relayé par le moteur (/ss/) : il refuse en CORS toute autre origine que Stremio.
$server = [uri]::EscapeDataString("http://127.0.0.1:$port/ss/")
Start-Process $stremio -ArgumentList "--webui-url=http://127.0.0.1:$port/#/?streamingServerUrl=$server" -Wait

if ($engine) {
    # uv lance python en processus enfant : on arrête tout l'arbre de CE processus, jamais un autre moteur.
    taskkill /PID $engine.Id /T /F | Out-Null
}
