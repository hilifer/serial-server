# Mark Edge's last session as a clean exit so it never shows the
# "还原页面 / Edge didn't shut down properly" bubble after a kiosk
# reboot or power loss. Called by start.bat before launching Edge.
#
# This lives in its own .ps1 file on purpose: the previous inline
# version used ^ line-continuation inside a batch for/() block, which
# cmd.exe parses unreliably — it produced a PowerShell syntax error on
# every boot and never actually did its job.

$base = Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\User Data'
if (-not (Test-Path $base)) { return }

Get-ChildItem -Path $base -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq 'Default' -or $_.Name -like 'Profile*' } |
    ForEach-Object {
        $f = Join-Path $_.FullName 'Preferences'
        if (Test-Path $f) {
            try {
                $t = Get-Content -Raw -LiteralPath $f
                $t = $t -replace '"exit_type":"[^"]*"', '"exit_type":"Normal"'
                $t = $t -replace '"exited_cleanly":false', '"exited_cleanly":true'
                [System.IO.File]::WriteAllText($f, $t)
            } catch { }
        }
    }
