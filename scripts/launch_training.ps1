# launch_training.ps1 — 启动训练并验证进程已就绪
#
# 用法:
#   .\scripts\launch_training.ps1 kundur          # 只启动 Kundur
#   .\scripts\launch_training.ps1 ne39            # 只启动 NE39
#   .\scripts\launch_training.ps1 both            # 同时启动两个（默认）
#   .\scripts\launch_training.ps1 both 1000       # 指定 episodes
#
# 必须在项目根目录执行，或传入正确的 $RootDir。

param(
    [string]$Target   = "both",
    [int]   $Episodes = 500,
    [string]$Mode     = "simulink",
    [string]$RootDir  = $PSScriptRoot + "\.."
)

$PYTHON = "C:\Users\27443\miniconda3\envs\andes_env\python.exe"
$Root   = (Resolve-Path $RootDir).Path

# PIDs of launched processes — used by Assert-Running for direct liveness check.
$script:LaunchedPids = @{}

function Start-Training {
    param([string]$ScenarioLabel, [string]$ScriptRelPath)

    $scriptPath = Join-Path $Root $ScriptRelPath

    Write-Host "[launch] $ScenarioLabel ..."
    # Direct Start-Process on python.exe (not wrapped in a powershell -Command shell).
    # -PassThru returns the Process object immediately so we get the PID before
    # MATLAB engine finishes loading (~30-60s).  -WindowStyle Normal keeps the
    # training window visible.
    $proc = Start-Process $PYTHON `
        -ArgumentList $scriptPath, "--mode", $Mode, "--episodes", $Episodes `
        -WorkingDirectory $Root `
        -PassThru `
        -WindowStyle Normal
    $script:LaunchedPids[$ScenarioLabel] = $proc.Id
    Write-Host "         PID $($proc.Id)"
}

function Assert-Running {
    param([string]$ScenarioLabel)

    $pid    = $script:LaunchedPids[$ScenarioLabel]
    $verify = 5   # 秒：等待足够确认进程没立即崩溃（Python import ~ 2-3s）
    Write-Host "[wait]   $ScenarioLabel — 等 ${verify}s 确认进程存活..."
    Start-Sleep -Seconds $verify
    $alive = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($alive) {
        Write-Host "[ok]     $ScenarioLabel — PID $pid 存活 (MemMB=$([int]($alive.WorkingSet/1MB)))"
    } else {
        Write-Error "[FAIL]   $ScenarioLabel — PID $pid 已退出，请检查训练窗口错误信息"
        exit 1
    }
}

# ── 启动 ──────────────────────────────────────────────────────────────────────

if ($Target -in "kundur","both") {
    Start-Training "Kundur x Simulink" "scenarios\kundur\train_simulink.py"
}
if ($Target -in "ne39","both") {
    Start-Training "NE39 x Simulink"   "scenarios\new_england\train_simulink.py"
}

# ── 验证 ──────────────────────────────────────────────────────────────────────

if ($Target -in "kundur","both") {
    Assert-Running "Kundur x Simulink"
}
if ($Target -in "ne39","both") {
    Assert-Running "NE39 x Simulink"
}

Write-Host "[done]   全部训练进程已就绪。"
