# commandai PowerShell integration — defines the `ai` function for Windows.
#
# Dot-source this from your PowerShell profile ($PROFILE):
#     . "C:\path\to\commandai\shell\ai.ps1"
#
# Like the zsh/bash wrapper, this lets the Python tool do all the interaction
# and then runs the chosen command in YOUR current session (so `cd` / $env:
# changes persist). It also passes the previous command's exit code and recent
# history so you can say `ai fix that`.
#
# Note: macOS is the primary target. On Windows, WSL (with shell/ai.sh) gives
# the most faithful experience; this native PowerShell function is provided for
# convenience. Requires the `command-ai` console script on PATH (pipx/pip).

function ai {
    # Capture the previous command's status FIRST, before anything resets it.
    $lastOk = $?
    $lastCode = $LASTEXITCODE

    if ($args.Count -eq 0) { command-ai; return }

    # Pass informational flags straight through.
    if ($args[0] -in @('--version', '--help', '-h', '--print-config', '--dry-run', '-n')) {
        command-ai @args
        return
    }

    $tmp = (New-TemporaryFile).FullName
    $ctx = (New-TemporaryFile).FullName

    # Recent shell context: previous exit status + recent command lines.
    $statusVal = if ($null -ne $lastCode) { $lastCode } elseif ($lastOk) { 0 } else { 1 }
    $ctxLines = @("last_exit_status=$statusVal", "recent_history:")
    $ctxLines += (Get-History | Select-Object -Last 15 | ForEach-Object { $_.CommandLine })
    Set-Content -Path $ctx -Value $ctxLines -Encoding utf8

    # Tell the tool which shell to target (so it generates PowerShell commands).
    $env:AI_CURRENT_SHELL = 'powershell'

    command-ai --shell-context-file $ctx --output-file $tmp @args
    $code = $LASTEXITCODE
    Remove-Item $ctx -ErrorAction SilentlyContinue

    if ($code -ne 0) { Remove-Item $tmp -ErrorAction SilentlyContinue; return }

    $cmd = Get-Content -Raw -Path $tmp -ErrorAction SilentlyContinue
    Remove-Item $tmp -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($cmd)) { return }

    $cmd = $cmd.Trim()

    # Record in PSReadLine history so you can recall/edit it later.
    try { [Microsoft.PowerShell.PSConsoleReadLine]::AddToHistory($cmd) } catch { }

    # Run it in the CURRENT session so cd / $env: changes persist.
    Invoke-Expression $cmd
}
