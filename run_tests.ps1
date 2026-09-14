# 仓库根 = 本脚本向上两级
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Push-Location $RepoRoot

try {
    uv run --locked python -u -m unittest discover -s tests -p "Test*.py" -v
    if ($LASTEXITCODE -ne 0) {
        throw "Test suite failed with exit code $LASTEXITCODE"
    }
}
catch {
    Write-Error $_
    exit 1
}
finally {
    Pop-Location
}
