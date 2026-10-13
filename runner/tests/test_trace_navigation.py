"""Real Qt source jumps and safe, mocked native IDE launches."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QTextCursor

from runner.domain.trace_locations import TraceLocation, SourceNavigationError, references, resolve_location, project_for_file
from runner.ui import external_editor
from runner.ui.trace_browser import TraceBrowser, linked_line
from runner.ui.main_window import MainWindow
from runner.ui.widgets import ErrorDialog


@pytest.mark.parametrize("text,path,line,column", [
    ('  File "C:\\Projet démo\\card.py", line 42, in initialize', r'C:\Projet démo\card.py', 42, 1),
    (r'\\server\share\test_card.py:9: TypeError', r'\\server\share\test_card.py', 9, 1),
    ('tests/test_card.py:3:7: SyntaxError', 'tests/test_card.py', 3, 7),
    ('E   /tmp/space here/été.py:12: ValueError', '/tmp/space here/été.py', 12, 1),
    ("  File 'relative.py', line 2", 'relative.py', 2, 1),
])
def test_reference_formats_and_encoded_round_trip(text, path, line, column):
    found = list(references(text, 'C:/space project'))
    assert len(found) == 1
    loc = found[0][2]
    assert (loc.path, loc.line, loc.column) == (path, line, column)
    assert TraceLocation.from_href(QUrl(loc.href()).toString(QUrl.FullyEncoded)) == loc


@pytest.mark.parametrize("text", ['File "<string>", line 2', '<frozen importlib>:12',
                                        'https://example.org/test.py:12', 'ValueError: no file'])
def test_non_file_text_is_not_linked(text):
    assert not list(references(text))


@pytest.mark.parametrize("href", ['https://example.com', 'pytestrunner-source:garbage',
    'pytestrunner-source:%7B%22path%22%3A%22x.py%22%2C%22line%22%3Atrue%7D',
    'pytestrunner-source:%7B%22path%22%3A%22x.py%22%2C%22line%22%3A-1%7D'])
def test_invalid_links_are_rejected(href):
    assert TraceLocation.from_href(href) is None


def test_resolver_uses_exact_context_and_refuses_ambiguity(tmp_path):
    source = tmp_path / 'test_card.py'
    source.write_text('pass\n')
    sub = tmp_path / 'sub'
    sub.mkdir()
    other = sub / source.name
    other.write_text('pass\n')
    loc = TraceLocation(source.name, 1, workspace=str(tmp_path))
    assert resolve_location(loc) == source
    with pytest.raises(SourceNavigationError, match='several files'):
        resolve_location(loc, nodeid='sub/test_card.py::test_card')
    assert resolve_location(TraceLocation(source.as_uri(), 1)) == source
    with pytest.raises(SourceNavigationError, match='not found'):
        resolve_location(TraceLocation('moved.py', 2), str(tmp_path))
    with pytest.raises(SourceNavigationError, match='unknown'):
        resolve_location(TraceLocation(source.name, 2, context_required=True), str(tmp_path))
    if sys.platform != 'win32':
        with pytest.raises(SourceNavigationError, match='Windows path'):
            resolve_location(TraceLocation(r'C:\tests\test_card.py', 2))


def test_project_and_matching_multiroot_workspace(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'pyproject.toml').write_text('')
    file = project / 'test_card.py'
    file.write_text('pass')
    descriptor = project / 'card.code-workspace'
    descriptor.write_text('{"folders":[{"path":"."}]}')
    assert project_for_file(file, str(tmp_path)) == descriptor
    assert project_for_file(file, str(tmp_path), 'pycharm') == project
    descriptor.write_text('[]')
    assert project_for_file(file, str(tmp_path)) == project
    descriptor.write_text('{// workspace\n"folders":[{"path":".",},],}')
    assert project_for_file(file, str(tmp_path)) == descriptor
    descriptor.unlink()
    outer = tmp_path / 'multi.code-workspace'
    outer.write_text('{"folders":[{"path":"project"},{"path":"other"}]}')
    assert project_for_file(file, str(project)) == outer


@pytest.mark.parametrize("preference,available,expected", [
    ('Automatic', {'vscode', 'pycharm'}, 'VS Code'),
    ('Automatic', {'pycharm'}, 'PyCharm'),
    ('PyCharm', {'pycharm', 'vscode'}, 'PyCharm'),
    ('PyCharm', {'vscode'}, 'VS Code'),
])
def test_external_editor_priority_and_project_line_arguments(tmp_path, monkeypatch, preference, available, expected):
    (tmp_path / '.git').mkdir()
    folder = tmp_path / 'sources'
    folder.mkdir()
    file = folder / 'été & name.py'
    file.write_text('pass')
    monkeypatch.setattr(external_editor, 'find_editor', lambda kind, configured='':
                        Path('/editor/' + kind) if kind in available else None)
    calls = []
    monkeypatch.setattr(external_editor.subprocess, 'Popen', lambda args, **kwargs: calls.append((args, kwargs)))
    assert external_editor.open_external(TraceLocation(str(file), 12, 3), file, str(tmp_path),
                                         {'external_editor': preference}) == expected
    args, kwargs = calls[0]
    assert args[1] == str(tmp_path)
    assert kwargs == {'cwd': str(tmp_path)}
    assert '--reuse-window' not in args and '--new-window' not in args
    assert f'{file}:12:3' in args if expected == 'VS Code' else args[-1] == str(file)


def test_missing_editors_and_invalid_setting_are_explained(tmp_path, monkeypatch):
    with pytest.raises(SourceNavigationError, match='Settings'):
        external_editor.find_editor('vscode', str(tmp_path / 'missing.exe'))
    monkeypatch.setattr(external_editor, 'find_editor', lambda *args: None)
    with pytest.raises(SourceNavigationError, match='Neither VS Code nor PyCharm'):
        external_editor.open_external(TraceLocation('test.py', 2), tmp_path / 'test.py', str(tmp_path), {})


def test_windows_cmd_launcher_uses_native_exe(tmp_path, monkeypatch):
    bin = tmp_path / 'bin'
    bin.mkdir()
    cmd = bin / 'code.cmd'
    cmd.write_text('')
    exe = tmp_path / 'Code.exe'
    exe.write_text('')
    monkeypatch.setattr(external_editor.sys, 'platform', 'win32')
    assert external_editor.find_editor('vscode', str(cmd)) == exe


def test_browser_plaintext_selection_and_link_clicks(qtbot):
    browser = TraceBrowser()
    qtbot.addWidget(browser)
    text = '  File "été & card.py", line 3\nValueError: <bad>'
    browser.setPlainText(text)
    assert browser.toPlainText() == text
    assert browser.document().toHtml().count('pytestrunner-source:') == 1
    hits = []
    browser.source_requested.connect(lambda *args: hits.append(args))
    location = TraceLocation('été & card.py', 3)
    browser.anchorClicked.emit(QUrl(location.href()))
    assert hits == [(location, False)]
    browser.anchorClicked.emit(QUrl('https://example.com'))
    assert len(hits) == 1
    browser.setHtml('<pre>' + linked_line(text.splitlines()[0]) + '</pre>')
    assert browser.toPlainText() == text.splitlines()[0]
    browser.restyle()


def test_source_same_buffer_failed_save_and_stale_lines(qtbot, tmp_path, monkeypatch):
    from runner.ui.source_panel import SourcePanel
    source = SourcePanel()
    qtbot.addWidget(source)
    path = tmp_path / 'card.py'
    path.write_text('first\nsecond\nthird\n')
    other = tmp_path / 'other.py'
    other.write_text('other')
    assert source.open_location(path, 2, 3)
    assert (source.editor.textCursor().blockNumber(), source.editor.textCursor().positionInBlock()) == (1, 2)
    source.set_editable(True)
    source.editor.appendPlainText('unsaved')
    before = source.editor.toPlainText()
    monkeypatch.setattr('runner.ui.source_panel.write_source', lambda *args: 'Disk full')
    assert source.open_location(path, 1)
    assert source.dirty and source.editor.toPlainText() == before
    assert not source.open_location(other, 1)
    assert source.path() == path and source.editor.toPlainText() == before
    source.clear()
    assert source.dirty and source.path() == path
    returned = []
    source.open_location(path, 999, on_return=lambda: returned.append(True))
    assert 'no longer exists' in source.status_label.text()
    source.back_button.click()
    assert returned == [True]
    source._timer.stop()


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from runner.domain import history
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat)
    monkeypatch.setattr('runner.ui.main_window.QSettings', lambda *_: settings)
    monkeypatch.setattr(history, 'dossier', lambda: tmp_path / 'history')
    monkeypatch.setattr(MainWindow, '_restore', lambda self: None)
    w = MainWindow()
    qtbot.addWidget(w)
    from runner.domain.workspace import Workspace
    w.workspace = Workspace.load(str(tmp_path))
    w.resize(1440, 900)
    w.show()
    yield w
    w.close()


def test_details_click_opens_exact_line_and_returns(window, tmp_path, qtbot):
    path = tmp_path / 'test_card.py'
    path.write_text('def test_card():\n    raise ValueError("card")\n')
    body = window.results.detail.body
    body.setHtml(window.results.detail._html_trace(f'{path}:2: ValueError: card'))
    window.results.show_tab(0)
    qtbot.wait(20)
    # A real viewport mouse click follows the actual encoded QTextBrowser anchor.
    cursor = QTextCursor(body.document())
    cursor.setPosition(5)
    position = body.cursorRect(cursor).center()
    assert body.anchorAt(position)
    qtbot.mouseClick(body.viewport(), Qt.LeftButton, pos=position)
    assert window.results.tabs.currentIndex() == 1
    assert window.results.source.path() == path
    assert window.results.source.editor.textCursor().blockNumber() == 1
    window.results.source.back_button.click()
    assert window.results.tabs.currentIndex() == 0


def test_control_click_forces_external_editor(window, tmp_path, qtbot, monkeypatch):
    path = tmp_path / 'test_card.py'
    path.write_text('pass')
    body = window.results.detail.body
    body.setHtml(window.results.detail._html_trace(f'{path}:1: AssertionError'))
    calls = []
    monkeypatch.setattr(external_editor, 'open_external', lambda *args: calls.append(args) or 'VS Code')
    cursor = QTextCursor(body.document())
    cursor.setPosition(5)
    qtbot.mouseClick(body.viewport(), Qt.LeftButton, Qt.ControlModifier, pos=body.cursorRect(cursor).center())
    assert len(calls) == 1 and calls[0][1] == path


def test_external_jump_saves_current_buffer_and_refuses_failed_save(window, tmp_path, monkeypatch):
    path = tmp_path / 'test_card.py'
    path.write_text('pass')
    source = window.results.source
    source.show_file(path)
    source.set_editable(True)
    source.editor.appendPlainText('# updated')
    calls = []
    monkeypatch.setattr(external_editor, 'open_external', lambda *args: calls.append(path.read_text()) or 'VS Code')
    assert window._open_source_reference(TraceLocation(str(path), 1), True)
    assert '# updated' in calls[0] and not source.dirty
    source.editor.appendPlainText('# still pending')
    monkeypatch.setattr('runner.ui.source_panel.write_source', lambda *args: 'Disk full')
    popups = []
    monkeypatch.setattr(ErrorDialog, 'show_error', lambda *args: popups.append(args))
    assert not window._open_source_reference(TraceLocation(str(path), 1), True)
    assert len(calls) == 1 and source.dirty
    assert popups[0][2] == 'Disk full'
    # This test intentionally simulates a failed save; preserve and stop it
    # without making the fixture's normal application close block on a dialog.
    source._timer.stop()
    monkeypatch.setattr('runner.ui.source_panel.write_source', lambda *args: '')


def test_force_external_dependencies_missing_files_and_settings(window, tmp_path, monkeypatch):
    path = tmp_path / 'test_card.py'
    path.write_text('pass')
    calls = []
    monkeypatch.setattr(external_editor, 'open_external', lambda *args: calls.append(args) or 'VS Code')
    assert window._open_source_reference(TraceLocation(str(path), 1), True)
    dep = tmp_path / '.venv' / 'site-packages' / 'dep.py'
    dep.parent.mkdir(parents=True)
    dep.write_text('pass')
    assert window._open_source_reference(TraceLocation(str(dep), 1))
    assert len(calls) == 2
    popups = []
    monkeypatch.setattr(ErrorDialog, 'show_error', lambda *args: popups.append(args))
    assert not window._open_source_reference(TraceLocation('missing.py', 1))
    assert 'not found' in popups[0][2]
    settings = window.preferences.settings_panel
    settings.controls['external_editor'].setCurrentIndex(2)
    settings.controls['vscode_path'].setText('/chosen/Code.exe')
    window.preferences.save()
    settings.controls['vscode_path'].setText('/bad')
    settings.cancel()
    assert settings.controls['vscode_path'].text() == '/chosen/Code.exe'
    assert calls[0][3]['external_editor'] == 'PyCharm'


def test_console_relative_paths_keep_event_project_and_no_link_bleed(window, tmp_path):
    console = window.preferences.console
    path = tmp_path / 'test_card.py'
    path.write_text('first\nsecond')
    window.preferences.context_record(window, 'errors', 'test_card.py:2: ValueError: example')
    console.refresh()
    html = console.text.toHtml()
    assert 'pytestrunner-source:' in html
    window.preferences.record('actions', 'Some unrelated action')
    console.refresh()
    end = QTextCursor(console.text.document())
    end.movePosition(QTextCursor.End)
    assert not end.charFormat().isAnchor()
    window.preferences.record('errors', 'test_card.py:2: project unknown')
    console.refresh()
    locations = []
    block = console.text.document().begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.charFormat().isAnchor():
                locations.append(TraceLocation.from_href(fragment.charFormat().anchorHref()))
            it += 1
        block = block.next()
    assert locations[-2].workspace == str(tmp_path)
    assert locations[-1].workspace == '' and locations[-1].context_required


def test_history_reference_uses_recorded_workspace(window, tmp_path, monkeypatch):
    history = window.history_dashboard
    history._execution_group = SimpleNamespace(workspace=str(tmp_path))
    history.execution_detail._nodeid = 'test_card.py::test_card'
    path = tmp_path / 'test_card.py'
    path.write_text('first\nsecond')
    history.execution_detail.source_requested.emit(TraceLocation('test_card.py', 2), False)
    assert window.results.source.path() == path
    window.results.source.back_button.click()
    assert window.pages.currentWidget() is window.history_page
    other = tmp_path / 'archived_project'
    other.mkdir()
    (other / 'test_card.py').write_text('pass')
    history._execution_group = SimpleNamespace(workspace=str(other))
    calls = []
    monkeypatch.setattr(external_editor, 'open_external', lambda *args: calls.append(args) or 'PyCharm')
    history.execution_detail.source_requested.emit(TraceLocation('test_card.py', 1), False)
    assert calls[0][1] == other / 'test_card.py'


def test_profile_jump_stays_readonly(window, tmp_path):
    path = tmp_path / 'test_card.py'
    path.write_text('first\nsecond')
    window.profile_results.detail.source_requested.emit(TraceLocation(str(path), 2), False)
    assert window.results_stack.currentWidget() is window.profile_result_page
    assert window.profile_results.source.path() == path
    assert not window.profile_results.source.edit_button.isEnabled()


def test_stress_reference_resolves_relative_to_its_test_and_keeps_attempt(window, tmp_path):
    from runner.domain.models import Reader, ReaderReport, Status
    from runner.domain.stress import MODE_N_TIMES, StressSummary, StressAttempt, StressReaderResult
    folder = tmp_path / 'nested'
    folder.mkdir()
    file = folder / 'test_card.py'
    file.write_text('first\nsecond')
    report = ReaderReport(reader=Reader('', 0), output=(
        '=================================== FAILURES ===================================\n'
        '_________________________ test_card _________________________\n'
        'test_card.py:2: ValueError\nE   ValueError: card unavailable\n'))
    attempt = StressAttempt(3, Status.FAILED, (StressReaderResult(report.reader, report, Status.FAILED),))
    panel = window.results.detail
    panel.show_stress_done('nested/test_card.py::test_card', StressSummary(
        mode=MODE_N_TIMES, cap=3, ran=3, passed=2, failed_attempts=[attempt]))
    assert 'pytestrunner-source:' in panel.stress_body.toHtml()
    panel.stress_body.source_requested.emit(TraceLocation('test_card.py', 2), False)
    assert window.results.source.path() == file
    window.results.source.back_button.click()
    assert panel.stack.currentIndex() == panel.PAGE_STRESS
    assert 'card unavailable' in panel.stress_body.toPlainText()


def test_console_selects_matching_run_and_reuses_open_project(window, tmp_path):
    from runner.domain.workspace import Workspace
    original = tmp_path / 'test_card.py'
    original.write_text('first\nsecond')
    child = window.run_tabs.new_run(window)
    second = tmp_path / 'another_project'
    second.mkdir()
    child.workspace = Workspace.load(str(second))
    file = second / 'test_card.py'
    file.write_text('first\nsecond\nthird')
    assert window._open_source_reference(TraceLocation(str(file), 3, workspace=str(second)))
    assert window.run_tabs.current.context is child
    assert child.results.source.path() == file
    # Jump back to the main context while another Run is selected.
    assert window._open_source_reference(TraceLocation(str(original), 2, workspace=str(tmp_path)))
    assert window.run_tabs.current.context is window
    assert window.results.source.path() == original


def test_real_collection_error_popup_link_navigates_to_broken_line(window, tmp_path, monkeypatch):
    from runner.domain import execution, diagnostics
    broken = tmp_path / 'test_bad_import.py'
    broken.write_text('import unavailable_trace_navigation_xyz\n')
    with pytest.raises(diagnostics.CollectionError) as raised:
        execution.collect(str(tmp_path), sys.executable)
    failure = raised.value
    assert str(broken.name) in failure.details
    def click_source(dialog):
        browser = dialog.detail_view
        block = browser.document().begin()
        found = None
        while block.isValid() and found is None:
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.charFormat().isAnchor():
                    loc = TraceLocation.from_href(fragment.charFormat().anchorHref())
                    if loc.path.endswith(broken.name):
                        found = loc
                        break
                it += 1
            block = block.next()
        assert found is not None and found.workspace == str(tmp_path)
        browser.source_requested.emit(found, False)
        return 1
    monkeypatch.setattr(ErrorDialog, 'exec', click_source)
    ErrorDialog.show_diagnostics(window, 'Collection failed', failure.details, workspace=failure.workspace)
    assert window.results.source.path() == broken
    assert window.results.source.editor.textCursor().blockNumber() == 0


def test_no_installed_editor_gives_visible_popup(window, tmp_path, monkeypatch):
    file = tmp_path / 'test_card.py'
    file.write_text('pass')
    monkeypatch.setattr(external_editor, 'find_editor', lambda *args: None)
    popups = []
    monkeypatch.setattr(ErrorDialog, 'show_error', lambda *args: popups.append(args))
    assert not window._open_source_reference(TraceLocation(str(file), 1), True)
    assert 'Neither VS Code nor PyCharm' in popups[0][2]
    assert 'Settings' in popups[0][2]


def test_real_failed_pytest_details_links_to_workspace_helper(window, tmp_path):
    from runner.domain.execution import ReaderRun
    from runner.domain.models import Reader, RunRequest, Status
    helper = tmp_path / 'card_backend.py'
    helper.write_text('def read_card():\n    raise ValueError("card unavailable")\n')
    (tmp_path / 'test_card.py').write_text('from card_backend import read_card\n\ndef test_card():\n    read_card()\n')
    reader = Reader('', 0)
    nodeid = 'test_card.py::test_card'
    report = ReaderRun(RunRequest(workspace=str(tmp_path), interpreter=sys.executable,
                                 nodeids=(nodeid,), readers=()), reader, {}).run(lambda line: None, lambda outcome: None)
    assert report.exit_code == 1 and 'card unavailable' in report.output
    window.results.set_readers((reader,))
    window.results.set_report(report)
    window.results.show_test(nodeid, {0: Status.FAILED}, str(tmp_path))
    browser = window.results.detail.body
    block = browser.document().begin()
    location = None
    while block.isValid() and location is None:
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.charFormat().isAnchor():
                value = TraceLocation.from_href(fragment.charFormat().anchorHref())
                if value.path.endswith(helper.name):
                    location = value
                    break
            it += 1
        block = block.next()
    assert location is not None
    browser.source_requested.emit(location, False)
    assert window.results.source.path() == helper
    assert window.results.source.editor.textCursor().blockNumber() == 1


def test_console_trimming_unicode_retains_exact_text(window):
    console = window.preferences.console
    console.clear()
    window.preferences.record('actions', '😀 first event')
    window.preferences.record('actions', 'second event')
    console.refresh()
    console.events.popleft()
    window.preferences.record('actions', 'third event')
    console.refresh()
    assert console.text.toPlainText().startswith(console._rendered[0])
    assert console.text.toPlainText() == '\n'.join(console._rendered)

