$ErrorActionPreference = "SilentlyContinue"

$candidates = [System.Collections.Generic.List[string]]::new()

if ($env:PYTEST_RUNNER_BUILD_PYTHON) {
    $candidates.Add($env:PYTEST_RUNNER_BUILD_PYTHON)
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($line in (& py -0p 2>$null)) {
        if ($line -match '([A-Za-z]:\\.*?python(?:\.exe)?)\s*$') {
            $candidates.Add($Matches[1].Trim())
        }
    }
}

$defaultPython = Get-Command python -ErrorAction SilentlyContinue
if ($defaultPython -and $defaultPython.Source) {
    $candidates.Add($defaultPython.Source)
}

foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        continue
    }
    & $candidate -c "import struct,sys; sys.exit(0 if struct.calcsize('P') * 8 == 64 else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Output $candidate
        exit 0
    }
}

exit 1
