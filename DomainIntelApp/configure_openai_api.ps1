$ErrorActionPreference = "Stop"
$Model = "gpt-5.6-terra"

Write-Host "IntDog OpenAI 联网 API 配置" -ForegroundColor Cyan
Write-Host "密钥只会写入当前 Windows 用户环境变量，不会写入项目配置或日志。"
$SecureKey = Read-Host "请输入 OPENAI_API_KEY" -AsSecureString
$Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)

try {
    $ApiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer)
    if (-not $ApiKey -or -not $ApiKey.StartsWith("sk-")) {
        throw "密钥格式不正确。"
    }
    Write-Host "正在验证 API 和模型访问权限…"
    $Headers = @{ Authorization = "Bearer $ApiKey" }
    $Result = Invoke-RestMethod -Method Get `
        -Uri "https://api.openai.com/v1/models/$Model" `
        -Headers $Headers -TimeoutSec 30
    if (-not $Result.id) { throw "API 返回成功，但没有模型标识。" }

    [Environment]::SetEnvironmentVariable("OPENAI_API_KEY", $ApiKey, "User")
    $env:OPENAI_API_KEY = $ApiKey
    Write-Host "配置成功：$($Result.id)" -ForegroundColor Green
    Write-Host "请完全退出并重新打开 IntDog。"
} catch {
    Write-Host "配置失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($Pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
    }
    Remove-Variable ApiKey -ErrorAction SilentlyContinue
}
