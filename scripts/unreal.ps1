[CmdletBinding()]
param(
    [ValidateSet('Check', 'Generate', 'Build', 'Setup', 'Verify', 'Open')]
    [string]$Action = 'Check',
    [string]$EngineRoot = $env:UE_ROOT,
    [string]$ProjectPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not $ProjectPath) {
    $ProjectPath = Join-Path $PSScriptRoot '..\unreal\METAHUMAN_5_5.uproject'
}
$ProjectPath = [IO.Path]::GetFullPath($ProjectPath)
if (-not (Test-Path -LiteralPath $ProjectPath -PathType Leaf)) {
    throw "Unreal project missing: $ProjectPath"
}
$projectDirectory = Split-Path -Parent $ProjectPath
$projectDefinition = Get-Content -LiteralPath $ProjectPath -Raw | ConvertFrom-Json
$engineVersion = $projectDefinition.EngineAssociation

# find the engine version recorded in the project
if (-not $EngineRoot) {
    $candidates = @()
    $engineRegistry = Get-ItemProperty -LiteralPath "HKLM:\SOFTWARE\EpicGames\Unreal Engine\$engineVersion" -ErrorAction SilentlyContinue
    if ($engineRegistry -and $engineRegistry.PSObject.Properties['InstalledDirectory']) {
        $candidates += $engineRegistry.InstalledDirectory
    }
    $buildRegistry = Get-ItemProperty -LiteralPath 'HKCU:\Software\Epic Games\Unreal Engine\Builds' -ErrorAction SilentlyContinue
    if ($buildRegistry -and $buildRegistry.PSObject.Properties[$engineVersion]) {
        $candidates += $buildRegistry.PSObject.Properties[$engineVersion].Value
    }
    $launcherManifest = Join-Path $env:ProgramData 'Epic\UnrealEngineLauncher\LauncherInstalled.dat'
    if (Test-Path -LiteralPath $launcherManifest) {
        $installations = (Get-Content -LiteralPath $launcherManifest -Raw | ConvertFrom-Json).InstallationList
        $candidates += @($installations | Where-Object { $_.AppName -eq "UE_$engineVersion" } | ForEach-Object { $_.InstallLocation })
    }
    $candidates += (Join-Path $env:ProgramFiles "Epic Games\UE_$engineVersion")
    $EngineRoot = $candidates | Where-Object {
        Test-Path -LiteralPath (Join-Path $_ 'Engine\Build\Build.version') -PathType Leaf
    } | Select-Object -First 1
}
if (-not $EngineRoot) {
    throw "Unreal Engine $engineVersion not found. Install it or pass -EngineRoot 'D:\Epic Games\UE_$engineVersion'."
}
$EngineRoot = [IO.Path]::GetFullPath($EngineRoot)
$versionPath = Join-Path $EngineRoot 'Engine\Build\Build.version'
$installedVersion = Get-Content -LiteralPath $versionPath -Raw | ConvertFrom-Json
$installedAssociation = "$($installedVersion.MajorVersion).$($installedVersion.MinorVersion)"
if ($engineVersion -match '^\d+\.\d+$' -and $installedAssociation -ne $engineVersion) {
    throw "This project requires UE $engineVersion; selected engine is $installedAssociation."
}

Write-Host "Project: $ProjectPath"
Write-Host "Engine:  $EngineRoot"

switch ($Action) {
    'Check' {
        if (-not (Test-Path -LiteralPath (Join-Path $projectDirectory 'Content\MetaHumans\Common\Face\Face_AnimBP.uasset'))) {
            throw 'The shared MetaHuman Face Anim Blueprint is missing. Restore the Content folder.'
        }
        $pluginNames = @(Get-ChildItem -LiteralPath (Join-Path $projectDirectory 'Plugins') -Filter '*.uplugin' -Recurse -File | ForEach-Object { $_.BaseName })
        foreach ($requiredPlugin in @('EasyWebsockets', 'RuntimeAudioImporter', 'NV_ACE_Reference', 'NvAudio2FaceClaire', 'NvAudio2FaceJames', 'NvAudio2FaceMark')) {
            if ($requiredPlugin -notin $pluginNames) {
                throw "Missing project plugin: $requiredPlugin. See docs/unreal.md."
            }
            Write-Host "Plugin:  $requiredPlugin"
        }
        Write-Host 'Project, engine version, shared face animation and project plugins found. This does not compile or run the project.'
    }
    'Generate' {
        $buildTool = Join-Path $EngineRoot 'Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe'
        & $buildTool '-projectfiles' "-project=$ProjectPath" '-game' '-engine' '-progress'
        if ($LASTEXITCODE -ne 0) { throw "Project generation failed (exit $LASTEXITCODE)." }
    }
    'Build' {
        $targets = @(Get-ChildItem -LiteralPath (Join-Path $projectDirectory 'Source') -Filter '*Editor.Target.cs' -File)
        if ($targets.Count -ne 1) { throw 'Expected one editor target in Source/.' }
        $targetName = $targets[0].Name -replace '\.Target\.cs$', ''
        $buildScript = Join-Path $EngineRoot 'Engine\Build\BatchFiles\Build.bat'
        & $buildScript $targetName 'Win64' 'Development' "-Project=$ProjectPath" '-WaitMutex'
        if ($LASTEXITCODE -ne 0) { throw "Unreal build failed (exit $LASTEXITCODE)." }
    }
    'Setup' {
        & (Join-Path $PSScriptRoot 'assets.ps1') -ProjectRoot (Split-Path -Parent $projectDirectory)
        & $PSCommandPath -Action Check -EngineRoot $EngineRoot -ProjectPath $ProjectPath
        & $PSCommandPath -Action Build -EngineRoot $EngineRoot -ProjectPath $ProjectPath
        $editor = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
        & $editor $ProjectPath '-run=ECASetup' '-unattended' '-nullrhi' '-nosound' '-nosplash' '-stdout' '-FullStdOutLogOutput'
        if ($LASTEXITCODE -ne 0) { throw "Unreal setup failed (exit $LASTEXITCODE)." }
        & $editor $ProjectPath '-run=ECATemplate' '-unattended' '-nullrhi' '-nosound' '-nosplash' '-stdout' '-FullStdOutLogOutput'
        if ($LASTEXITCODE -ne 0) { throw "Avatar template setup failed (exit $LASTEXITCODE)." }
    }
    'Verify' {
        & (Join-Path $PSScriptRoot 'assets.ps1') -ProjectRoot (Split-Path -Parent $projectDirectory)
        $editor = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
        $verificationScript = Join-Path $PSScriptRoot 'verify_unreal.py'
        & $editor $ProjectPath '-run=pythonscript' "-script=$verificationScript" '-unattended' '-nullrhi' '-nosound' '-nosplash' '-stdout' '-FullStdOutLogOutput'
        if ($LASTEXITCODE -ne 0) { throw "Unreal verification failed (exit $LASTEXITCODE)." }
    }
    'Open' {
        & (Join-Path $PSScriptRoot 'assets.ps1') -ProjectRoot (Split-Path -Parent $projectDirectory)
        $editor = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe'
        $editorArguments = @($ProjectPath)
        $localProfile = Join-Path $projectDirectory 'Config\ECA.local.ini'
        if (Test-Path -LiteralPath $localProfile) {
            $startup = Select-String -LiteralPath $localProfile -Pattern '^\s*StartupMap\s*=\s*(/Game/[\w/-]+)\s*$' | Select-Object -First 1
            if ($startup) { $editorArguments += $startup.Matches[0].Groups[1].Value }
        }
        & $editor @editorArguments
    }
}
