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


def _lab(color):
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(int(color[i:i + 2], 16) / 255) for i in (1, 3, 5))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda v: v ** (1 / 3) if v > 0.008856 else 7.787 * v + 16 / 116
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def _delta_e2000(first, second):
    """Ecart perceptuel CIEDE2000 entre deux couleurs hexadecimales."""
    from math import atan2, cos, degrees, exp, hypot, radians, sin, sqrt
    (l1, a1, b1), (l2, a2, b2) = _lab(first), _lab(second)
    mean_c = (hypot(a1, b1) + hypot(a2, b2)) / 2
    g = 0.5 * (1 - sqrt(mean_c ** 7 / (mean_c ** 7 + 25 ** 7)))
    a1, a2 = (1 + g) * a1, (1 + g) * a2
    c1, c2 = hypot(a1, b1), hypot(a2, b2)
    h1, h2 = degrees(atan2(b1, a1)) % 360, degrees(atan2(b2, a2)) % 360
    dh = 0 if c1 * c2 == 0 else (h2 - h1 - 360 if h2 - h1 > 180 else h2 - h1 + 360 if h2 - h1 < -180 else h2 - h1)
    big_dh = 2 * sqrt(c1 * c2) * sin(radians(dh / 2))
    mean_l, mean_c = (l1 + l2) / 2, (c1 + c2) / 2
    mean_h = h1 + h2 if c1 * c2 == 0 else ((h1 + h2 + 360) / 2 if abs(h1 - h2) > 180 else (h1 + h2) / 2)
    tt = (1 - 0.17 * cos(radians(mean_h - 30)) + 0.24 * cos(radians(2 * mean_h))
          + 0.32 * cos(radians(3 * mean_h + 6)) - 0.20 * cos(radians(4 * mean_h - 63)))
    rc = 2 * sqrt(mean_c ** 7 / (mean_c ** 7 + 25 ** 7))
    sl = 1 + 0.015 * (mean_l - 50) ** 2 / sqrt(20 + (mean_l - 50) ** 2)
    sc, sh = 1 + 0.045 * mean_c, 1 + 0.015 * mean_c * tt
    rt = -sin(radians(60 * exp(-((mean_h - 275) / 25) ** 2))) * rc
    return sqrt(((l2 - l1) / sl) ** 2 + ((c2 - c1) / sc) ** 2 + (big_dh / sh) ** 2
                + rt * ((c2 - c1) / sc) * (big_dh / sh))


@pytest.mark.parametrize('name,minimum', [('dark', 14), ('dark_colorblind', 14),
                                          ('light', 11.5), ('light_colorblind', 11.5)])
def test_reader_colors_stay_away_from_the_verdicts_of_the_same_theme(name, minimum):
    """La 1.7.12 reprenait le turquoise de PASSED et l'ambre de SKIPPED : en
    daltonien, la ligne d'un lecteur qui avait reussi prenait la couleur d'un
    echec. Chaque lecteur garde un ecart visible avec chaque verdict."""
    t.set_theme(name)
    verdicts = [t.status_color(status) for status in Status if status.is_final]
    for color in t.READER_COLORS:
        nearest = min(_delta_e2000(color, verdict) for verdict in verdicts)
        assert nearest >= minimum, (color, round(nearest, 1))


@pytest.mark.parametrize('name', ['dark', 'light', 'dark_colorblind', 'light_colorblind'])
def test_reader_colors_are_real_colors_not_greys(name):
    """Des lecteurs gris-bleus se ressemblaient tous : chaque couleur reste vive."""
    from math import hypot
    t.set_theme(name)
    for color in t.READER_COLORS:
        _, a, b = _lab(color)
        assert hypot(a, b) >= 30, color  # les gris-bleus de la 1.7.10 restaient sous 28


@pytest.mark.parametrize('name,filled', [('dark', False), ('dark_colorblind', False),
                                         ('light', True), ('light_colorblind', True)])
def test_light_themes_draw_reader_badges_filled_with_white_text(name, filled):
    from runner.ui import theme
    t.set_theme(name)
    color = t.reader_color(1)
    style = theme.reader_badge_style(color)
    assert (f"background-color: {color}; color: {t.ON_READER};" in style) is filled
    # Un lecteur exclu du prochain run reste en creux, quel que soit le theme.
    assert f"background-color: {color};" not in theme.reader_badge_style(color, actif=False)
    if filled:
        assert _contrast(t.ON_READER, color) >= 4.5
