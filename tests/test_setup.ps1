$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot '../scripts/setup.ps1'
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
# load only the file-editing helpers; do not start containers or Unreal
foreach ($name in @('Write-LocalText', 'Set-IniValue')) {
    $function = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name }, $true)
    Invoke-Expression $function.Extent.Text
}
$utf8 = New-Object Text.UTF8Encoding($false)
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('eca-profile-' + [guid]::NewGuid().ToString('N') + '.ini')
try {
    Write-LocalText $fixture "[ECA.Local]`r`nStartupMap=/Game/Private`r`nGameMode=/Game/PrivateMode.PrivateMode_C`r`n`r`n[/Script/METAHUMAN_5_5.ECAAvatarSettings]`r`nMetaHumanClass=/Game/PrivateCharacter.PrivateCharacter_C`r`n"
    $section = '/Script/METAHUMAN_5_5.ECAAvatarSettings'
    Set-IniValue $fixture $section 'BackendUrl' '"http://192.168.1.20:8000"'
    Set-IniValue $fixture $section 'BackendUrl' '"http://192.168.1.21:9000"'
    $content = [IO.File]::ReadAllText($fixture)
    foreach ($required in @('StartupMap=/Game/Private', 'GameMode=/Game/PrivateMode.PrivateMode_C', 'MetaHumanClass=/Game/PrivateCharacter.PrivateCharacter_C', 'BackendUrl="http://192.168.1.21:9000"')) {
        if (-not $content.Contains($required)) { throw "Profile value was lost: $required" }
    }
    if (([regex]::Matches($content, 'BackendUrl=')).Count -ne 1) { throw 'Duplicate BackendUrl' }
    Write-Host 'PASS: setup script parses; private map, game mode and character survive endpoint updates.'
} finally {
    Remove-Item -LiteralPath $fixture -ErrorAction SilentlyContinue
}
