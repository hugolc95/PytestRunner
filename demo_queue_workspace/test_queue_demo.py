"""Predictable long runs with visible progress, without hardware dependencies."""
import os
import time

import pytest


def simulate_activity(seconds, *, lines_per_tick=1):
    scale = float(os.environ.get("PYTEST_RUNNER_DEMO_TIME_SCALE", "1"))
    if not 0 < scale <= 10:
        raise ValueError("PYTEST_RUNNER_DEMO_TIME_SCALE must be in (0, 10]")
    ticks = seconds * 10
    started = time.monotonic()
    for tick in range(ticks):
        for line in range(lines_per_tick):
            print(f"[demo] progress={tick + 1}/{ticks} message={line + 1}", flush=True)
        deadline = started + (tick + 1) * 0.1 * scale
        time.sleep(max(0, deadline - time.monotonic()))


@pytest.mark.long_run
class TestRunLong90Seconds:
    @pytest.mark.parametrize("step", range(1, 7), ids=lambda step: f"step_{step:02d}_15s")
    def test_activity(self, step):
        simulate_activity(15)
        assert step > 0


@pytest.mark.queue_one
class TestQueueOne40Seconds:
    @pytest.mark.parametrize("step", range(1, 5), ids=lambda step: f"step_{step:02d}_10s")
    def test_activity(self, step):
        simulate_activity(10)
        assert step > 0


@pytest.mark.queue_two
class TestQueueTwo30Seconds:
    @pytest.mark.parametrize("step", range(1, 4), ids=lambda step: f"step_{step:02d}_10s")
    def test_activity(self, step):
        simulate_activity(10)
        assert step > 0


@pytest.mark.output_stress
class TestOutputStress30Seconds:
    @pytest.mark.parametrize("step", range(1, 4), ids=lambda step: f"step_{step:02d}_10s")
    def test_activity(self, step):
        simulate_activity(10, lines_per_tick=20)
        assert step > 0
