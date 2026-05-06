# R01 Plan (saturated, R01.2)

**Status**: DRAFT
**Date**: 2026-05-07
**Trigger**: handoff `2026-05-07_andes_6axis_recovery_handoff.md` → fresh start; user 2026-05-07 后追问 "感觉没饱和" 触发 R01.2 重排

## 上轮
无 (R0). prior = 6-axis 真相文档 + recovery plan.
现 best ckpt = `balanced_seed46_best`, overall=0.036, smoothness=0.83, 其余 axis 全 fail.

## 假设
H1: 加 LAMBDA_SMOOTH=0.01 平滑惩罚 → smoothness axis 0.83→0.95+ (5 seed mean±std).
   理由: ΔH/ΔD std 22 偏大根因 = SAC stochastic actor + 无 smoothing penalty.
H2: λ ∈ {0.001, 0.01, 0.1} 三档定 sweet spot, 主推 λ=0.01 多 seed 出 std.
   理由: 太小无效, 太大压抑探索退化为 no-control. 5 seed × λ=0.01 是 R02 直接接 baseline.
H3: ANDES IEEEG1+EXST1 add API 可跑 + H₀=50 power flow 收敛.
   理由: Phase B/C 是 G2/G3/G4 唯一通道. 不验通就盲投 R02 全训.

## 跑啥 (K=8, 物理饱和: CPU 32/4=8 上限, daemon fit_count=8)
预算 budget_pct≈1.0 → K_max heuristic=4. AI override → K=8 全占 CPU vCPU.
RAM: 8×1.5=12 + probe 1 = 13 GB / 24 free, safe. VRAM: 7 GPU×~400MB ≈ 2.8 GB / 8 GB.
GPU SM 利用率 ~35-50% (256-256 net 不真饱和; 真饱和靠 R02 加大 batch/hidden).

```
exp1: r01_BC_probe          backend=andes_cpu (cpu, 1 vCPU 槽, ~5-10min)
      sanity only: IEEEG1+EXST1 add API + H₀{20,30,50,80} pf+5step TDS smoke
exp2: r01_A_lam0p01_s42     backend=sac_gpu  λ=0.01 seed=42  (5seed canonical)
exp3: r01_A_lam0p01_s43     backend=sac_gpu  λ=0.01 seed=43
exp4: r01_A_lam0p01_s44     backend=sac_gpu  λ=0.01 seed=44
exp5: r01_A_lam0p01_s45     backend=sac_gpu  λ=0.01 seed=45
exp6: r01_A_lam0p01_s46     backend=sac_gpu  λ=0.01 seed=46  → 5seed mean±std on smoothness axis = R01 main signal
exp7: r01_A_lam0p001_s42    backend=sac_gpu  λ=0.001 seed=42 (low-arm)
exp8: r01_A_lam0p1_s42      backend=sac_gpu  λ=0.1 seed=42   (high-arm)
exp9: r01_A_stress_b2048_h1024  backend=sac_gpu  batch=2048 hidden=1024 (GPU stress; queues 9th, 等空槽)

每路: V2 env, 50 ep, --phi-d 0.05, DEVICE=cuda CUDA_VISIBLE_DEVICES=0
backend=sac_gpu wraps andes_cpu.sh + GPU env injection (per nav-layer 修)
exp9 改 batch_size 256→2048 + hidden 128→1024 把 GPU 真打满 (~3-5 GB VRAM 单进程, SM ~80%+)
```

## Why 论文 config 不真饱和 VRAM (而 stress arm 解决)
SAC 论文 net [128,128,128,128] + batch=256 单进程 VRAM ≈ 250-400 MB.
7 路并行 ≈ 2-3 GB / 8 GB, SM 30-50%. 不饱和 root cause = 网络太小, 不是 GPU 不行.

要饱和 GPU 必修:
- (a) 加 batch_size 256→2048+ ✅ exp9 stress arm 跑这个
- (b) 加 hidden 128→1024 ✅ exp9 stress arm 跑这个
- (c) 多 seed × 多 λ 组合堆 16+ 路 → CPU 不够 (32/4=8 上限)

(a)+(b) 同步在 exp9 (off-paper, 不进 R02 训练 baseline, 仅 GPU pipeline 可用性证明).
R01 8 路 ANDES = CPU 物理饱和 (32 vCPU 全用); 9th stress arm 等空槽接.
论文 baseline (exp2-8) 仍 byte-faithful Table I, paper-anchor 不破.

## 期 (跟 G1-G6)
- G5 (smoothness ≤1.0): exp2-6 mean smoothness axis std ≤ 5.0 (5seed mean±std)
- exp4 (BC_probe): IEEEG1 add API 不抛 ImportError; H₀=50 pf 收敛 + 5step TDS 不发散
- G1-G4/G6 R01 不涉, R02 起跳

## 不行咋办
- exp2-8 全 NaN/critic 爆 → incident, λ 公式 bug, R02 重做
- exp2-6 std 巨大 → audit, smoothing penalty 失效原因 (per-agent dilute?), R02 改 reward 路径
- exp1 IEEEG1 add 抛错 → pivot R02: 不上 governor, 换 H4="D₀ 放大 5x 当 governor proxy"
- exp1 H₀=50 pf 不收敛 → R02 收紧 H₀ ≤ 30, 重算 ΔH range axis 上限

## 双 metric 强制
R01 是 50ep smoke, 不出 cum_rf @50 fixed seed (太短). 仅出:
- train_reward (R_avg10 5seed mean±std)
- 末 5ep ΔH/ΔD std (smoothness 信号)
- 6-axis 跑 (daemon 自动) 但 50ep 太短 ranking 不稳, 仅参考 smoothness axis
verdict 标 "smoke, paper_grade not measured". R02 进 200ep 再走双 metric.

## §note (GPU 政策, nav-layer 已修)
2026-05-07 user override: GPU=optional 不 REJECT. spec verdict 是 ROI 弱不是不兼容.
SKILL.md / feedback_gpu_policy_optional.md 同步. 7 路 GPU 镜像 (R01.2 saturated) 实测对照.

---

# §Done (post-execution append)
(待 R01 8 路全完后填)
