param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Virtual environment not found at .venv\\Scripts\\python.exe. Create it first with: py -m venv .venv"
}

if (-not $CommandArgs -or $CommandArgs.Count -eq 0) {
    $CommandArgs = @("ingest-all")
}

Push-Location $repoRoot
try {
    & $pythonExe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    & $pythonExe -m src.main @CommandArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}