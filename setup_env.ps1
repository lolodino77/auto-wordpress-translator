# Crée (ou met à jour) l'environnement conda "auto-wordpress-translator" et installe tout le nécessaire.
# Usage : powershell -ExecutionPolicy Bypass -File setup_env.ps1
$ErrorActionPreference = "Stop"
$EnvName = "auto-wordpress-translator"
Set-Location $PSScriptRoot

# Localise conda (PATH, sinon emplacements habituels d'Anaconda/Miniconda)
$conda = $env:CONDA_EXE
if (-not $conda) { $conda = (Get-Command conda.exe -ErrorAction SilentlyContinue).Source }
if (-not $conda) {
    foreach ($root in "$env:USERPROFILE\anaconda3", "$env:USERPROFILE\miniconda3", "$env:LOCALAPPDATA\anaconda3", "$env:LOCALAPPDATA\miniconda3", "C:\ProgramData\anaconda3", "C:\ProgramData\miniconda3") {
        if (Test-Path "$root\Scripts\conda.exe") { $conda = "$root\Scripts\conda.exe"; break }
    }
}
if (-not $conda) { throw "conda introuvable : installez Anaconda/Miniconda ou ajoutez-le au PATH." }
Write-Host "conda : $conda"

# Utilise le magasin de certificats Windows (utile derrière un antivirus/proxy qui inspecte HTTPS),
# pour cette exécution uniquement : aucune configuration conda globale n'est modifiée.
$env:CONDA_SSL_VERIFY = "truststore"
$env:NODE_OPTIONS = "--use-system-ca"

$exists = (& $conda env list) -match "^\s*$EnvName\s"
if ($exists) {
    Write-Host "L'environnement existe déjà : mise à jour."
    & $conda env update -n $EnvName -f environment.yml --prune
} else {
    Write-Host "Création de l'environnement $EnvName."
    & $conda env create -f environment.yml
}
if ($LASTEXITCODE -ne 0) { throw "Échec de conda env create/update" }

# Navigateur utilisé par Playwright (Chromium dédié, séparé de votre Chrome)
& $conda run -n $EnvName --no-capture-output python -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "Échec de l'installation de Chromium pour Playwright" }

Write-Host "`nEnvironnement prêt. Pour l'utiliser :  conda activate $EnvName"
