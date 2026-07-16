# Eshu Forex Trader — Windows VPS bootstrap.
# Run from the repo root (e.g. C:\Eshu) in an elevated PowerShell:
#   powershell -ExecutionPolicy Bypass -File deploy\setup_windows.ps1
# Creates the venv, installs deps, registers the daily Scheduled Task, runs one test cycle.

$ErrorActionPreference = "Stop"
$Root = (Get-Location).Path
Write-Host "Eshu setup in $Root"

# 1) venv + dependencies
if (-not (Test-Path "$Root\.venv")) {
    py -3 -m venv "$Root\.venv"
}
& "$Root\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$Root\.venv\Scripts\python.exe" -m pip install -r "$Root\requirements.txt"

# 2) .env sanity
if (-not (Test-Path "$Root\.env")) {
    Copy-Item "$Root\.env.example" "$Root\.env"
    Write-Warning ".env created from template — EDIT IT (Telegram token/chat id, QUEUE_DIR) before going live."
}

# 3) daily runner wrapper (logs to data\dailyrun.log)
$Bat = "$Root\deploy\run_daily.bat"
@"
@echo off
cd /d $Root
".venv\Scripts\python.exe" scripts\daily_run.py >> data\dailyrun.log 2>&1
"@ | Set-Content -Path $Bat -Encoding ASCII
New-Item -ItemType Directory -Force -Path "$Root\data" | Out-Null

# 4) Scheduled Task: daily 07:00 server time, catch up after downtime, retry on failure
$Action   = New-ScheduledTaskAction -Execute $Bat
$Trigger  = New-ScheduledTaskTrigger -Daily -At 07:00
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
            -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10) `
            -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "EshuDailyRun" -Action $Action -Trigger $Trigger `
    -Settings $Settings -Description "Eshu Forex Trader daily risk directive + weekly rebalance" -Force

Write-Host "Scheduled task 'EshuDailyRun' registered (daily 07:00, StartWhenAvailable)."

# 5) one manual test cycle so you see it work now
Write-Host "`nRunning one test cycle..."
& "$Root\.venv\Scripts\python.exe" "$Root\scripts\daily_run.py"
Write-Host "`nDone. Check data\dailyrun.log and your Telegram, then follow deploy\WINDOWS_VPS_SETUP.md step 5."
