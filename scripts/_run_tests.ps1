$ErrorActionPreference = "Continue"
$tests = @('test_re_resolve_tickers.py', 'test_no_streamlit_imports.py', 'test_api_members.py', 'test_api_review.py', 'test_api_raw.py', 'test_api_tickers.py')
foreach ($f in $tests) {
    $log = "scripts\_test_$($f -replace '\.py$','').log"
    Remove-Item $log -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath ".\.venv\Scripts\python.exe" `
        -ArgumentList "-m", "pytest", "tests/$f", "-q", "--tb=line" `
        -WorkingDirectory "c:\Users\andre\Downloads\F9_CongressTrading" `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err" `
        -NoNewWindow -PassThru
    Write-Output "Started $f PID=$($p.Id)"
    $done = $false
    for ($i=0; $i -lt 20; $i++) {
        $alive = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
        if (-not $alive) { $done = $true; break }
        Start-Sleep -Seconds 3
    }
    $status = if ($done) { "DONE" } else { "TIMEOUT" }
    $out = ""
    if (Test-Path $log) { $out = (Get-Content $log -Tail 2 -ErrorAction SilentlyContinue) -join " | " }
    Write-Output ("{0} {1}: {2}" -f $f, $status, $out)
    if (-not $done) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
}
