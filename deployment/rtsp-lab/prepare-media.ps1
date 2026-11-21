param(
    [string]$Destination = (Join-Path $PSScriptRoot '../../../Operix-Docker/rtsp-lab-media')
)

$ErrorActionPreference = 'Stop'
$manifestPath = Join-Path $PSScriptRoot 'approved-media.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
$folder = (New-Item -ItemType Directory -Path $Destination -Force).FullName

foreach ($clip in $manifest.clips) {
    if ($clip.filename -notmatch '^lab-cam-0[12]\.mp4$' -or
        $clip.sha256 -notmatch '^[a-f0-9]{64}$' -or
        $clip.download_url -notmatch '^https://huggingface\.co/datasets/Voxel51/Safe_and_Unsafe_Behaviours/resolve/[a-f0-9]{40}/data/[a-z0-9_]+\.mp4$') {
        throw 'Entrada de procedencia no admitida.'
    }
    $file = Join-Path $folder $clip.filename
    if (Test-Path -LiteralPath $file) {
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $clip.sha256) {
            throw "La copia existente de $($clip.filename) tiene otra huella."
        }
        continue
    }
    $staging = Join-Path $folder ([guid]::NewGuid().ToString('N') + '.part')
    try {
        Invoke-WebRequest -Uri $clip.download_url -OutFile $staging -TimeoutSec 90
        if ((Get-FileHash -LiteralPath $staging -Algorithm SHA256).Hash -ne $clip.sha256) {
            throw "La descarga de $($clip.filename) tiene otra huella."
        }
        Move-Item -LiteralPath $staging -Destination $file
    } finally {
        if (Test-Path -LiteralPath $staging) {
            Remove-Item -LiteralPath $staging
        }
    }
}

$publishedManifest = Join-Path $folder 'manifest.json'
if (Test-Path -LiteralPath $publishedManifest) {
    if ((Get-FileHash -LiteralPath $publishedManifest).Hash -ne (Get-FileHash -LiteralPath $manifestPath).Hash) {
        throw 'Ya existe un manifest diferente. Seleccione otro directorio.'
    }
} else {
    Copy-Item -LiteralPath $manifestPath -Destination $publishedManifest
}

Write-Output "Medios verificados en $folder"
