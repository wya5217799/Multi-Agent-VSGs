"""
Unified entry point for Modified NE 39-Bus Multi-Agent VSG System.

Usage:
    # Train in standalone mode (no MATLAB needed)
    python run_all.py train --mode standalone --episodes 500

    # Train with Simulink
    python run_all.py train --mode simulink --episodes 500

    # Evaluate and generate paper figures
    python run_all.py evaluate --mode standalone --checkpoint checkpoints/best.pt

    # Generate single figure
    python run_all.py evaluate --mode standalone --fig 18

    # Quick test (5 episodes, verify everything works)
    python run_all.py test --mode standalone

    # Build Simulink model (requires MATLAB)
    python run_all.py build-model

    # Calibrate standalone env against paper values
    python run_all.py calibrate --mode standalone
"""

import argparse
import sys
import os
import time
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def cmd_train(args):
    """Run training."""
    from scenarios.new_england.train_simulink import train, parse_args as train_parse_args

    # Forward args to train.py
    sys.argv = ["train.py",
                "--mode", args.mode,
                "--episodes", str(args.episodes),
                "--seed", str(args.seed)]
    if args.resume:
        sys.argv += ["--resume", args.resume]
    if args.x_line != 0.10:
        sys.argv += ["--x-line", str(args.x_line)]
    if args.comm_delay > 0:
        sys.argv += ["--comm-delay", str(args.comm_delay)]

    train_args = train_parse_args()
    train(train_args)


def cmd_evaluate(args):
    """Run evaluation and generate figures."""
    from scenarios.new_england.evaluate_simulink import main as eval_main

    sys.argv = ["evaluate.py",
                "--mode", args.mode]
    if args.checkpoint:
        sys.argv += ["--checkpoint", args.checkpoint]
    if args.fig:
        sys.argv += ["--fig", str(args.fig)]

    eval_main()


def cmd_test(args):
    """Quick integration test."""
    print("=" * 60)
    print("Quick Integration Test")
    print("=" * 60)

    # Test 1: Import all modules
    print("\n[1/5] Importing modules...")
    try:
        from env.simulink.ne39_simulink_env import NE39BusStandaloneEnv
        from env.simulink.sac_agent_standalone import SACAgent
        from scenarios.new_england import config_simulink as config
        print("  OK: All modules imported")
    except Exception as e:
        print(f"  FAIL: {e}")
        return

    # Test 2: Create environment
    print("\n[2/5] Creating standalone environment...")
    try:
        env = NE39BusStandaloneEnv(x_line=args.x_line, training=True)
        print(f"  OK: obs_space={env.observation_space.shape}, act_space={env.action_space.shape}")
    except Exception as e:
        print(f"  FAIL: {e}")
        return

    # Test 3: Reset and step
    print("\n[3/5] Reset + 5 steps...")
    try:
        obs, info = env.reset(seed=42)
        print(f"  Reset OK: obs shape={obs.shape}, sim_time={info['sim_time']}")

        for i in range(5):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            print(f"  Step {i+1}: t={info['sim_time']:.1f}s, "
                  f"avg_omega={info['omega'].mean():.6f}, "
                  f"avg_reward={reward.mean():+.4f}")
            if terminated:
                print("  TERMINATED early!")
                break
    except Exception as e:
        print(f"  FAIL: {e}")
        return

    # Test 4: SAC agent
    print("\n[4/5] Testing SAC agent...")
    try:
        agent = SACAgent(obs_dim=config.OBS_DIM, act_dim=2)
        actions = agent.select_actions_multi(obs, deterministic=False)
        print(f"  OK: actions shape={actions.shape}, range=[{actions.min():.3f}, {actions.max():.3f}]")

        # Store a few transitions
        next_obs, rewards, _, _, _ = env.step(actions)
        agent.store_multi_transitions(obs, actions, rewards, next_obs, False)
        print(f"  OK: buffer size={len(agent.buffer)}")
    except Exception as e:
        print(f"  FAIL: {e}")
        return

    # Test 5: Quick training (3 episodes)
    print("\n[5/5] Quick training (3 episodes)...")
    try:
        for ep in range(3):
            obs, _ = env.reset(seed=ep)
            ep_reward = 0
            for step in range(int(config.T_EPISODE / config.DT)):
                actions = agent.select_actions_multi(obs, deterministic=False)
                next_obs, rewards, terminated, truncated, info = env.step(actions)
                agent.store_multi_transitions(obs, actions, rewards, next_obs,
                                              terminated or truncated)
                agent.update()
                obs = next_obs
                ep_reward += rewards.mean()
                if terminated or truncated:
                    break
            print(f"  Episode {ep+1}: total_reward={ep_reward:+.2f}, "
                  f"steps={step+1}, buffer={len(agent.buffer)}")
        print("  OK: Training loop works")
    except Exception as e:
        print(f"  FAIL: {e}")
        return

    env.close()
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)


def cmd_build_model(args):
    """Build modified Simulink model via MATLAB."""
    print("Building modified Simulink model...")
    try:
        import matlab.engine
        eng = matlab.engine.start_matlab()
        eng.cd(os.path.dirname(os.path.abspath(__file__)), nargout=0)

        print("Running build_modified_model.m ...")
        eng.eval("run('build_modified_model.m');", nargout=0)

        print("Running build_pmsg_wind_farm.m ...")
        eng.eval("build_pmsg_wind_farm('NE39bus_v2');", nargout=0)

        print("Running build_comm_topology.m ...")
        eng.eval("build_comm_topology('NE39bus_v2');", nargout=0)

        eng.quit()
        print("Model build complete: NE39bus_v2.slx")
    except Exception as e:
        print(f"Build failed: {e}")
        print("Make sure MATLAB is installed and matlab.engine is available.")


def cmd_calibrate(args):
    """Calibrate standalone environment against paper reference values."""
    from env.simulink.ne39_simulink_env import NE39BusStandaloneEnv
    from scenarios.new_england import config_simulink as config

    print("=" * 60)
    print("Calibrating Standalone Environment")
    print("=" * 60)

    env = NE39BusStandaloneEnv(x_line=args.x_line, training=False)

    # Run W2 trip scenario with no control
    obs, _ = env.reset(seed=0)
    omega_history = []
    time_history = []

    for step in range(config.STEPS_PER_EPISODE):
        if step == int(config.SCENARIO1_TRIP_TIME / config.DT):
            env.gen_trip(config.SCENARIO1_GEN_TRIP)

        action = np.zeros((config.N_AGENTS, 2), dtype=np.float32)  # no control
        obs, _, terminated, truncated, info = env.step(action)
        omega_history.append(info['omega'].copy())
        time_history.append(info['sim_time'])

        if terminated:
            break

    omega_arr = np.array(omega_history)
    time_arr = np.array(time_history)

    # Analyze
    freq_dev_hz = (omega_arr - 1.0) * config.FN

    # Steady state (last 2 seconds)
    ss_mask = time_arr > (config.T_EPISODE - 2.0)
    ss_dev = freq_dev_hz[ss_mask].mean()

    # Max transient
    max_dev = freq_dev_hz.min()
    max_dev_agent = np.unravel_index(freq_dev_hz.argmin(), freq_dev_hz.shape)[1]

    # Oscillation period (from zero crossings of ES2)
    es2_dev = freq_dev_hz[:, 1]
    zero_crossings = np.where(np.diff(np.sign(es2_dev - es2_dev.mean())))[0]
    if len(zero_crossings) >= 2:
        period = 2 * (time_arr[zero_crossings[-1]] - time_arr[zero_crossings[0]]) / (len(zero_crossings) - 1)
    else:
        period = float('nan')

    print(f"\n{'Metric':<30} {'Simulated':>12} {'Paper Ref':>12} {'Match':>8}")
    print("-" * 65)

    def check(name, sim_val, ref_val, tol=0.3):
        match = abs(sim_val - ref_val) < abs(ref_val * tol) if ref_val != 0 else abs(sim_val) < tol
        status = "OK" if match else "TUNE"
        print(f"{name:<30} {sim_val:>12.4f} {ref_val:>12.4f} {status:>8}")
        return match

    check("Steady-state freq dev (Hz)", ss_dev, config.CALIB_STEADY_STATE_FREQ_DEV)
    check("Max transient freq dev (Hz)", max_dev, config.CALIB_MAX_TRANSIENT_FREQ_DEV)
    check("Oscillation period (s)", period, config.CALIB_OSCILLATION_PERIOD)
    print(f"{'Max dev agent (0-indexed)':<30} {max_dev_agent:>12d} {config.CALIB_MAX_DEV_AGENT:>12d} "
          f"{'OK' if max_dev_agent == config.CALIB_MAX_DEV_AGENT else 'TUNE':>8}")

    env.close()
    print("\nCalibration complete. Adjust x_line if values don't match.")
    print(f"Current x_line = {args.x_line}")


def main():
    parser = argparse.ArgumentParser(
        description="Modified NE 39-Bus Multi-Agent VSG System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", help="Command to run")

    # Train
    p_train = sub.add_parser("train", help="Train SAC agents")
    p_train.add_argument("--mode", choices=["standalone", "simulink"], default="standalone")
    p_train.add_argument("--episodes", type=int, default=500)
    p_train.add_argument("--resume", type=str, default=None)
    p_train.add_argument("--seed", type=int, default=42)
    p_train.add_argument("--x-line", type=float, default=0.10)
    p_train.add_argument("--comm-delay", type=int, default=0)

    # Evaluate
    p_eval = sub.add_parser("evaluate", help="Generate paper figures")
    p_eval.add_argument("--mode", choices=["standalone", "simulink"], default="standalone")
    p_eval.add_argument("--checkpoint", type=str, default="checkpoints/best.pt")
    p_eval.add_argument("--fig", type=int, default=None, help="Generate single figure (17-21)")

    # Test
    p_test = sub.add_parser("test", help="Quick integration test")
    p_test.add_argument("--mode", choices=["standalone", "simulink"], default="standalone")
    p_test.add_argument("--x-line", type=float, default=0.10)

    # Build model
    sub.add_parser("build-model", help="Build modified Simulink model (requires MATLAB)")

    # Calibrate
    p_calib = sub.add_parser("calibrate", help="Calibrate standalone env")
    p_calib.add_argument("--mode", choices=["standalone", "simulink"], default="standalone")
    p_calib.add_argument("--x-line", type=float, default=0.10)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    commands = {
        "train": cmd_train,
        "evaluate": cmd_evaluate,
        "test": cmd_test,
        "build-model": cmd_build_model,
        "calibrate": cmd_calibrate,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
