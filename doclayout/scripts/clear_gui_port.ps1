$ErrorActionPreference = 'Stop'

try {
    $listeners = @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq 8471)
    $owners = @($listeners.OwningProcess | Sort-Object -Unique)
    foreach ($ownerId in $owners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerId"
        if (-not $process) { continue }
        $isDocLayout = $process.CommandLine -match 'streamlit\s+run\s+.*doclayout[\\/]scripts[\\/]streamlit_app\.py'
        if (-not $isDocLayout) {
            $answer = Read-Host "Port 8471 is used by $($process.Name) (PID $ownerId). Stop it? Unsaved work may be lost [y/N]"
            if ($answer -notmatch '^(?i:y|yes)$') {
                throw 'Port release cancelled; the application was not stopped.'
            }
        }
        # Recheck identity and ownership before terminating the specific listener.
        $current = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerId"
        $stillListening = @(Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -eq 8471 -and $_.OwningProcess -eq $ownerId })
        if (-not $stillListening.Count) { continue }
        if (-not $current -or $current.CreationDate -ne $process.CreationDate) {
            throw 'Port owner changed; retry the launcher.'
        }
        Write-Host "Stopping $($process.Name) (PID $ownerId) on port 8471..."
        Stop-Process -Id $ownerId -Force -ErrorAction Stop
    }
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        $remaining = @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq 8471)
        if (-not $remaining.Count) { exit 0 }
        Start-Sleep -Milliseconds 250
    }
    throw 'Port 8471 is still busy after waiting five seconds.'
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message)
    exit 1
}
