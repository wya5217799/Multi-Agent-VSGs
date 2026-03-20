"""
一键运行全部实验 — 论文 Fig 4-21 复现
========================================

用法:
  python run_all.py                    # 运行全部 ODE 实验
  python run_all.py --skip-train       # 跳过训练, 仅评估 (需已有模型)
  python run_all.py --andes            # 同时运行 ANDES 实验 (需 WSL)
  python run_all.py --quick            # 快速模式 (减少 episodes)

论文: Yang et al., IEEE TPWRS 2023
"""

import argparse
import os
import sys
import subprocess
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_cmd(cmd, desc, timeout=None):
    """运行命令并打印状态."""
    print(f"\n{'='*60}")
    print(f" {desc}")
    print(f"{'='*60}")
    t0 = time.time()
    result = subprocess.run(cmd, shell=True, timeout=timeout)
    elapsed = time.time() - t0
    status = "✓" if result.returncode == 0 else "✗"
    print(f"  {status} {desc} — {elapsed:.0f}s")
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="一键运行全部论文复现实验")
    parser.add_argument("--skip-train", action="store_true", help="跳过训练")
    parser.add_argument("--andes", action="store_true", help="包含 ANDES 实验 (WSL)")
    parser.add_argument("--quick", action="store_true", help="快速模式 (少量 episodes)")
    args = parser.parse_args()

    ep_main = 200 if args.quick else 2000
    ep_scale = 100 if args.quick else 2000

    os.makedirs("results/figures", exist_ok=True)

    print(f"\n论文复现 — Yang et al. TPWRS 2023")
    print(f"Episodes: main={ep_main}, scalability={ep_scale}")
    print(f"模式: {'快速' if args.quick else '完整'}, "
          f"{'跳过训练' if args.skip_train else '含训练'}, "
          f"{'含ANDES' if args.andes else '仅ODE'}")

    success = True
    t_total = time.time()

    # ═══ Step 1: ODE 主训练 (Fig 4) ═══
    if not args.skip_train:
        ok = run_cmd(f"python train.py --episodes {ep_main}",
                     f"Step 1/6: ODE 主训练 ({ep_main}ep) → Fig 4 训练曲线")
        success = success and ok

    # ═══ Step 2: ODE 评估 (Fig 4-13) ═══
    ok = run_cmd("python evaluate.py",
                 "Step 2/6: ODE 评估 → Fig 4-13")
    success = success and ok

    # ═══ Step 3: 可扩展性实验 (Fig 14-16) ═══
    if not args.skip_train:
        ok = run_cmd(f"python train_scalability.py --episodes {ep_scale}",
                     f"Step 3/6: 可扩展性训练 N=2,4,8 ({ep_scale}ep) → Fig 14-15")
        success = success and ok

    # ═══ Step 4: New England (Fig 17-21) ═══
    if not args.skip_train:
        ok = run_cmd(f"python train_new_england.py --episodes {ep_main}",
                     f"Step 4/6: New England 训练+评估 ({ep_main}ep) → Fig 17-21")
        success = success and ok

    # ═══ Step 5: Fig 16 可扩展性分析图 ═══
    ok = run_cmd("python generate_fig16.py",
                 "Step 5/6: 生成 Fig 16 可扩展性分析")
    # Fig 16 失败不影响整体
    if not ok:
        print("  (Fig 16 跳过, 需先完成可扩展性训练)")

    # ═══ Step 6: ANDES (可选) ═══
    if args.andes:
        wsl_prefix = 'wsl -e bash -c \'source ~/andes_venv/bin/activate && cd "/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs" && '

        if not args.skip_train:
            ok = run_cmd(
                f'{wsl_prefix}python3 train_andes.py --episodes {ep_main} '
                f'--save-dir results/andes_models_r4\'',
                f"Step 6a/6: ANDES 训练 ({ep_main}ep)")
            success = success and ok

        ok = run_cmd(
            f'{wsl_prefix}python3 evaluate_andes.py\'',
            "Step 6b/6: ANDES 评估 → Fig 4-13 (ANDES)")
        success = success and ok

    # ═══ 汇总 ═══
    total_time = time.time() - t_total
    print(f"\n{'='*60}")
    print(f" 全部完成! 总耗时: {total_time/60:.1f} 分钟")
    print(f"{'='*60}")

    # 列出所有生成的图
    fig_dir = "results/figures"
    figs = sorted([f for f in os.listdir(fig_dir) if f.endswith('.png')])
    print(f"\n生成的图表 ({len(figs)} 张):")
    for f in figs:
        size = os.path.getsize(os.path.join(fig_dir, f))
        print(f"  {f} ({size//1024}KB)")

    if not success:
        print("\n⚠ 部分步骤失败, 请检查输出")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
