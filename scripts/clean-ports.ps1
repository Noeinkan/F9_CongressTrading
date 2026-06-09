<#
.SYNOPSIS
    Killa i processi che tengono occupate le porte 8000 (API) e 5173-5175 (Vite).
.DESCRIPTION
    Usa Get-NetTCPConnection per trovare i PID e termina solo quelli,
    con taskkill /T /F per chiudere l'intero process tree (incluso
    eventuali worker uvicorn). Non tocca altri processi Python/Node.
    Salta processi antenati del processo corrente (evita auto-kill della shell).
#>

$ErrorActionPreference = "SilentlyContinue"

$ports = @(8000, 5173, 5174, 5175)
$killed = 0
$myPid = $PID
$myTree = @($myPid)
# Cammina l'albero dei padri per un po' (best effort).
$cur = $myPid
for ($i = 0; $i -lt 8; $i++) {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$cur" -ErrorAction SilentlyContinue
    if (-not $p -or -not $p.ParentProcessId) { break }
    $cur = [int]$p.ParentProcessId
    $myTree += $cur
}

foreach ($port in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $pid = [int]$c.OwningProcess
        if (-not $pid -or $pid -eq 0) { continue }
        if ($myTree -contains $pid) {
            Write-Host ("  Skipping PID {0} on port {1} (antenato della shell corrente)" -f $pid, $port)
            continue
        }
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host ("  Killing PID {0,-6} ({1,-12}) on port {2}" -f $pid, $proc.ProcessName, $port)
            taskkill.exe /PID $pid /T /F 2>&1 | Out-Null
            $killed++
        }
    }
}

if ($killed -eq 0) {
    Write-Host "  Nessun processo trovato sulle porte 8000/5173-5175 (o tutti protetti)."
} else {
    Write-Host "  Terminati $killed processi."
}
