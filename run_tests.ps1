# Only files named Test*.py are picked up, matching .github/workflows/release-en.yml.
# Runs each test module in its own process. The ok framework installs a process-wide singleton,
# so a second init in the same process fails.
$env:PYTHONIOENCODING = 'UTF-8'
$failed = 0

Get-ChildItem -LiteralPath tests -Filter "Test*.py" | Sort-Object Name | ForEach-Object {
    $module = "tests.$($_.BaseName)"
    Write-Host "Running $module"
    python -u -m unittest $module -v
    if ($LASTEXITCODE -ne 0) { $failed = 1 }
}

if ($failed -ne 0) { Write-Host "FAILED"; exit 1 }
Write-Host "All tests passed"
