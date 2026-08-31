$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $AppDir
$Launcher = Join-Path $AppDir "launch_intdog.py"
$Icon = Join-Path $AppDir "app\intdog.ico"

$Python = $null
$PyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($PyLauncher) {
    try {
        $Python = (& $PyLauncher.Source -3 -c "import sys; print(sys.executable)" 2>$null |
            Select-Object -First 1)
    } catch {}
}
if (-not $Python) {
    $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($PythonCommand) { $Python = $PythonCommand.Source }
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "IntDog 行业情报.lnk"
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$IsWslHome = $ProjectDir -match '^\\\\(?:wsl\.localhost|wsl\$)\\[^\\]+\\'
$NativeReady = (-not $IsWslHome) -and $Python -and (Test-Path $Python.Trim())
if ($IsWslHome) {
    # Windows owns the desktop window lifecycle; WSL owns the runtime and data.
    $WindowsLauncher = Join-Path $AppDir "windows_launcher.ps1"
    $Shortcut.TargetPath = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
    $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WindowsLauncher`""
    $Shortcut.WorkingDirectory = $Desktop
} elseif ($NativeReady) {
    $Pythonw = Join-Path (Split-Path -Parent $Python.Trim()) "pythonw.exe"
    if (-not (Test-Path $Pythonw)) { $Pythonw = $Python.Trim() }
    $Shortcut.TargetPath = $Pythonw
    $Shortcut.Arguments = '"' + $Launcher + '"'
    $Shortcut.WorkingDirectory = $ProjectDir
} else {
    # Windows-drive checkout with Python available only inside WSL.
    $Drive = ([IO.Path]::GetPathRoot($ProjectDir)).Substring(0, 1).ToLower()
    $Rest = $ProjectDir.Substring(3).Replace('\', '/')
    $WslProject = "/mnt/$Drive/$Rest"
    $WslLauncher = "$WslProject/run_intdog.sh"
    $Shortcut.TargetPath = "$env:WINDIR\System32\wsl.exe"
    $Shortcut.Arguments = "--cd `"$WslProject`" bash `"$WslLauncher`""
    $Shortcut.WorkingDirectory = $ProjectDir
}
if (Test-Path $Icon) { $Shortcut.IconLocation = $Icon }
$Shortcut.Description = "IntDog 行业情报工作台"
$Shortcut.Save()
Write-Output $ShortcutPath
