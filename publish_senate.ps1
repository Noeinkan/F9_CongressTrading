param(
    [string]$VpsUser = "root",
    [string]$VpsHost = "77.42.70.26",
    [string]$VpsRepoDir = "/opt/F9_CongressTrading",
    [switch]$SkipScrape,
    [string]$Since = "",
    [int]$Limit = 0
)

# publish_senate.ps1 - Scrape the Senate locally, then publish to the prod VPS.
#
# WHY THIS EXISTS: efdsearch.senate.gov sits behind Akamai, which blocks the
# datacenter IP of the VPS. So Senate scraping runs HERE (residential IP) via
# curl_cffi, and the resulting raw files are shipped to the VPS, where prod's own
# `ingest-senate` parses them into the prod DB (same model as House/OGE, which
# build on-box). data/raw is gitignored, so this cannot ride `git pull`.
#
# Steps:
#   1. (unless -SkipScrape) run `download-senate` + `ingest-senate` locally to verify.
#   2. scp data/raw/senate/*.{html,pdf} to the VPS.
#   3. Run `ingest-senate` + CSV exports on the VPS over SSH. The API's mtime-keyed
#      cache reloads on the next request; no service restart needed.
#
# Usage (from repo root):
#   .\publish_senate.ps1                       # scrape + ingest + publish
#   .\publish_senate.ps1 -Since 2026 -Limit 50 # scrape a bounded slice
#   .\publish_senate.ps1 -SkipScrape           # publish already-scraped files
#
# Requires: git + OpenSSH (scp/ssh) on PATH (Windows 10+ ships both).

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $repoRoot
try {
    $py = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { throw "Missing venv python at $py" }
    $senateDir = Join-Path $repoRoot "data\raw\senate"

    if (-not $SkipScrape) {
        $dlArgs = @("-m", "src.main", "download-senate")
        if ($Since) { $dlArgs += @("--since", $Since) }
        if ($Limit -gt 0) { $dlArgs += @("--limit", "$Limit") }
        Write-Host "Scraping Senate eFD locally..." -ForegroundColor Cyan
        & $py @dlArgs
        if ($LASTEXITCODE -ne 0) { throw "download-senate failed." }

        Write-Host "Ingesting locally (verification)..." -ForegroundColor Cyan
        & $py -m src.main ingest-senate
        if ($LASTEXITCODE -ne 0) { throw "local ingest-senate failed." }
    }

    if (-not (Test-Path $senateDir)) { throw "No $senateDir to publish." }
    $files = Get-ChildItem -Path $senateDir -File -Recurse |
        Where-Object { $_.Extension -in ".html", ".pdf" }
    if (-not $files) { throw "No .html/.pdf files under $senateDir to publish." }
    Write-Host "Publishing $($files.Count) Senate files to ${VpsUser}@${VpsHost}..." -ForegroundColor Cyan

    $remoteSenate = "$VpsRepoDir/data/raw/senate"
    ssh "$VpsUser@$VpsHost" "mkdir -p '$remoteSenate'"
    if ($LASTEXITCODE -ne 0) { throw "Remote mkdir failed." }

    # scp the explicit file list (PowerShell expands the array to separate args) so
    # the files land directly in the remote senate/ dir with no directory nesting.
    scp @($files.FullName) "${VpsUser}@${VpsHost}:$remoteSenate/"
    if ($LASTEXITCODE -ne 0) { throw "scp failed." }

    Write-Host "Ingesting on prod + refreshing exports..." -ForegroundColor Cyan
    $venvPy = "./.venv/bin/python"
    $remoteCmd = "cd '$VpsRepoDir' && " +
        "$venvPy -m src.main ingest-senate && " +
        "$venvPy -m src.main export-csv && " +
        "$venvPy -m src.main export-fd-csv && " +
        "$venvPy -m src.main export-review-csv"
    ssh "$VpsUser@$VpsHost" $remoteCmd
    if ($LASTEXITCODE -ne 0) { throw "Remote ingest/export failed." }

    Write-Host "Senate data published. The live dashboard reloads on next request (mtime cache)." -ForegroundColor Green
}
finally {
    Pop-Location
}
