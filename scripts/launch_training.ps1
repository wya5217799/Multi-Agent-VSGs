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

function Start-Training {
    param([string]$ScenarioLabel, [string]$ScriptRelPath)

    $script = Join-Path $Root $ScriptRelPath
    $cmd    = "& '$PYTHON' '$script' --mode $Mode --episodes $Episodes"

    Write-Host "[launch] $ScenarioLabel ..."
    # Use -WorkingDirectory instead of cd inside -Command:
    # paths with multiple spaces (e.g. "Multi-Agent  VSGs") cause Set-Location
    # to fail silently when passed through -ArgumentList string expansion.
    Start-Process powershell -WorkingDirectory $Root -ArgumentList "-NoExit", "-Command", $cmd
}

function Assert-Running {
    param([string]$ScenarioLabel, [string]$ScriptPattern)

    Start-Sleep -Seconds 4
    $proc = Get-WmiObject Win32_Process -Filter "name='python.exe'" |
            Where-Object { $_.CommandLine -like "*$ScriptPattern*" }

    if ($proc) {
        Write-Host "[ok]     $ScenarioLabel — PID $($proc.ProcessId)"
    } else {
        Write-Error "[FAIL]   $ScenarioLabel — 进程未找到，请检查 PowerShell 窗口错误信息"
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

Write-Host "[wait]   等待进程启动..."

if ($Target -in "kundur","both") {
    Assert-Running "Kundur x Simulink" "kundur\train_simulink"
}
if ($Target -in "ne39","both") {
    Assert-Running "NE39 x Simulink"   "new_england\train_simulink"
}

Write-Host "[done]   全部训练进程已就绪。"
