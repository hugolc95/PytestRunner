"""Regression tests for the colorblind-friendly application palette."""

from __future__ import annotations

import pytest

from runner.domain.models import Status
from runner.ui import tokens as t


@pytest.fixture(autouse=True)
def restore_theme():
    previous = t.current_theme()
    yield
    t.set_theme(previous)


def _luminance(color: str) -> float:
    channels = []
    for i in (1, 3, 5):
        value = int(color[i:i + 2], 16) / 255
        channels.append(
            value / 12.92
            if value <= 0.03928
            else ((value + 0.055) / 1.055) ** 2.4
        )
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(foreground: str, background: str) -> float:
    a, b = _luminance(foreground), _luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def test_colorblind_palette_defines_every_regular_theme_token():
    assert set(t.COLORBLIND) == set(t.DARK) == set(t.LIGHT)


def test_colorblind_theme_can_be_selected_and_restored():
    t.set_theme("colorblind")

    assert t.current_theme() == "colorblind"
    assert t.TEXT == t.COLORBLIND["TEXT"]
    assert t.status_color(Status.PASSED) == "#56b4e9"
    assert t.status_color(Status.FAILED) == "#d55e00"


def test_colorblind_statuses_do_not_use_the_normal_green_red_pair():
    t.set_theme("colorblind")

    passed = t.status_color(Status.PASSED)
    failed = t.status_color(Status.FAILED)

    assert passed != t.DARK["STATUS_COLORS"][Status.PASSED]
    assert failed != t.DARK["STATUS_COLORS"][Status.FAILED]
    assert passed != failed


def test_colorblind_statuses_remain_visible_on_the_surface():
    t.set_theme("colorblind")

    for status in (Status.PASSED, Status.FAILED, Status.SKIPPED,
                   Status.ERROR, Status.RUNNING):
        assert _contrast(t.status_color(status), t.BG_SURFACE) >= 3.0, status

    assert _contrast(t.ON_RUN, t.RUN) >= 4.0
    assert _contrast(t.ON_ACCENT, t.ACCENT) >= 4.0


def test_colorblind_reader_colors_are_not_all_variants_of_one_hue():
    t.set_theme("colorblind")

    colors = {t.reader_color(index) for index in range(len(t.READER_COLORS))}
    assert len(colors) == len(t.READER_COLORS)
    assert len(colors) >= 5
