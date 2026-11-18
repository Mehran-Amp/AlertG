<#
  start_bourse.ps1 - keeps the Iranian Bourse gateway and its SSH reverse tunnel alive (IB-12b).

  Run on the PC with the Iranian IP (no VPN):   powershell -ExecutionPolicy Bypass -File .\start_bourse.ps1
  First run safely:                              ... -File .\start_bourse.ps1 -Check     (starts nothing)

  It
    * allows exactly ONE copy of itself,
    * starts the gateway (key passed through the environment, never printed) and the tunnel,
    * restarts either one when it dies, waiting longer after each failure (max $MaxBackoff s),
    * restarts the gateway when its /health fails $HealthFailures times in a row,
    * writes a log with times to $LogDir.
  Stop it with Ctrl+C: it stops the gateway and the tunnel it started.
#>
param([switch]$Check)

$ErrorActionPreference = 'Stop'
$cfgPath = Join-Path $PSScriptRoot 'bourse.config.ps1'
if (-not (Test-Path $cfgPath)) {
    Write-Host "Missing $cfgPath. Copy bourse.config.example.ps1 to bourse.config.ps1 and fill it in." -ForegroundColor Red
    exit 2
}
. $cfgPath

function Log([string]$msg) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Host $line
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
    $file = Join-Path $LogDir 'start_bourse.log'
    if ((Test-Path $file) -and ((Get-Item $file).Length -gt 2MB)) { Move-Item $file "$file.old" -Force }
    Add-Content -Path $file -Value $line -Encoding UTF8
}

# ---- validate configuration (no secrets printed) ----
$problems = @()
if (-not (Test-Path $GatewayDir))  { $problems += "GatewayDir not found: $GatewayDir" }
if (-not (Test-Path $ApiKeyFile))  { $problems += "ApiKeyFile not found: $ApiKeyFile" }
if (-not (Test-Path $SshKeyFile))  { $problems += "SshKeyFile not found: $SshKeyFile" }
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { $problems += 'ssh not found in PATH' }
if (-not (Get-Command $GatewayExe -ErrorAction SilentlyContinue)) { $problems += "GatewayExe not found: $GatewayExe" }
if ($SshHost -like '*example.com') { $problems += 'SshHost is still the example value' }

if ($Check) {
    Write-Host "Gateway : $GatewayExe $GatewayArgs   (in $GatewayDir, port $GatewayPort)"
    Write-Host "Tunnel  : ssh -N -R 127.0.0.1:${RemotePort}:127.0.0.1:${GatewayPort} $SshUser@$SshHost -p $SshPort -i <key file>"
    Write-Host "Logs    : $LogDir"
    if ($problems.Count -eq 0) { Write-Host 'Check OK: nothing was started.' -ForegroundColor Green; exit 0 }
    $problems | ForEach-Object { Write-Host "PROBLEM: $_" -ForegroundColor Red }
    exit 1
}
if ($problems.Count -gt 0) { $problems | ForEach-Object { Write-Host "PROBLEM: $_" -ForegroundColor Red }; exit 1 }

# ---- exactly one copy ----
$created = $false
$mutex = New-Object System.Threading.Mutex($true, 'Global\AlertG_Bourse_Supervisor', [ref]$created)
if (-not $created) { Write-Host 'Another start_bourse.ps1 is already running. Exiting.' -ForegroundColor Yellow; exit 3 }

$key = (Get-Content -Raw $ApiKeyFile).Trim()
if (-not $key) { Write-Host 'ApiKeyFile is empty.' -ForegroundColor Red; exit 1 }
$env:TSETMC_API_KEY = $key            # inherited by the gateway process only

$script:gw = $null; $script:tn = $null
$script:gwFails = 0; $script:gwDelay = 5; $script:tnDelay = 5
$script:gwNext = Get-Date; $script:tnNext = Get-Date

function Stop-Proc($p) {
    if ($p -and -not $p.HasExited) { try { Stop-Process -Id $p.Id -Force } catch { } }
}

function Start-Gateway {
    Log "starting gateway: $GatewayExe $GatewayArgs"
    $out = Join-Path $LogDir 'gateway.out.log'; $err = Join-Path $LogDir 'gateway.err.log'
    $script:gw = Start-Process -FilePath $GatewayExe -ArgumentList $GatewayArgs -WorkingDirectory $GatewayDir `
        -PassThru -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err
    $script:gwFails = 0
}

function Start-Tunnel {
    Log "starting tunnel to $SshUser@$SshHost (remote port $RemotePort)"
    $sshArgs = @('-N', '-T', '-p', "$SshPort", '-i', ('"' + $SshKeyFile + '"'),
        '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
        '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
        '-o', 'StrictHostKeyChecking=accept-new',
        '-R', "127.0.0.1:${RemotePort}:127.0.0.1:${GatewayPort}", "$SshUser@$SshHost")
    $err = Join-Path $LogDir 'tunnel.err.log'
    $script:tn = Start-Process -FilePath 'ssh' -ArgumentList $sshArgs -PassThru -WindowStyle Hidden -RedirectStandardError $err
}

# 'ok' (answers), 'warming' (503: gateway up but data not loaded yet), or 'down'
function Test-Gateway {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri "http://127.0.0.1:$GatewayPort/health" -Headers @{ 'X-API-Key' = $key }
        if ($r.StatusCode -eq 200) { return 'ok' }
        return 'down'
    } catch {
        $resp = $_.Exception.Response
        if ($resp -and [int]$resp.StatusCode -eq 503) { return 'warming' }
        return 'down'
    }
}

function Next-Delay([int]$d) { return [Math]::Min($MaxBackoff, $d * 2) }

Log 'supervisor started (Ctrl+C to stop)'
try {
    while ($true) {
        $now = Get-Date

        # --- gateway ---
        if (-not $script:gw -or $script:gw.HasExited) {
            if ($now -ge $script:gwNext) {
                if ($script:gw) { Log "gateway exited (code $($script:gw.ExitCode))" }
                Start-Gateway
                $script:gwNext = (Get-Date).AddSeconds($script:gwDelay)
                $script:gwDelay = Next-Delay $script:gwDelay
            }
        } else {
            $state = Test-Gateway
            if ($state -eq 'ok') { $script:gwFails = 0; $script:gwDelay = 5 }
            elseif ($state -eq 'warming') { $script:gwFails = 0 }
            else {
                $script:gwFails++
                Log "gateway health failed ($($script:gwFails)/$HealthFailures)"
                if ($script:gwFails -ge $HealthFailures) {
                    Log 'gateway not answering: restarting it'
                    Stop-Proc $script:gw
                    $script:gw = $null
                    $script:gwNext = (Get-Date).AddSeconds($script:gwDelay)
                    $script:gwDelay = Next-Delay $script:gwDelay
                }
            }
        }

        # --- tunnel ---
        if (-not $script:tn -or $script:tn.HasExited) {
            if ($now -ge $script:tnNext) {
                if ($script:tn) { Log "tunnel exited (code $($script:tn.ExitCode)); see tunnel.err.log" }
                Start-Tunnel
                $script:tnNext = (Get-Date).AddSeconds($script:tnDelay)
                $script:tnDelay = Next-Delay $script:tnDelay
            }
        } elseif (((Get-Date) - $script:tn.StartTime).TotalSeconds -gt 60) {
            $script:tnDelay = 5   # it has been up for a minute: next failure starts with a short wait again
        }

        Start-Sleep -Seconds $CheckSeconds
    }
}
finally {
    Log 'supervisor stopping: stopping gateway and tunnel'
    Stop-Proc $script:gw
    Stop-Proc $script:tn
    $mutex.ReleaseMutex()
}
