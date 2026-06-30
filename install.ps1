# commandai installer for Windows (PowerShell).
#
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#
# Installs the `command-ai` console script (via pipx if available, else
# `pip install --user`), seeds a config file, and wires the `ai` function into
# your PowerShell profile.
#
# Note: macOS is the primary target. On Windows, WSL + ./install.sh gives the
# most faithful experience; this is the native-PowerShell path.

$ErrorActionPreference = 'Stop'
$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Info($m) { Write-Host ("> " + $m) -ForegroundColor Cyan }
function Ok($m)   { Write-Host ("+ " + $m) -ForegroundColor Green }
function Warn($m) { Write-Host ("! " + $m) -ForegroundColor Yellow }

# 1. Install the package.
if (Get-Command pipx -ErrorAction SilentlyContinue) {
    Info "Installing with pipx..."
    pipx install --force $RepoDir
    Ok "Installed command-ai via pipx."
} else {
    Warn "pipx not found; installing with 'pip install --user'."
    python -m pip install --user $RepoDir
    Ok "Installed command-ai with pip --user. Ensure your Python user Scripts dir is on PATH."
}

# 2. Seed a config file if missing (tool reads ~/.config/command-ai/config.toml).
$ConfigDir  = Join-Path $env:USERPROFILE ".config\command-ai"
$ConfigFile = Join-Path $ConfigDir "config.toml"
if (-not (Test-Path $ConfigFile)) {
    New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
    Copy-Item (Join-Path $RepoDir "config.example.toml") $ConfigFile
    # Best-effort: the config may later hold a plaintext API key, so restrict it
    # to the current user (disable inheritance, grant only this account).
    try {
        icacls $ConfigFile /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
        icacls $ConfigDir  /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)(F)" | Out-Null
    } catch { Warn "Could not tighten permissions on $ConfigFile (continuing)." }
    Ok "Wrote default config to $ConfigFile"
} else {
    Info "Config already exists at $ConfigFile (left untouched)."
}

# 3. Wire up the PowerShell profile.
$line = ". `"$RepoDir\shell\ai.ps1`""
if (-not (Test-Path $PROFILE)) {
    New-Item -ItemType File -Force -Path $PROFILE | Out-Null
}
if (Select-String -Path $PROFILE -SimpleMatch $line -Quiet -ErrorAction SilentlyContinue) {
    Info "ai() already sourced in $PROFILE."
} else {
    Add-Content -Path $PROFILE -Value "`n# commandai: ai() function`n$line"
    Ok "Added the ai() function to $PROFILE"
}

# 4. Enable the committed git hooks (pre-push runs the test suite + docs-sync).
try {
    git -C $RepoDir rev-parse --git-dir *> $null
    if ($LASTEXITCODE -eq 0) {
        git -C $RepoDir config core.hooksPath .githooks
        Ok "Enabled git pre-push hook (core.hooksPath=.githooks)."
    }
} catch { }

Write-Host ""
Ok "Done. Restart PowerShell (or run: . `$PROFILE), then try:"
Write-Host "    ai list the 3 largest files in this directory"
