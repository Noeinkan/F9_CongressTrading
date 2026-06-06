param(
    [string]$VpsUser = "root",
    [string]$VpsHost = "77.42.70.26",
    [string]$VpsRepoDir = "/opt/F9_CongressTrading",
    [string]$Branch = "main",
    [string]$Message = ""
)

# deploy_local.ps1 - One-shot deploy from this Windows PC.
# 1. Commit pending changes (prompts for a message, or use -Message).
# 2. Push the current branch to origin.
# 3. Run deploy/deploy.sh on the VPS over SSH.
#
# Usage (from repo root):
#   .\deploy_local.ps1
#   .\deploy_local.ps1 -Message "fix: foo bar"
#   .\deploy_local.ps1 -VpsUser root -VpsHost 77.42.70.26 -VpsRepoDir /opt/F9_CongressTrading
#
# Requires: git + OpenSSH on PATH (Windows 10+ ships both).

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $repoRoot
try {
    if (-not (Test-Path ".git")) {
        throw "Not a git repo at $repoRoot."
    }

    $current = (git rev-parse --abbrev-ref HEAD).Trim()
    if ($current -ne $Branch) {
        throw "Wrong branch '$current'. Check out $Branch before deploying."
    }

    $dirty = ((git status --porcelain) | Out-String).Trim() -ne ""
    if ($dirty) {
        if (-not $Message) {
            $Message = Read-Host "Commit message (leave blank to abort)"
        }
        if (-not $Message) {
            throw "Aborted: empty commit message."
        }
        git add -A
        git commit -m $Message
        if ($LASTEXITCODE -ne 0) { throw "git commit failed." }
    }
    else {
        Write-Host "Working tree clean." -ForegroundColor Green
    }

    Write-Host "Pushing $Branch to origin..." -ForegroundColor Cyan
    git push origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git push failed." }

    $scriptPath = Join-Path $repoRoot "deploy\deploy.sh"
    if (-not (Test-Path $scriptPath)) {
        throw "Missing $scriptPath"
    }

    $remoteCmd = "REPO_DIR=$VpsRepoDir bash -s"
    Write-Host "Deploying to $VpsUser@$VpsHost ($VpsRepoDir)..." -ForegroundColor Cyan
    Get-Content $scriptPath -Raw | ssh "$VpsUser@$VpsHost" $remoteCmd
    if ($LASTEXITCODE -ne 0) { throw "Remote deploy failed." }

    Write-Host "Deploy complete." -ForegroundColor Green
}
finally {
    Pop-Location
}
