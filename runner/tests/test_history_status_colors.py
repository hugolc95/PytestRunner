from runner.domain.history import History, RunEntry
from runner.domain.models import Status
from runner.ui.widgets import RecentRunsSparkline
from runner.ui import tokens as t


def test_statuses_roundtrip_and_sparkline(qtbot, tmp_path):
    history = History(tmp_path)
    statuses = [Status.PASSED, Status.SKIPPED, Status.ERROR, Status.FAILED]
    for i, status in enumerate(statuses):
        history.add(RunEntry(id=str(i), timestamp=i, workspace='', nodeids=('test_a',),
                            counts={status.name: 1}, test_statuses={'test_a': status.name}))
    saved = History(tmp_path)
    assert saved.recent_statuses('test_a') == statuses
    sparkline = RecentRunsSparkline()
    qtbot.addWidget(sparkline)
    sparkline.set_runs(saved.recent_statuses('test_a'))
    for i, status in enumerate(statuses):
        bar = sparkline._ligne.itemAt(i).widget()
        assert t.status_color(status) in bar.styleSheet()
        assert bar.toolTip() == status.label


def test_old_ambiguous_history_is_not_green(tmp_path):
    history = History(tmp_path)
    history.add(RunEntry(id='old', timestamp=1, workspace='', nodeids=('a', 'b'),
                        counts={'PASSED': 1, 'SKIPPED': 1}))
    assert history.recent_statuses('a') == [Status.PENDING]
