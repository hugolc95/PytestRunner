"""Presentation riche des reglages ; les donnees accessibles restent en texte."""
from html import escape
import re

from runner.domain.models import Status
from runner.ui import tokens as t


MAX_ROWS = 6


def _gap(height):
    return f'<tr><td height="{height}" style="font-size:1px">&nbsp;</td></tr>'


def _text(value, limit=None):
    text = str(value)
    if limit and len(text) > limit:
        text = text[:limit - 1] + '…'
    # Les chemins longs doivent pouvoir revenir a la ligne sans elargir la bulle.
    text = re.sub(r'([^\s/._-]{28})', lambda match: match[0] + '\u200b', text)
    return escape(text).replace('\n', '<br>').replace('/', '/\u200b').replace('.', '.\u200b')


def profile_yaml_tooltip(title, annotation, *, membership='', description='', problems=(), read_only=False, extra='', font_scale=1):
    scale = max(1, font_scale)
    def px(size):
        return int(size * scale + .5)
    amber = '#f2bb55' if t.is_dark() else '#875500'
    inherited_color = t.ACCENT
    muted = t.TEXT_MUTED
    foreground = t.TEXT
    background = t.BG_RAISED
    panel = t.BG_INPUT if t.is_dark() else t.BG_APP
    parts = [f'<qt><table width="{px(410)}" cellspacing="0" cellpadding="0" bgcolor="{background}">',
             f'<tr><td><span style="font-size:{px(10)}px; color:{muted}">YAML SETTINGS</span><br>',
             f'<span style="font-size:{px(15)}px; font-weight:600; color:{foreground}">{_text(title, 90)}</span>']
    if membership:
        parts.append(f'<br><span style="font-size:{px(11)}px; color:{muted}">Group · {_text(membership, 130)}</span>')
    if description:
        parts.append(f'<br><span style="font-size:{px(11)}px; color:{muted}">{_text(description, 150)}</span>')
    parts.append('</td></tr>' + _gap(8))
    if problems:
        color = t.status_color(Status.FAILED)
        parts.append(f'<tr><td><b style="color:{color}">Configuration problem</b><br>'
                     f'<span style="color:{foreground}">{_text(chr(10).join(problems), 650)}</span></td></tr>')
    else:
        custom = annotation.get('custom_entries', [])
        inherited = annotation.get('inherited_entries', [])
        count = annotation.get('customized_tests')
        if count:
            parts.append(f'<tr><td style="color:{muted}; font-size:{px(11)}px">{count} of '
                         f'{annotation["total_tests"]} tests have their own values.</td></tr>')
        remaining = max(2, int(MAX_ROWS / scale))
        shown = 0
        custom_label = 'CUSTOMIZED IN TESTS' if count else 'CUSTOMIZED HERE'
        for rows, label, color, own in ((custom, custom_label, amber, True),
                                        (inherited, 'FROM GROUPS', inherited_color, False)):
            visible = rows[:remaining]
            if not visible:
                continue
            parts.append(_gap(4) + '<tr><td>'
                         f'<span style="color:{color}; font-size:{px(10)}px; font-weight:600">{label}</span>'
                         '</td></tr>' + _gap(4))
            for row in visible:
                caption = 'Group default' if annotation.get('scope') == 'group' else 'Value used'
                size = px(19 if len(row['value']) <= 16 else 13)
                parts.append(f'<tr><td bgcolor="{panel}"><table width="100%" cellpadding="{px(7)}" cellspacing="0">'
                             f'<tr><td><span style="font-family:monospace; font-size:{px(12)}px; font-weight:600; color:{foreground}">'
                             f'{_text(row["parameter"], 85)}</span><br>'
                             f'<span style="font-size:{px(10)}px; color:{muted}">{caption}</span></td>'
                             f'<td width="{px(100)}" align="right" valign="middle"><span style="color:{color}; '
                             f'font-size:{size}px; font-weight:700">{_text(row["value"], 100)}</span></td></tr>')
                if own:
                    detail = f'Inherited value: <b>{_text(row["inherited"], 100)}</b>'
                    if row.get('origin'):
                        detail += ' · ' + _text(row['origin'], 110)
                    if row.get('same'):
                        detail += '<br>Same value, explicitly saved here.'
                else:
                    detail = 'Defined by: ' + _text(row['origin'], 140)
                parts.append(f'<tr><td colspan="2"><span style="font-size:{px(11)}px; color:{muted}">{detail}</span>'
                             '</td></tr></table></td></tr>' + _gap(5))
            remaining -= len(visible)
            shown += len(visible)
        more = len(custom) + len(inherited) - shown
        if more:
            parts.append(f'<tr><td style="font-size:{px(11)}px; color:{muted}">+ {more} more parameters in the full YAML preview.</td></tr>')
    if extra:
        parts.append(f'<tr><td style="font-size:{px(11)}px; color:{muted}">{_text(extra, 350)}</td></tr>')
    footer = ('Edit in Execution Profiles · future runs' if read_only else 'Right-click → Edit YAML parameters…')
    parts.append(_gap(6) + f'<tr><td style="font-size:{px(11)}px; color:{muted}">{footer}</td></tr></table></qt>')
    return ''.join(parts)
