# Inicio nativo: solo el frontend recibe tráfico remoto; API/DB siguen locales.
[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$FrontendPort = 13000,
    [ValidateRange(1024, 65535)][int]$BackendPort = 18000,
    [string]$TailnetAddress,
    [string]$NodePath,
    [string]$PostgresBin,
    [string]$PostgresData
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$workspace = Split-Path $repo -Parent
$backend = Join-Path $repo 'backend'
$frontend = Join-Path $repo 'frontend'
$python = Join-Path $backend '.venv/Scripts/python.exe'
$engine = Join-Path $repo 'engine/.venv/Scripts/python.exe'
$processes = @()
$savedEnvironment = @{}
function Set-DemoEnvironment([string]$Name, [string]$Value) {
    if (-not $savedEnvironment.ContainsKey($Name)) {
        $savedEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process')
    }
    [Environment]::SetEnvironmentVariable($Name, $Value, 'Process')
}
function Assert-Exit([string]$Message) { if ($LASTEXITCODE -ne 0) { throw $Message } }
function Wait-Http([string]$Url, $Process) {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($Process.HasExited) { throw 'Un servicio terminó; consulte los logs de la demo.' }
        try {
            $response = Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch { Start-Sleep -Seconds 1 }
    }
    throw "El servicio no respondió: $Url"
}
try {
    if ($FrontendPort -eq $BackendPort) { throw 'Frontend y API necesitan puertos diferentes.' }
    foreach ($path in @($python, $engine, (Join-Path $backend '.env'))) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Falta backend/.env o un entorno Python; consulte los README nativos.' }
    }
    if (-not $TailnetAddress) {
        $tailscale = Get-Command tailscale.exe -ErrorAction SilentlyContinue
        $tailscalePath = if ($tailscale) { $tailscale.Source } else { "$env:ProgramFiles/Tailscale/tailscale.exe" }
        $tailnetResult = & $tailscalePath ip -4
        Assert-Exit 'Tailscale debe estar conectado.'
        $TailnetAddress = ($tailnetResult | Select-Object -First 1).Trim()
    }
    $address = [System.Net.IPAddress]::Parse($TailnetAddress)
    $octets = $address.GetAddressBytes()
    if ($octets.Length -ne 4 -or $octets[0] -ne 100 -or $octets[1] -lt 64 -or $octets[1] -gt 127) {
        throw 'Indique la IPv4 privada asignada por Tailscale (100.64.0.0/10).'
    }
    $localAddresses = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | ForEach-Object { $_.GetIPProperties().UnicastAddresses.Address.IPAddressToString }
    if ($TailnetAddress -notin $localAddresses) {
        throw 'La dirección Tailscale no está asignada a este PC.'
    }
    if (-not $NodePath) {
        $NodePath = Join-Path $workspace 'Operix-local-node/node-v24.2.0-win-x64/node.exe'
        if (-not (Test-Path -LiteralPath $NodePath)) { $NodePath = (Get-Command node.exe).Source }
    }
    if ((& $NodePath --version) -ne 'v24.2.0') { throw 'Se requiere Node v24.2.0; use -NodePath.' }
    foreach ($line in Get-Content -LiteralPath (Join-Path $backend '.env')) {
        if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            Set-DemoEnvironment $matches[1] $matches[2].Trim().Trim('"').Trim("'")
        }
    }
    if ($env:POSTGRES_HOST -notin @('localhost', '127.0.0.1', '::1')) { throw 'Esta demo requiere PostgreSQL local.' }
    # Comprobar antes de arrancar; no detener ni reemplazar servicios ajenos.
    foreach ($port in @($FrontendPort, $BackendPort)) {
        $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, $port)
        try { $probe.Start() } finally { $probe.Stop() }
    }
    $logs = Join-Path ([System.IO.Path]::GetTempPath()) ('operix-demo-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Path $logs | Out-Null
    $dbCheck = @"
import os,sys,psycopg
try:
    psycopg.connect(dbname=os.environ['POSTGRES_DB'],user=os.environ['POSTGRES_USER'],password=os.environ['POSTGRES_PASSWORD'],host=os.environ['POSTGRES_HOST'],port=os.environ['POSTGRES_PORT'],connect_timeout=3).close()
except psycopg.OperationalError:
    sys.exit(1)
"@
    & $python -B -c $dbCheck 2>$null
    if ($LASTEXITCODE -ne 0) {
        if (-not $PostgresBin) { $PostgresBin = Join-Path $workspace 'Operix-local-postgres/pgsql/pgsql/bin' }
        if (-not $PostgresData) { $PostgresData = Join-Path $workspace 'Operix-local-postgres/data' }
        $pgctl = Join-Path $PostgresBin 'pg_ctl.exe'
        if (-not (Test-Path -LiteralPath $pgctl)) { throw 'Inicie PostgreSQL local antes de ejecutar la demo.' }
        & $pgctl start -D $PostgresData -l (Join-Path $logs 'postgres.log') -w -t 20
        Assert-Exit 'No fue posible iniciar PostgreSQL local.'
        & $python -B -c $dbCheck
        Assert-Exit 'PostgreSQL no responde con la configuración de backend/.env.'
    }
    Set-DemoEnvironment 'OPERIX_ENGINE_PYTHON' $engine
    Set-DemoEnvironment 'EVENT_POST_ENABLED' '1'
    Set-DemoEnvironment 'OPERIX_EVENT_API_BASE_URL' "http://127.0.0.1:$BackendPort/api/v1"
    Set-DemoEnvironment 'DJANGO_ALLOWED_HOSTS' 'localhost,127.0.0.1'
    Set-DemoEnvironment 'CORS_ALLOWED_ORIGINS' "http://localhost:$FrontendPort,http://127.0.0.1:$FrontendPort,http://${TailnetAddress}:$FrontendPort"
    Set-DemoEnvironment 'DJANGO_DEBUG' '0'
    Set-DemoEnvironment 'NEXT_PUBLIC_DATA_SOURCE' 'api'
    Set-DemoEnvironment 'NEXT_PUBLIC_API_BASE_URL' '/api/v1'
    Set-DemoEnvironment 'OPERIX_API_PROXY_TARGET' "http://127.0.0.1:$BackendPort"
    Set-DemoEnvironment 'HOSTNAME' '0.0.0.0'
    Set-DemoEnvironment 'PORT' "$FrontendPort"
    & $engine -B -c "import os,hashlib,torch; from pathlib import Path; assert torch.cuda.is_available(), 'CUDA no disponible'; expected={'OPERIX_PERSON_WEIGHTS':'d5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95','OPERIX_FORKLIFT_WEIGHTS':'1465105ea80737ddc65d72e97d6dc24fc253995a98d6d4eea9b377fe3a8edce6'}; assert all(hashlib.sha256(Path(os.environ[k]).read_bytes()).hexdigest()==v for k,v in expected.items()), 'Revise pesos y hashes'; print('CUDA:',torch.cuda.get_device_name(0))"
    Assert-Exit 'La GPU o los pesos operativos no superaron la comprobación.'
    Push-Location $backend
    try { & $python -B manage.py check; Assert-Exit 'Django check falló.'; & $python -B manage.py migrate --check; Assert-Exit 'Existen migraciones pendientes; revise la instalación.' } finally { Pop-Location }
    Push-Location $frontend
    try {
        & $NodePath node_modules/next/dist/bin/next build --webpack
        Assert-Exit 'La compilación del frontend falló.'
        foreach ($asset in @('.next/static', 'public')) {
            $target = Join-Path '.next/standalone' $asset
            New-Item -ItemType Directory -Force -Path $target | Out-Null
            Copy-Item (Join-Path $asset '*') $target -Recurse -Force
        }
    } finally { Pop-Location }
    $api = Start-Process $python -ArgumentList '-B', 'manage.py', 'runserver', "127.0.0.1:$BackendPort", '--noreload' -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'backend.log') -RedirectStandardError (Join-Path $logs 'backend-error.log')
    $processes += $api
    Wait-Http "http://127.0.0.1:$BackendPort/api/v1/health/" $api
    $web = Start-Process $NodePath -ArgumentList 'server.js' -WorkingDirectory (Join-Path $frontend '.next/standalone') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'frontend.log') -RedirectStandardError (Join-Path $logs 'frontend-error.log')
    $processes += $web
    Wait-Http "http://127.0.0.1:$FrontendPort/api/v1/health/" $web
    Write-Host "Demo lista: http://${TailnetAddress}:$FrontendPort"
    Write-Host "Local: http://localhost:$FrontendPort | Logs: $logs"
    Write-Host 'Mantenga esta terminal abierta. Detenga los análisis antes de Ctrl+C.'
    while (-not $api.HasExited -and -not $web.HasExited) { Start-Sleep -Seconds 2 }
    throw 'Un servicio terminó; consulte los logs de la demo.'
} finally {
    foreach ($process in $processes) {
        if (-not $process.HasExited) { & taskkill.exe /PID $process.Id /T /F | Out-Null }
    }
    foreach ($key in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($key, $savedEnvironment[$key], 'Process') }
    # PostgreSQL puede pertenecer a otros procesos nativos: se conserva en ejecución.
}
