"""Tests for utils.training_callback — callback ABC and CallbackList."""
import numpy as np
import pytest

from utils.training_callback import CallbackList, EpisodeResult, TrainingCallback
from utils.monitor import TrainingMonitor


def _make_result(episode: int = 0, rewards: float = -100.0) -> EpisodeResult:
    return EpisodeResult(
        episode=episode,
        rewards=rewards,
        reward_components={"r_f": rewards, "r_h": 0.0, "r_d": 0.0},
        actions=np.zeros((10, 2, 2)),
        info={"tds_failed": False, "max_freq_deviation_hz": 0.1},
    )


# ── ABC contract ─────────────────────────────────────────────────────────────

def test_training_callback_is_abstract():
    """Cannot instantiate TrainingCallback directly."""
    with pytest.raises(TypeError):
        TrainingCallback()  # type: ignore[abstract]


def test_training_callback_defaults_do_not_raise():
    """on_training_start / on_training_end have no-op defaults."""

    class MinimalCb(TrainingCallback):
        def on_episode_end(self, result: EpisodeResult) -> bool:
            return False

    cb = MinimalCb()
    cb.on_training_start()          # must not raise
    cb.on_training_end(False)       # must not raise
    cb.on_training_end(True)        # must not raise


# ── CallbackList ──────────────────────────────────────────────────────────────

def test_callbacklist_continues_when_all_return_false():
    class NeverStop(TrainingCallback):
        def on_episode_end(self, result: EpisodeResult) -> bool:
            return False

    cbs = CallbackList([NeverStop(), NeverStop()])
    assert cbs.on_episode_end(_make_result()) is False


def test_callbacklist_stops_on_first_true():
    calls = []

    class StopCb(TrainingCallback):
        def on_episode_end(self, result: EpisodeResult) -> bool:
            calls.append("stop")
            return True

    class AfterCb(TrainingCallback):
        def on_episode_end(self, result: EpisodeResult) -> bool:
            calls.append("after")
            return False

    cbs = CallbackList([StopCb(), AfterCb()])
    result = cbs.on_episode_end(_make_result())
    assert result is True
    assert calls == ["stop"]          # AfterCb never called


def test_callbacklist_broadcasts_lifecycle_hooks():
    started = []
    ended = []

    class LifecycleCb(TrainingCallback):
        def __init__(self, name: str):
            self.name = name

        def on_training_start(self) -> None:
            started.append(self.name)

        def on_episode_end(self, result: EpisodeResult) -> bool:
            return False

        def on_training_end(self, stopped_early: bool) -> None:
            ended.append((self.name, stopped_early))

    cbs = CallbackList([LifecycleCb("a"), LifecycleCb("b")])
    cbs.on_training_start()
    cbs.on_episode_end(_make_result())
    cbs.on_training_end(stopped_early=True)

    assert started == ["a", "b"]
    assert ended == [("a", True), ("b", True)]


# ── TrainingMonitor as callback ───────────────────────────────────────────────

def test_training_monitor_is_training_callback():
    assert issubclass(TrainingMonitor, TrainingCallback)


def test_training_monitor_on_episode_end_matches_log_and_check():
    """on_episode_end must return the same bool as log_and_check for the same data."""
    m1 = TrainingMonitor()
    m2 = TrainingMonitor()
    result = _make_result(episode=0, rewards=-50.0)

    via_callback = m1.on_episode_end(result)
    via_direct = m2.log_and_check(
        episode=result.episode,
        rewards=result.rewards,
        reward_components=result.reward_components,
        actions=result.actions,
        info=result.info,
        per_agent_rewards=result.per_agent_rewards,
        sac_losses=result.sac_losses,
    )
    assert via_callback == via_direct


def test_training_monitor_log_and_check_still_works_directly():
    """Existing callers of log_and_check must not be broken."""
    m = TrainingMonitor()
    stop = m.log_and_check(
        episode=0,
        rewards=-100.0,
        reward_components={"r_f": -100.0, "r_h": 0.0, "r_d": 0.0},
        actions=np.zeros((10, 2, 2)),
        info={"tds_failed": False, "max_freq_deviation_hz": 0.1},
    )
    assert isinstance(stop, bool)


def test_training_monitor_in_callback_list():
    """TrainingMonitor can be composed via CallbackList."""
    monitor = TrainingMonitor()
    cbs = CallbackList([monitor])
    cbs.on_training_start()
    stop = cbs.on_episode_end(_make_result(episode=0))
    assert isinstance(stop, bool)
    cbs.on_training_end(stopped_early=stop)
