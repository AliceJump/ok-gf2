$ErrorActionPreference = "Stop"

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
