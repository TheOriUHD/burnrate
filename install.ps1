<#
.SYNOPSIS
  Install, update or remove Burnrate on Windows (per user, no admin rights needed).

.DESCRIPTION
  One line in PowerShell:
      irm https://raw.githubusercontent.com/TheOriUHD/burnrate/main/install.ps1 | iex

  What it does:
    * finds Python 3.11+ (offers to install it with winget if missing)
    * creates a private environment in %LOCALAPPDATA%\Burnrate and installs Burnrate into it
    * starts Burnrate in the background at every logon (shortcut in your Startup folder, no console window)
    * starts it now and opens http://127.0.0.1:8090

  Run it again to update. Your data (%LOCALAPPDATA%\Burnrate\data) is kept.

  With options:
      & ([scriptblock]::Create((irm https://raw.githubusercontent.com/TheOriUHD/burnrate/main/install.ps1))) -Lan -Port 9000
  Options:
    -Port <n>     port to listen on (default 8090)
    -Lan          reachable from other devices on your network (asks for a password on first visit)
    -NoAutostart  don't start with Windows
    -Source <s>   install from a folder or zip instead of GitHub main
    -Uninstall    remove Burnrate (asks before deleting your data)
#>
param(
    [int]$Port = 8090,
    [switch]$Lan,
    [switch]$NoAutostart,
    [string]$Source = "https://github.com/TheOriUHD/burnrate/archive/refs/heads/main.zip",
    [switch]$Uninstall
)
$ErrorActionPreference = "Stop"
$Home_ = Join-Path $env:LOCALAPPDATA "Burnrate"
$Venv = Join-Path $Home_ "venv"
$Data = Join-Path $Home_ "data"
$Launcher = Join-Path $Home_ "start-burnrate.cmd"
$Shortcut = Join-Path ([Environment]::GetFolderPath("Startup")) "Burnrate.lnk"

function Say($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

function Stop-Burnrate {
    # the pid Burnrate wrote at start (a venv's pythonw.exe is only a launcher for the real interpreter)
    $pidFile = Join-Path $Data "burnrate.pid"
    if (Test-Path $pidFile) {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$([int](Get-Content $pidFile))" -ErrorAction SilentlyContinue
        if ($p -and $p.CommandLine -match "burnrate") {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 500
        }
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    }
}

if ($Uninstall) {
    Say "Stopping Burnrate"
    Stop-Burnrate
    Remove-Item $Shortcut -ErrorAction SilentlyContinue
    Remove-Item $Venv, $Launcher -Recurse -Force -ErrorAction SilentlyContinue
    if ((Test-Path $Data) -and -not $env:CI -and (Read-Host "Also delete your Burnrate data in $Data? [y/N]") -match '^[yY]') {
        Remove-Item $Home_ -Recurse -Force
    }
    Say "Burnrate removed."
    return
}

function Find-Python {
    foreach ($c in @(@("py", "-3"), @("python"), @("python3"))) {
        $exe = Get-Command $c[0] -ErrorAction SilentlyContinue
        if (-not $exe) { continue }
        $args_ = @($c | Select-Object -Skip 1) + @("-c", "import sys; print('%d.%d' % sys.version_info[:2]); print(sys.executable)")
        try { $out = & $c[0] @args_ 2>$null } catch { continue }
        if ($LASTEXITCODE -ne 0 -or -not $out) { continue }     # the Microsoft Store stub prints nothing useful
        $ver = [version]($out[0]); if ($ver -ge [version]"3.11") { return $out[1] }
    }
    return $null
}

Say "Looking for Python 3.11 or newer"
$Python = Find-Python
if (-not $Python) {
    if ((Get-Command winget -ErrorAction SilentlyContinue) -and
        ((Read-Host "Python 3.11+ was not found. Install Python 3.13 with winget now? [Y/n]") -notmatch '^[nN]')) {
        winget install --id Python.Python.3.13 -e --scope user --accept-package-agreements --accept-source-agreements
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
        $Python = Find-Python
    }
    if (-not $Python) { throw "Python 3.11+ is required. Install it from https://www.python.org/downloads/ (tick 'Add to PATH') and run this again." }
}
Say "Using $Python"

New-Item -ItemType Directory -Force -Path $Home_, $Data | Out-Null
Stop-Burnrate
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    Say "Creating the environment in $Venv"
    & $Python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "could not create the virtual environment" }
}
$VPy = Join-Path $Venv "Scripts\python.exe"
$VPyw = Join-Path $Venv "Scripts\pythonw.exe"
Say "Installing Burnrate from $Source"
& $VPy -m pip install --quiet --disable-pip-version-check --upgrade --force-reinstall --no-deps $Source
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
& $VPy -m pip install --quiet --disable-pip-version-check --upgrade tzdata     # Windows has no zone database
if ($LASTEXITCODE -ne 0) { throw "pip install tzdata failed" }

if ($Lan) { $Listen = "0.0.0.0"; $Auth = "password" } else { $Listen = "127.0.0.1"; $Auth = "none" }
# the launcher keeps the settings in one place; edit it to change port / listen address later
@"
@echo off
rem Burnrate launcher (written by install.ps1). Change the values and run it again, or re-run the installer.
set BURNRATE_DATA=$Data
set BURNRATE_LISTEN=$Listen
set BURNRATE_PORT=$Port
set BURNRATE_AUTH=$Auth
start "" /b "$VPyw" -m burnrate
"@ | Set-Content -Encoding Oem $Launcher     # cmd.exe reads batch files in the OEM code page (umlauts in user names)

if (-not $NoAutostart) {
    Say "Starting with Windows (Startup folder shortcut)"
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut($Shortcut)
    $lnk.TargetPath = $Launcher
    $lnk.WorkingDirectory = $Home_
    $lnk.WindowStyle = 7                          # minimized: the .cmd window closes right away
    $lnk.Description = "Burnrate usage tracker"
    $lnk.Save()
} else {
    Remove-Item $Shortcut -ErrorAction SilentlyContinue
}

Say "Starting Burnrate"
Start-Process -FilePath $Launcher -WindowStyle Hidden -WorkingDirectory $Home_
$Url = "http://127.0.0.1:$Port"
$up = $false
foreach ($i in 1..30) {
    Start-Sleep -Milliseconds 500
    try { Invoke-RestMethod "$Url/healthz" -TimeoutSec 2 | Out-Null; $up = $true; break } catch {}
}
if (-not $up) { throw "Burnrate did not come up on $Url. Log: $(Join-Path $Data 'burnrate.log')" }

Write-Host ""
Write-Host "Burnrate is running: $Url" -ForegroundColor Green
Write-Host "  data:     $Data"
Write-Host "  log:      $(Join-Path $Data 'burnrate.log')"
Write-Host "  settings: $Launcher"
if ($Lan) {
    Write-Host "  On first visit Burnrate asks for a setup code: it is in the log file above." -ForegroundColor Yellow
    Write-Host "  Windows may ask whether Python may accept network connections: allow it for private networks."
}
Write-Host "  update: run the same install command again; remove: add -Uninstall"
if (-not $env:CI) { Start-Process $Url }
