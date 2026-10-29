"""Survol riche : lisibilite, acces complet aux valeurs et suivi du theme."""
import copy

import pytest
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QTextDocument, QHelpEvent
from PySide6.QtWidgets import QToolTip

from runner.domain.execution_profile import ExecutionProfile, ProfileStore
from runner.domain.profile_configuration import configuration_annotation, aggregate_annotations
from runner.ui import tokens as t
from runner.ui.execution_profiles_page import ExecutionProfilesPage
from runner.ui.profile_yaml_tooltip import profile_yaml_tooltip, MAX_ROWS

GROUP = dict(id='t1', name='Qualification T1', color='#a675ed', description='T1 qualification.',
             configuration_overrides={'protocol': 'T1'})


@pytest.fixture(autouse=True)
def palette(qapp):
    previous = t.current_theme()
    yield
    QToolTip.hideText()
    t.set_theme(previous)


def plain(rich):
    document = QTextDocument()
    document.setHtml(rich)
    return document.toPlainText().replace('\u200b', '')


@pytest.mark.parametrize('theme', ['dark', 'light', 'dark_colorblind', 'light_colorblind'])
def test_rich_values_and_origins_render_in_each_palette(theme):
    t.set_theme(theme)
    annotation = configuration_annotation({'protocol': 'T0', 'timeout': 15}, [GROUP], {'timeout': 75})
    original = copy.deepcopy(annotation)
    rich = profile_yaml_tooltip('test_read_atr', annotation, membership='Qualification T1')
    text = plain(rich)
    assert 'CUSTOMIZED HERE' in text and 'FROM GROUPS' in text
    assert '75' in text and 'Inherited value: 15' in text
    assert 'T1' in text and 'Defined by: Group: Qualification T1' in text
    assert t.TEXT_MUTED in rich and t.ACCENT in rich and t.BG_RAISED in rich
    assert annotation == original


def test_group_defaults_and_same_value_customizations_remain_explicit():
    annotation = configuration_annotation({'protocol': 'T1'}, [GROUP])
    text = plain(profile_yaml_tooltip('Qualification T1', annotation))
    assert 'Group default' in text
    assert 'Same value, explicitly saved here.' in text


def test_user_content_is_literal_text_in_titles_names_values_and_diagnostics():
    value = '<img src="https://invalid.test/x"> & <b>literal</b>'
    annotation = configuration_annotation({}, [], {'<b>parameter</b>': value})
    rich = profile_yaml_tooltip('<b>title</b>', annotation, membership='<script>group</script>')
    text = plain(rich)
    assert '<b>title</b>' in text and '<b>parameter</b>' in text
    assert value in text
    assert '<img ' not in rich and '<script>' not in rich
    diagnostic = plain(profile_yaml_tooltip('test', annotation, problems=['Invalid <mapping> & "quoted"']))
    assert 'Configuration problem' in diagnostic and 'Invalid <mapping> & "quoted"' in diagnostic


def test_large_tooltip_is_bounded_without_losing_parameters_in_the_profile():
    annotation = configuration_annotation({}, [], {f'parameter_{i}': i for i in range(30)})
    text = plain(profile_yaml_tooltip('test_many_parameters', annotation))
    assert text.count('Value used') == MAX_ROWS
    assert '+ 24 more parameters' in text
    assert len(annotation['custom_entries']) == 30


def test_folder_summary_describes_child_customizations_without_claiming_a_group_default():
    first = configuration_annotation({'timeout': 15}, [], {'timeout': 25})
    second = configuration_annotation({'timeout': 15}, [], {'timeout': 30})
    summary = aggregate_annotations([first, first, second])
    assert len(summary['custom_entries']) == 2
    text = plain(profile_yaml_tooltip('Tests', summary))
    assert '3 of 3 tests have their own values.' in text
    assert 'CUSTOMIZED IN TESTS' in text
    assert '25' in text and '30' in text


def test_live_context_explains_that_edits_apply_to_future_runs():
    annotation = configuration_annotation({}, [], {'timeout': 75})
    text = plain(profile_yaml_tooltip('test_read', annotation, read_only=True))
    assert 'future runs' in text and 'Execution Profiles' in text


def test_large_interface_font_scales_tooltip_and_reduces_rows_without_changing_values():
    annotation = configuration_annotation({}, [], {f'parameter_{i}': i for i in range(12)})
    rich = profile_yaml_tooltip('test', annotation, font_scale=1.5)
    assert 'font-size:29px' in rich
    assert plain(rich).count('Value used') == 4
    assert '+ 8 more parameters' in plain(rich)
    assert len(annotation['custom_entries']) == 12


def test_native_tooltip_updates_on_hover_after_theme_change_without_mutating_editor(qtbot, tmp_path, qapp):
    page = ExecutionProfilesPage(ProfileStore(tmp_path / 'profiles'))
    qtbot.addWidget(page)
    profile = ExecutionProfile('Protocols', ['test_card.py::test_read'], 'config.yaml', 'timeout: 15\n',
        profile_id=page.current_profile().profile_id, step_overrides=[{'timeout': 75}])
    page._profiles[page.profile_list.currentRow()] = profile
    page._populate(profile)
    page.resize(1200, 800)
    page.show()
    index = page.sequence_list.indexFromItem(page._step_items()[0])
    original = page._profile_from_editor()
    accessible = index.data(Qt.AccessibleDescriptionRole)
    assert 'Value used: 75' in accessible and '<qt>' not in accessible
    for theme in ('dark', 'light'):
        t.set_theme(theme)
        pos = page.sequence_list.visualRect(index).center()
        event = QHelpEvent(QEvent.ToolTip, pos, page.sequence_list.viewport().mapToGlobal(pos))
        qapp.sendEvent(page.sequence_list.viewport(), event)
        qtbot.waitUntil(QToolTip.isVisible)
        assert QToolTip.text().startswith('<qt>')
        assert t.BG_RAISED in QToolTip.text()
        assert 'Inherited value: 15' in plain(QToolTip.text())
        assert index.data(Qt.AccessibleDescriptionRole) == accessible
        QToolTip.hideText()
    assert page._profile_from_editor() == original
