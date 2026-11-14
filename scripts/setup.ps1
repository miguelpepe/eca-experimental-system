[CmdletBinding()]
param(
    [ValidateSet('Setup', 'Prepare', 'Start', 'Stop', 'Status', 'Logs', 'SyncRag')]
    [string]$Action = 'Setup',
    [ValidateSet('Backend', 'Frontend', 'Both')]
    [string]$Mode,
    [string]$BackendUrl,
    [string]$EngineRoot = $env:UE_ROOT
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$localRoot = Join-Path $projectRoot '.eca'
$installationPath = Join-Path $localRoot 'installation.json'
$envPath = Join-Path $localRoot 'docker.env'
$utf8 = New-Object Text.UTF8Encoding($false)

function Write-LocalText([string]$Path, [string]$Value) {
    [IO.File]::WriteAllText($Path, $Value, $utf8)
}

function New-Secret {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return -join ($bytes | ForEach-Object { $_.ToString('x2') })
}

function Initialize-LocalFiles {
    $configRoot = Join-Path $localRoot 'config'
    New-Item -ItemType Directory -Force -Path $configRoot | Out-Null
    foreach ($directory in @('RAG', 'voices', 'models')) {
        New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot $directory) | Out-Null
    }
    if (-not (Test-Path -LiteralPath (Join-Path $configRoot 'avatar.toml'))) {
        Copy-Item -LiteralPath (Join-Path $projectRoot 'config/avatar.example.toml') -Destination (Join-Path $configRoot 'avatar.toml')
    }
    if (-not (Test-Path -LiteralPath (Join-Path $configRoot 'persona.txt'))) {
        Copy-Item -LiteralPath (Join-Path $projectRoot 'avatar_backend/config/system_prompt.txt') -Destination (Join-Path $configRoot 'persona.txt')
    }
    if (-not (Test-Path -LiteralPath $envPath)) {
        $password = New-Secret
        $secret = New-Secret
        Write-LocalText $envPath @"
WEBUI_ADMIN_EMAIL=admin@eca.local
WEBUI_ADMIN_PASSWORD=$password
WEBUI_SECRET_KEY=$secret
WEBUI_PORT=3100
BACKEND_PORT=8000
BACKEND_BIND=127.0.0.1
"@
    }
}

function Get-LocalSetting([string]$Name, [string]$Default) {
    if (Test-Path -LiteralPath $envPath) {
        foreach ($line in [IO.File]::ReadAllLines($envPath)) {
            if ($line.StartsWith("$Name=")) { return $line.Substring($Name.Length + 1).Trim() }
        }
    }
    return $Default
}

function Set-IniValue([string]$Path, [string]$Section, [string]$Key, [string]$Value) {
    $text = if (Test-Path -LiteralPath $Path) { [IO.File]::ReadAllText($Path) } else { '' }
    $sectionPattern = '(?ms)^\[' + [regex]::Escape($Section) + '\][^\S\r\n]*\r?\n(?<body>.*?)(?=^\[|\z)'
    $match = [regex]::Match($text, $sectionPattern)
    if ($match.Success) {
        $body = $match.Groups['body'].Value
        $keyPattern = '(?m)^\s*' + [regex]::Escape($Key) + '\s*=.*$'
        if ([regex]::IsMatch($body, $keyPattern)) {
            $body = [regex]::Replace($body, $keyPattern, "$Key=$Value")
        } else { $body = $body.TrimEnd() + "`r`n$Key=$Value`r`n" }
        $replacement = "[$Section]`r`n$body"
        $text = $text.Substring(0, $match.Index) + $replacement + $text.Substring($match.Index + $match.Length)
    } else { $text = $text.TrimEnd() + "`r`n`r`n[$Section]`r`n$Key=$Value`r`n" }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    Write-LocalText $Path $text
}

function Set-FrontendEndpoint {
    $parsedUrl = $null
    if (-not [Uri]::TryCreate($BackendUrl, [UriKind]::Absolute, [ref]$parsedUrl) -or
        $parsedUrl.Scheme -notin @('http', 'https') -or $parsedUrl.UserInfo -or $parsedUrl.Query -or $parsedUrl.Fragment) {
        throw 'BackendUrl must be an HTTP(S) base address, e.g. http://192.168.1.20:8000.'
    }
    $profile = Join-Path $projectRoot 'unreal/Config/ECA.local.ini'
    Set-IniValue $profile '/Script/METAHUMAN_5_5.ECAAvatarSettings' 'BackendUrl' ('"' + $BackendUrl.TrimEnd('/') + '"')
    # legacy local scene reads the existing MetaHumanBackend setting
    $editorConfig = Join-Path $projectRoot 'unreal/Saved/Config/WindowsEditor/Engine.ini'
    Set-IniValue $editorConfig '/Script/METAHUMAN_5_5.MetaHumanBackend' 'BackendBaseUrl' ('"' + $BackendUrl.TrimEnd('/') + '"')
}

function Restore-FrontendAssets {
    & (Join-Path $PSScriptRoot 'assets.ps1') -ProjectRoot $projectRoot
}

function Assert-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Install Docker Desktop with the WSL 2 backend, then run Setup.bat again. See docs/docker.md.'
    }
    & docker info --format '{{.OSType}}' 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop in Linux-container mode with WSL 2, then run this command again.' }
    & docker compose version | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose is missing. Update Docker Desktop.' }
}

function Invoke-Compose([string[]]$Arguments) {
    & docker compose --project-directory $projectRoot --env-file $envPath -f (Join-Path $projectRoot 'compose.yaml') @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed. See the output above; use Status.bat or scripts/setup.ps1 -Action Logs." }
}

function Start-Backend {
    Assert-Docker
    Write-Host 'Checking GPU access before model downloads...'
    & docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu22.04 nvidia-smi --query-gpu=name --format=csv,noheader
    if ($LASTEXITCODE -ne 0) { throw 'Docker cannot access the NVIDIA GPU. Check WSL 2 and the NVIDIA driver. See docs/docker.md.' }
    Invoke-Compose @('build')
    Invoke-Compose @('run', '--rm', '--no-deps', 'backend', 'python', 'docker/check_gpu.py')
    Invoke-Compose @('up', '-d', '--wait', '--wait-timeout', '1800', 'ollama', 'openwebui')
    Invoke-Compose @('stop', 'backend')
    Invoke-Compose @('run', '--rm', '--no-deps', 'provision')
    Write-Host 'Starting speech models. First startup may take a while; progress: scripts/setup.ps1 -Action Logs'
    Invoke-Compose @('up', '-d', '--no-deps', '--wait', '--wait-timeout', '3600', 'backend')
    $port = Get-LocalSetting 'BACKEND_PORT' '8000'
    $webPort = Get-LocalSetting 'WEBUI_PORT' '3100'
    Write-Host "Backend ready: http://localhost:$port ; Open WebUI: http://localhost:$webPort"
    Write-Host 'Open WebUI login details: .eca/docker.env (local only).'
}

if (-not $Mode -and (Test-Path -LiteralPath $installationPath)) {
    $installation = Get-Content -LiteralPath $installationPath -Raw | ConvertFrom-Json
    $Mode = $installation.Mode
    if (-not $BackendUrl) { $BackendUrl = $installation.BackendUrl }
}
if (-not $Mode) {
    if ($Action -eq 'Setup') {
        Write-Host '1 - Backend (Docker, Ollama, Open WebUI, speech models)'
        Write-Host '2 - Frontend (Unreal project, existing backend)'
        Write-Host '3 - Both'
        $choice = Read-Host 'Choose installation [3]'
        $Mode = switch ($choice) { '1' { 'Backend' } '2' { 'Frontend' } '' { 'Both' } '3' { 'Both' } default { throw 'Choose 1, 2 or 3.' } }
    } elseif ($Action -in @('Stop', 'Status', 'Logs', 'SyncRag')) { $Mode = 'Backend' }
    else { throw 'Run Setup.bat first, or pass -Mode Backend, Frontend or Both.' }
}

if ($Action -in @('Setup', 'Prepare')) { Initialize-LocalFiles }
elseif (-not (Test-Path -LiteralPath $envPath) -and $Mode -ne 'Frontend') { throw 'Run Setup.bat first.' }

if ($Mode -in @('Frontend', 'Both') -and -not $BackendUrl) {
    $BackendUrl = 'http://127.0.0.1:' + (Get-LocalSetting 'BACKEND_PORT' '8000')
    if ($Action -eq 'Setup' -and $Mode -eq 'Frontend') {
        $answer = Read-Host "Backend address [$BackendUrl]"
        if ($answer) { $BackendUrl = $answer }
    }
}

switch ($Action) {
    'Prepare' { Write-Host 'Local configuration prepared; no containers or Unreal builds started.' }
    'Setup' {
        if ($Mode -in @('Frontend', 'Both')) {
            Restore-FrontendAssets
            & (Join-Path $PSScriptRoot 'unreal.ps1') -Action Check -EngineRoot $EngineRoot
        }
        if ($Mode -in @('Backend', 'Both')) { Start-Backend }
        if ($Mode -in @('Frontend', 'Both')) {
            Set-FrontendEndpoint
            & (Join-Path $PSScriptRoot 'unreal.ps1') -Action Setup -EngineRoot $EngineRoot
        }
    }
    'Start' {
        if ($Mode -in @('Backend', 'Both')) { Start-Backend }
        if ($Mode -in @('Frontend', 'Both')) {
            Set-FrontendEndpoint
            & (Join-Path $PSScriptRoot 'unreal.ps1') -Action Open -EngineRoot $EngineRoot
        }
    }
    'Stop' { Assert-Docker; Invoke-Compose @('stop') }
    'Status' { Assert-Docker; Invoke-Compose @('ps', '-a') }
    'Logs' { Assert-Docker; Invoke-Compose @('logs', '--follow', '--tail', '80', 'backend', 'provision', 'openwebui') }
    'SyncRag' {
        Assert-Docker
        Invoke-Compose @('up', '-d', '--wait', '--wait-timeout', '1800', 'ollama', 'openwebui')
        Invoke-Compose @('stop', 'backend')
        Invoke-Compose @('run', '--rm', '--no-deps', 'provision')
        Invoke-Compose @('up', '-d', '--no-deps', '--wait', '--wait-timeout', '3600', 'backend')
    }
}

if ($Action -in @('Setup', 'Prepare')) {
    Write-LocalText $installationPath (@{ Mode = $Mode; BackendUrl = $BackendUrl } | ConvertTo-Json)
    Write-Host 'Settings: .eca/config/persona.txt and .eca/config/avatar.toml ; documents: RAG/ ; recordings: voices/'
}
