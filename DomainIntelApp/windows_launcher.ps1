# Developer-only WSL compatibility launcher; excluded from native release resources.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$WslDistribution = "Ubuntu-D"
$WslProject = "/home/joenardo/My Projects/IntDog"
$WslExe = "$env:WINDIR\System32\wsl.exe"
$ApiUrl = "http://127.0.0.1:8765"
$Profile = Join-Path $env:TEMP ("IntDog\Sessions\" + [Guid]::NewGuid().ToString("N"))
$LogDir = Join-Path $env:LOCALAPPDATA "IntDog"
$LogPath = Join-Path $LogDir "launcher.log"
$ServerOut = Join-Path $LogDir "server.stdout.log"
$ServerErr = Join-Path $LogDir "server.stderr.log"
$Server = $null
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-LauncherLog([string]$Text) {
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "[$Timestamp] $Text"
}

$Form = New-Object System.Windows.Forms.Form
$Form.Text = "IntDog 正在启动"
$Form.Size = New-Object System.Drawing.Size(480, 210)
$Form.StartPosition = "CenterScreen"
$Form.FormBorderStyle = "FixedDialog"
$Form.MaximizeBox = $false
$Form.MinimizeBox = $false
$Form.TopMost = $true
$Form.BackColor = [System.Drawing.Color]::FromArgb(244, 246, 245)
$Title = New-Object System.Windows.Forms.Label
$Title.Text = "IntDog"
$Title.Font = New-Object System.Drawing.Font("Segoe UI", 20, [System.Drawing.FontStyle]::Bold)
$Title.ForeColor = [System.Drawing.Color]::FromArgb(38, 54, 49)
$Title.AutoSize = $true
$Title.Location = New-Object System.Drawing.Point(34, 28)
$Status = New-Object System.Windows.Forms.Label
$Status.Text = "正在检查运行环境…"
$Status.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 11)
$Status.ForeColor = [System.Drawing.Color]::FromArgb(82, 102, 95)
$Status.AutoSize = $true
$Status.Location = New-Object System.Drawing.Point(36, 91)
$Progress = New-Object System.Windows.Forms.ProgressBar
$Progress.Style = "Marquee"
$Progress.MarqueeAnimationSpeed = 25
$Progress.Location = New-Object System.Drawing.Point(38, 130)
$Progress.Size = New-Object System.Drawing.Size(390, 8)
$Form.Controls.AddRange(@($Title, $Status, $Progress))
$Form.Show()
[System.Windows.Forms.Application]::DoEvents()

function Update-Status([string]$Text) {
    $Status.Text = $Text
    [System.Windows.Forms.Application]::DoEvents()
}

try {
    Write-LauncherLog "启动请求；desktop=$([Environment]::GetFolderPath('Desktop')); project=$WslProject; distro=$WslDistribution"
    Update-Status "正在准备隔离运行环境…"
    Write-LauncherLog "准备运行环境"
    $PrepareOutput = & $WslExe --distribution $WslDistribution --cd $WslProject `
        bash "$WslProject/run_intdog.sh" --prepare 2>&1
    $PrepareSucceeded = $?
    $PrepareExit = $LASTEXITCODE
    $PrepareOutput | Set-Content -LiteralPath (Join-Path $LogDir "prepare.stdout.log") -Encoding UTF8
    Write-LauncherLog "环境准备返回；success=$PrepareSucceeded; exit=$PrepareExit"
    if (-not $PrepareSucceeded) { throw "运行环境准备失败 ($PrepareExit)" }
    Write-LauncherLog "运行环境就绪"

    $Bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($Bytes)
    $Token = [Convert]::ToBase64String($Bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
    $ServeArgs = "--distribution $WslDistribution --cd `"$WslProject`" bash `"$WslProject/DomainIntelApp/serve_intdog.sh`" $Token"
    Update-Status "正在加载行业数据库…"
    $Server = Start-Process -FilePath $WslExe -ArgumentList $ServeArgs -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $ServerOut -RedirectStandardError $ServerErr
    Write-LauncherLog "服务进程已启动；pid=$($Server.Id)"

    $Ready = $false
    for ($Index = 0; $Index -lt 120; $Index++) {
        if ($Server.HasExited) {
            $Server.WaitForExit()
            $Server.Refresh()
            throw "IntDog 服务启动失败 ($($Server.ExitCode))"
        }
        try {
            $null = Invoke-RestMethod -Method Get -Uri "$ApiUrl/api/health" -TimeoutSec 1
            $Ready = $true
            break
        } catch {}
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 250
    }
    if (-not $Ready) { throw "IntDog 服务在 30 秒内未就绪" }
    Write-LauncherLog "健康检查通过"

    $Browsers = @(
        "C:\Program Files\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    )
    $Browser = $Browsers | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Browser) { throw "需要安装 Chrome 或 Edge" }
    New-Item -ItemType Directory -Force -Path $Profile | Out-Null
    $BrowserArgs = @(
        "--user-data-dir=$Profile",
        "--app=$ApiUrl#session=$Token",
        "--no-first-run",
        "--disable-background-mode",
        "--disable-features=Translate"
    )
    Update-Status "工作台已就绪，正在打开…"
    $Form.Close()
    $BrowserProcess = Start-Process -FilePath $Browser -ArgumentList $BrowserArgs -PassThru
    Write-LauncherLog "浏览器应用已启动；browser=$Browser; pid=$($BrowserProcess.Id)"
    $BrowserProcess.WaitForExit()
    Write-LauncherLog "浏览器应用已关闭；开始关闭服务"
} catch {
    Write-LauncherLog "启动失败：$($_.Exception.ToString())"
    if ($Form.Visible) { $Form.Close() }
    [System.Windows.Forms.MessageBox]::Show(
        "$($_.Exception.Message)`n`nWindows 日志：$LogPath`n服务错误：$ServerErr",
        "IntDog 启动失败", "OK", "Error") | Out-Null
} finally {
    if ($Token) {
        try {
            Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$ApiUrl/api/shutdown" `
                -Headers @{ "X-IntDog-Session" = $Token } -TimeoutSec 3 | Out-Null
        } catch {}
    }
    if ($Server -and -not $Server.HasExited) {
        $null = $Server.WaitForExit(10000)
    }
    Remove-Item -LiteralPath $Profile -Recurse -Force -ErrorAction SilentlyContinue
    if ($Form.Visible) { $Form.Close() }
    Write-LauncherLog "启动会话结束"
}
