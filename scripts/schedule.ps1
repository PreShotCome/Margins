param([switch]$Remove)
$ErrorActionPreference = 'Stop'
$taskName = 'Dokaz-Margins'
if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host 'Margins schedule removed.'
    exit
}
$projectPath = Split-Path $PSScriptRoot -Parent
$pythonPath = (& py -3 -c 'import sys; print(sys.executable)').Trim()
if (-not (Test-Path $pythonPath)) { throw 'Python 3.11+ is required.' }
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument '-m margins run' -WorkingDirectory $projectPath
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host 'Runs every 30 minutes while this user is logged in. Keep the computer awake and online.'
Write-Host 'Source ingestion, publication, and customer briefs each run at most daily; failures retry within limits.'
