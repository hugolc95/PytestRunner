"""Regression tests for colorblind-friendly light and dark palettes."""
from __future__ import annotations
import pytest
from colorsys import rgb_to_hsv
from runner.domain.models import Status
from runner.ui import tokens as t
@pytest.fixture(autouse=True)
def restore_theme():
    previous=t.current_theme(); yield; t.set_theme(previous)
def _luminance(color):
    channels=[]
    for i in (1,3,5):
        value=int(color[i:i+2],16)/255; channels.append(value/12.92 if value<=.03928 else ((value+.055)/1.055)**2.4)
    r,g,b=channels; return .2126*r+.7152*g+.0722*b
def _contrast(a,b):
    x,y=_luminance(a),_luminance(b); return (max(x,y)+.05)/(min(x,y)+.05)
def test_colorblind_palettes_define_every_regular_theme_token():
    assert set(t.COLORBLIND_DARK)==set(t.DARK)
    assert set(t.COLORBLIND_LIGHT)==set(t.LIGHT)
@pytest.mark.parametrize("name,base",[("dark_colorblind","dark"),("light_colorblind","light")])
def test_colorblind_is_independent_from_base_theme(name,base):
    t.set_theme(name); assert t.is_colorblind(); assert t.base_theme()==base; assert t.is_dark()==(base=="dark")
@pytest.mark.parametrize("name",["dark_colorblind","light_colorblind"])
def test_colorblind_statuses_avoid_normal_green_red_pair(name):
    t.set_theme(name); passed=t.status_color(Status.PASSED); failed=t.status_color(Status.FAILED)
    assert passed not in (t.DARK["STATUS_COLORS"][Status.PASSED],t.LIGHT["STATUS_COLORS"][Status.PASSED])
    assert failed not in (t.DARK["STATUS_COLORS"][Status.FAILED],t.LIGHT["STATUS_COLORS"][Status.FAILED]); assert passed!=failed
@pytest.mark.parametrize("name",["dark_colorblind","light_colorblind"])
def test_colorblind_statuses_remain_visible(name):
    t.set_theme(name)
    for status in (Status.PASSED,Status.FAILED,Status.SKIPPED,Status.ERROR,Status.RUNNING): assert _contrast(t.status_color(status),t.BG_SURFACE)>=3.0,status
    assert _contrast(t.ON_RUN,t.RUN)>=4.0; assert _contrast(t.ON_ACCENT,t.ACCENT)>=4.0
def test_light_colorblind_statuses_have_strong_contrast():
    t.set_theme("light_colorblind")
    for status in (Status.PASSED,Status.FAILED,Status.SKIPPED,Status.ERROR,Status.RUNNING,Status.PENDING):
        assert _contrast(t.status_color(status),t.BG_SURFACE)>=6.0,status
def test_light_colorblind_failed_and_skipped_use_different_hue_families():
    t.set_theme("light_colorblind")
    failed=t.status_color(Status.FAILED).lower(); skipped=t.status_color(Status.SKIPPED).lower()
    assert failed=="#a83200"
    assert skipped=="#5b2aa8"
    assert failed!=skipped
@pytest.mark.parametrize("name",["dark_colorblind","light_colorblind"])
def test_reader_colors_are_distinct(name):
    t.set_theme(name); colors={t.reader_color(i) for i in range(len(t.READER_COLORS))}; assert len(colors)==len(t.READER_COLORS)>=5
def test_tree_icons_use_balanced_intermediate_size():
    assert t.TREE_ICON_SIZE==18


def _hue(color):
    return rgb_to_hsv(*(int(color[i:i+2], 16) / 255 for i in (1, 3, 5)))[0] * 360


@pytest.mark.parametrize('name', ['dark', 'light', 'dark_colorblind', 'light_colorblind'])
def test_reader_identity_has_distinct_hues_and_readable_labels(name):
    t.set_theme(name)
    verdicts = {t.status_color(status) for status in Status if status.is_final}
    for color in t.READER_COLORS:
        assert color not in verdicts
        assert _contrast(color, t.BG_SURFACE) >= 4.5
        selected = t.blend(color, t.BG_SURFACE, .14)
        assert _contrast(color, selected) >= 4.5
    assert t.reader_color(len(t.READER_COLORS)) == t.reader_color(0)
    hues = [_hue(color) for color in t.READER_COLORS]
    for index, hue in enumerate(hues):
        for other in hues[index + 1:]:
            distance = abs(hue - other)
            assert min(distance, 360 - distance) >= 25


@pytest.mark.parametrize('name', ['dark_colorblind', 'light_colorblind', 'colorblind'])
def test_passed_cannot_be_confused_with_checkboxes_or_launch_controls(name):
    t.set_theme(name)
    passed = t.status_color(Status.PASSED)
    assert 145 <= _hue(passed) <= 180
    for control in (t.ACCENT, t.RUN):
        assert 195 <= _hue(control) <= 235
        assert abs(_hue(passed) - _hue(control)) >= 30
    for status in Status:
        if status.is_final:
            assert _contrast(t.status_color(status), t.BG_SURFACE) >= 4.5


@pytest.mark.parametrize('name', ['dark_colorblind', 'light_colorblind'])
def test_difference_highlight_is_not_a_verdict_color(name):
    t.set_theme(name)
    color = t.divergent_color()
    assert color not in {t.status_color(status) for status in Status if status.is_final}
    assert _contrast(color, t.BG_SURFACE) >= 4.5
