"""Shared presentation of durations; stored values remain seconds."""

from __future__ import annotations

import math


def format_duration(seconds: float | None, precision: int = 1) -> str:
    """Use seconds, minutes or hours, retaining precision for short tests.

    Round before splitting units so rounding can never display ``60s``.
    Unknown/non-finite measurements are not displayed as a fake zero.
    """
    if seconds is None or not math.isfinite(seconds):
        return "—"
    scale = 10 ** precision
    ticks = round(max(0.0, seconds) * scale)
    hours, ticks = divmod(ticks, 3600 * scale)
    minutes, ticks = divmod(ticks, 60 * scale)
    remainder = f"{ticks / scale:.{precision}f}"
    if not hours and not minutes:
        return f"{remainder}s"
    if precision:
        remainder = remainder.rstrip("0").rstrip(".")
    parts = [f"{hours} h"] if hours else []
    parts.extend((f"{minutes} min", f"{remainder}s"))
    return " ".join(parts)
