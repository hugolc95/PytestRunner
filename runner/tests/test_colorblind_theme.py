"""Regression tests for colorblind-friendly light and dark palettes."""
from __future__ import annotations
import pytest
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
@pytest.mark.parametrize("name",["dark_colorblind","light_colorblind"])
def test_reader_colors_are_distinct(name):
    t.set_theme(name); colors={t.reader_color(i) for i in range(len(t.READER_COLORS))}; assert len(colors)==len(t.READER_COLORS)>=5
