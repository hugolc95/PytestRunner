"""Le demarrage suit les memes chemins que les verdicts, dans chaque suite."""
import sys

import pytest

from runner.domain import parsing
from runner.domain.execution import ReaderRun
from runner.domain.models import Reader, RunRequest, Status


@pytest.mark.parametrize('configuration', ['ini', 'toml', 'none'])
@pytest.mark.parametrize('distributed', [False, True], ids=['serial', 'xdist'])
def test_activity_uses_collected_paths_even_for_identical_tests_in_two_suites(
        tmp_path, configuration, distributed):
    if distributed:
        pytest.importorskip('xdist')
    nodes = []
    for name in ('SuiteA', 'SuiteB'):
        suite = tmp_path / name
        (suite / 'tests').mkdir(parents=True)
        # Le conftest delimite la suite meme sans fichier de configuration.
        (suite / 'conftest.py').write_text('')
        if configuration == 'ini':
            (suite / 'pytest.ini').write_text('[pytest]\n')
        elif configuration == 'toml':
            (suite / 'pyproject.toml').write_text('[tool.pytest.ini_options]\npython_files = ["*.py"]\n')
        (suite / 'tests/test_same.py').write_text('''import pytest
@pytest.mark.parametrize('protocol', ['T0', 'T1'])
def test_same(protocol):
    assert protocol
''')
        nodes.extend(f'{name}/tests/test_same.py::test_same[{p}]' for p in ('T0', 'T1'))
    events = []
    def line(text):
        activity = parsing.parse_activity_line(text)
        if activity:
            events.append(('prepare' if activity[1] else 'start', activity[0]))
    request = RunRequest(str(tmp_path), sys.executable, tuple(nodes), ())
    report = ReaderRun(request, Reader('', 0), {'PYTEST_ADDOPTS': '-n 2 --color=yes' if distributed else '--color=yes'}).run(
        line, lambda outcome: events.append(('finish', outcome.nodeid)))
    assert report.exit_code == 0, report.output
    assert report.counts == {Status.PASSED: 4}
    assert sorted(node for kind, node in events if kind == 'start') == sorted(nodes)
    assert sorted(node for kind, node in events if kind == 'finish') == sorted(nodes)
    assert [node for kind, node in events if kind == 'prepare'] == [nodes[0], nodes[2]]
    for node in nodes:
        assert events.index(('start', node)) < events.index(('finish', node))
    assert 'PYTESTRUNNER_START' not in report.output
    assert 'PYTESTRUNNER_PREPARE' not in report.output


def test_activity_parser_preserves_case_parameters_and_windows_paths():
    node = r'TSu\Tests\test_card.py::TestCard::test_card[T0 value]'
    assert parsing.parse_activity_line('\x1b[34mPYTESTRUNNER_START\t' + node + '\x1b[0m\n') == (node, False)
    assert parsing.parse_activity_line('PYTESTRUNNER_PREPARE\t' + node) == (node, True)
    assert parsing.parse_activity_line('PYTESTRUNNER_START\t\n') is None
    assert parsing.parse_activity_line('ordinary test output') is None
