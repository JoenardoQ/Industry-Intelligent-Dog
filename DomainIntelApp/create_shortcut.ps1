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
$NativeReady = $Python -and (Test-Path $Python.Trim())
if ($NativeReady) {
    $Pythonw = Join-Path (Split-Path -Parent $Python.Trim()) "pythonw.exe"
    if (-not (Test-Path $Pythonw)) { $Pythonw = $Python.Trim() }
    $Shortcut.TargetPath = $Pythonw
    $Shortcut.Arguments = '"' + $Launcher + '"'
} else {
    # Codex workspace runs in WSL; use its Python/WSLg when native Python is absent.
    $Drive = ([IO.Path]::GetPathRoot($ProjectDir)).Substring(0, 1).ToLower()
    $Rest = $ProjectDir.Substring(3).Replace('\', '/')
    $WslProject = "/mnt/$Drive/$Rest"
    $WslLauncher = "$WslProject/DomainIntelApp/launch_intdog.py"
    $Shortcut.TargetPath = "$env:WINDIR\System32\wsl.exe"
    $Shortcut.Arguments = "--cd `"$WslProject`" python3 `"$WslLauncher`""
}
$Shortcut.WorkingDirectory = $ProjectDir
if (Test-Path $Icon) { $Shortcut.IconLocation = $Icon }
$Shortcut.Description = "IntDog 行业情报工作台"
$Shortcut.Save()
Write-Output $ShortcutPath
