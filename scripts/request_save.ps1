# scripts/request_save.ps1
# 在重启电脑前，触发训练循环立即保存完整 checkpoint（模型 + Replay Buffer）。
#
# 用法：
#   .\scripts\request_save.ps1           # 默认 ne39
#   .\scripts\request_save.ps1 kundur    # 指定场景
#
# 脚本会等待训练确认保存完成后才退出，届时即可安全重启。

param([string]$scenario = "ne39")

$projectRoot = Split-Path $PSScriptRoot -Parent
$runsDir = Join-Path $projectRoot "results\sim_$scenario\runs"

if (-not (Test-Path $runsDir)) {
    Write-Host "ERROR: 找不到 runs 目录: $runsDir" -ForegroundColor Red
    Write-Host "请确认场景名称正确，且训练已至少启动过一次。"
    exit 1
}

# 找最新的 run（按目录名降序，目录名含时间戳）
$latestRun = Get-ChildItem $runsDir -Directory |
    Sort-Object Name -Descending |
    Select-Object -First 1

if (-not $latestRun) {
    Write-Host "ERROR: runs 目录为空，没有正在运行的训练。" -ForegroundColor Red
    exit 1
}

$flagPath = Join-Path $latestRun.FullName "save_now"

# 若已有旧标志（上次未清理），先删掉
if (Test-Path $flagPath) { Remove-Item $flagPath -Force }

# 写标志文件
New-Item -ItemType File -Path $flagPath -Force | Out-Null

Write-Host ""
Write-Host "保存请求已发送" -ForegroundColor Green
Write-Host "  场景   : $scenario"
Write-Host "  Run    : $($latestRun.Name)"
Write-Host "  标志   : $flagPath"
Write-Host ""
Write-Host "等待训练完成当前集后保存..." -ForegroundColor Yellow
Write-Host "(NE39 每集约 7 分钟，请耐心等待)" -ForegroundColor DarkGray
Write-Host ""

# 等待标志文件被训练循环删除（= 保存完成）
$timeoutSec = 600   # 最多等 10 分钟
$elapsed    = 0
$interval   = 5

while ((Test-Path $flagPath) -and ($elapsed -lt $timeoutSec)) {
    Start-Sleep $interval
    $elapsed += $interval
    $remaining = $timeoutSec - $elapsed
    Write-Host "  还在等待... ($elapsed s 已过，剩余超时 $remaining s)" -ForegroundColor DarkGray
}

if (-not (Test-Path $flagPath)) {
    Write-Host ""
    Write-Host "Checkpoint 完成！现在可以安全重启电脑。" -ForegroundColor Green
    Write-Host "重启后重新运行训练命令，会自动从刚才的 checkpoint 恢复。" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "WARN: 等待超时（$timeoutSec s）。训练可能已停止或出错。" -ForegroundColor Red
    Write-Host "请检查训练窗口的输出日志，确认 [SaveNow] Done. 是否出现。"
    Remove-Item $flagPath -Force -ErrorAction SilentlyContinue
}
