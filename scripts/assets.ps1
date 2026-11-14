[CmdletBinding()]
param(
    [string]$ProjectRoot,
    [string]$ManifestPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $ProjectRoot) { $ProjectRoot = Join-Path $PSScriptRoot '..' }
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\', '/')
if (-not $ManifestPath) { $ManifestPath = Join-Path $ProjectRoot 'unreal/assets.json' }
$manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ($manifest.schema -ne 1 -or $manifest.version -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') {
    throw 'Unsupported Unreal asset manifest.'
}
$localRoot = Join-Path $ProjectRoot '.eca'
$cacheRoot = Join-Path $localRoot ('downloads/' + $manifest.version)
$statePath = Join-Path $localRoot 'assets-installed.json'
$managed = @{}
if (Test-Path -LiteralPath $statePath) {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    foreach ($property in $state.files.PSObject.Properties) { $managed[$property.Name] = $property.Value }
}
$updated = @{} + $managed
$knownPaths = @{}

function Get-AssetPath([string]$RelativePath) {
    if ($RelativePath.Contains('\') -or $RelativePath.Contains(':') -or
        $RelativePath -match '(^|/)\.{1,2}(/|$)' -or
        $RelativePath -notmatch '^unreal/Content/(ECA/|MetaHumans/(Common|Keiji|Ada)/)' -or
        ([IO.Path]::GetExtension($RelativePath) -notin @('.uasset', '.umap', '.dna', '.ubulk', '.uexp') -and
            $RelativePath -notin @('unreal/Content/MetaHumans/Ada/SourceAssets/MigrationInfo.json',
                'unreal/Content/MetaHumans/Ada/VersionInfo.txt', 'unreal/Content/MetaHumans/Common/VersionInfo.txt',
                'unreal/Content/MetaHumans/Keiji/VersionInfo.txt')) -or
        $RelativePath -in @('unreal/Content/MetaHumans/Common/Face/BP_AI_VoiceManager.uasset',
            'unreal/Content/MetaHumans/Common/Face/audio2face.uasset', 'unreal/Content/MetaHumans/Keiji/no_move.uasset')) {
        throw "Invalid public asset path: $RelativePath"
    }
    $target = [IO.Path]::GetFullPath((Join-Path $ProjectRoot $RelativePath))
    if (-not $target.StartsWith($ProjectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Asset path leaves the project folder.'
    }
    return $target
}

function Get-AssetHash([string]$Path) {
    if (-not [IO.File]::Exists($Path)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-LfsPointer([string]$Path) {
    if (-not [IO.File]::Exists($Path) -or (Get-Item -LiteralPath $Path).Length -gt 1024) { return $false }
    return [IO.File]::ReadAllText($Path).StartsWith('version https://git-lfs.github.com/spec/')
}

function Assert-NoLinks([string]$Path) {
    $current = $Path
    while ($current.Length -gt $ProjectRoot.Length) {
        if (Test-Path -LiteralPath $current) {
            if (([IO.File]::GetAttributes($current) -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Asset destination uses a link; install it manually: $Path"
            }
        }
        $current = Split-Path -Parent $current
    }
}

# validate the complete inventory before downloading or writing assets
foreach ($package in $manifest.packages) {
    if ($package.name -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*\.zip$' -or $package.sha256 -notmatch '^[a-f0-9]{64}$') {
        throw 'Invalid archive name or checksum.'
    }
    $uri = [Uri]$package.url
    if (-not $uri.IsAbsoluteUri -or ($uri.Scheme -ne 'https' -and -not ($uri.Scheme -eq 'http' -and $uri.IsLoopback))) {
        throw 'Asset downloads require HTTPS.'
    }
    foreach ($item in $package.files) {
        $null = Get-AssetPath $item.path
        if ($knownPaths.ContainsKey($item.path) -or $item.sha256 -notmatch '^[a-f0-9]{64}$' -or $item.size -lt 0) {
            throw 'Duplicate asset or invalid file checksum.'
        }
        $knownPaths[$item.path] = $true
    }
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$protectedCount = 0
foreach ($package in $manifest.packages) {
    $pending = @()
    $observed = @{}
    foreach ($item in $package.files) {
        $target = Get-AssetPath $item.path
        $hash = Get-AssetHash $target
        if ($hash -eq $item.sha256) { $updated[$item.path] = $hash; continue }
        if ($hash -and -not (Test-LfsPointer $target) -and
            (-not $managed.ContainsKey($item.path) -or $managed[$item.path] -ne $hash)) {
            Write-Warning "Keeping local asset changes: $($item.path)"
            $protectedCount++
            continue
        }
        $pending += $item
        $observed[$item.path] = $hash
    }
    if (-not $pending.Count) { continue }
    New-Item -ItemType Directory -Force -Path $cacheRoot | Out-Null
    $archivePath = Join-Path $cacheRoot $package.name
    if ((Get-AssetHash $archivePath) -ne $package.sha256) {
        if (Test-Path -LiteralPath $archivePath) { Remove-Item -LiteralPath $archivePath }
        $partial = $archivePath + '.partial'
        Write-Host ("Downloading {0} ({1:N0} MiB)..." -f $package.name, ($package.size / 1MB))
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $ProgressPreference = 'SilentlyContinue'
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            try {
                Invoke-WebRequest -UseBasicParsing -Uri $package.url -OutFile $partial -TimeoutSec 3600
                if ((Get-Item -LiteralPath $partial).Length -ne $package.size -or (Get-AssetHash $partial) -ne $package.sha256) {
                    throw "Archive checksum mismatch: $($package.name)"
                }
                Move-Item -LiteralPath $partial -Destination $archivePath -Force
                break
            } catch {
                if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial }
                if ($attempt -eq 3) { throw }
                Write-Warning "Download failed; retrying $($package.name)..."
            }
        }
    }
    Write-Host "Installing $($package.name)..."
    $archive = [IO.Compression.ZipFile]::OpenRead($archivePath)
    try {
        $expected = @{}
        foreach ($item in $package.files) { $expected[$item.path] = $true }
        $seen = @{}
        if ($archive.Entries.Count -ne @($package.files).Count) { throw 'Unexpected archive inventory.' }
        foreach ($entry in $archive.Entries) {
            if (-not $expected.ContainsKey($entry.FullName) -or $seen.ContainsKey($entry.FullName)) { throw 'Unexpected archive entry.' }
            $seen[$entry.FullName] = $true
        }
        foreach ($item in $pending) {
            $temporary = Join-Path $cacheRoot ([guid]::NewGuid().ToString('N') + '.tmp')
            try {
                $inputStream = $archive.GetEntry($item.path).Open()
                try {
                    $outputStream = [IO.File]::Create($temporary)
                    try { $inputStream.CopyTo($outputStream) } finally { $outputStream.Dispose() }
                } finally { $inputStream.Dispose() }
                if ((Get-Item -LiteralPath $temporary).Length -ne $item.size -or (Get-AssetHash $temporary) -ne $item.sha256) {
                    throw "Asset checksum mismatch: $($item.path)"
                }
                $target = Get-AssetPath $item.path
                if ((Get-AssetHash $target) -ne $observed[$item.path]) {
                    Write-Warning "Asset changed during installation; keeping it: $($item.path)"
                    $protectedCount++
                    continue
                }
                Assert-NoLinks $target
                New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
                [IO.File]::Copy($temporary, $target, $true)
                $updated[$item.path] = $item.sha256
            } finally {
                if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary }
            }
        }
    } finally { $archive.Dispose() }
}
New-Item -ItemType Directory -Force -Path $localRoot | Out-Null
$json = @{ version = $manifest.version; files = $updated } | ConvertTo-Json -Depth 5
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($statePath + '.tmp', $json, $utf8)
Move-Item -LiteralPath ($statePath + '.tmp') -Destination $statePath -Force
Write-Host "Unreal assets ready: $($manifest.version); local changes kept: $protectedCount."
