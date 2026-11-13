"""Les groupes compacts restent lisibles et leurs colonnes se reglent a la souris."""
from dataclasses import replace

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt, QRect, QSize
from PySide6.QtGui import QImage, QMouseEvent, QPainter, QFontMetrics, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem

from runner.domain.execution import Collection
from runner.domain.execution_profile import ExecutionProfile
from runner.domain.models import Kind, Reader, Status
from runner.domain.workspace import Workspace
from runner.ui.live_profile_model import LiveProfileModel
from runner.ui.main_window import MainWindow
from runner.ui import tokens as t


PREFIX = 'TSu/RA/Int/FlexiDep/tests/'
NODES = [PREFIX + 'perso/test_perso.py::TestSetup::test_load',
         PREFIX + 'nominal/test_RSA.py::TestRSA::test_sign[T0]',
         PREFIX + 'nominal/test_RSA.py::TestRSA::test_sign[T1]']
GROUP = dict(id='rsa', name='Flexi module RSA', color='#448aff', description='')
READERS = (Reader('simuSCR700U1132 Reader', 0), Reader('Other reader', 2))


def profile(nodes=NODES, **kwargs):
    return ExecutionProfile('FLEXI DEP NEW METHODE', list(nodes), '', '',
                            step_groups=[dict(GROUP) for _ in nodes], **kwargs)


def test_named_group_hides_only_shared_directories_and_keeps_full_targets():
    model = LiveProfileModel()
    model.prepare(profile(), READERS)
    root = model.index(0, 0)
    assert [child.node.name for child in root.internalPointer().children] == ['perso', 'nominal']
    assert [location[2] for location in model.locations.values()] == NODES
    nominal = model.index(1, 0, root)
    assert model.activation_target(nominal) == PREFIX + 'nominal'
    module = model.index(0, 0, nominal)
    assert model.activation_target(module) == PREFIX + 'nominal/test_RSA.py'
    function = model.index(0, 0, module)
    assert function.data() == 'test_sign'
    assert model.activation_target(function) == NODES[1].split('[')[0]
    assert function.internalPointer().node.kind is Kind.TEST
    assert model.rowCount(function) == 2
    model.set_disabled_tests({PREFIX + 'nominal': {'reason': 'temporarily disabled'}})
    assert model.checked_nodeids() == ['0:0']


def test_compact_group_preserves_module_cases_duplicates_yaml_and_retries():
    nodes = [NODES[1], NODES[2], NODES[1]]
    p = profile(nodes, step_overrides=[{'protocol': 'T0'}, {'protocol': 'T1'}, {'protocol': 'T2'}])
    p.execution = replace(p.execution, repetitions=2)
    model = LiveProfileModel()
    model.prepare(p, READERS)
    group = model.index(0, 0, model.index(0, 0))
    assert model.index(0, 0, group).data() == 'test_RSA.py'
    assert list(model.locations.values()) == [(i, 0, node) for i, node in enumerate(nodes * 2)]
    assert model.counts() == (6, 6)
    model.apply_execution(2, 1, 2, nodes[2], Status.FAILED)
    assert model.locations['2:1'] == (2, 1, nodes[2])
    assert model.activation_target(model.index_for_nodeid('2:1')) == nodes[2]
    assert model.counts() == (6, 6)


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(MainWindow, '_restore', lambda *_: None)
    w = MainWindow()
    qtbot.addWidget(w)
    w.workspace = Workspace.load(str(tmp_path))
    w._on_collected(Collection(tuple(NODES)))
    w.model.set_readers(READERS)
    w._open_collected_profile(profile())
    w.profile_model.set_readers(READERS)
    w._size_reader_columns()
    w._size_reader_columns(w.profile_tree, w.profile_model)
    w.resize(1450, 900)
    w.show()
    qtbot.waitExposed(w)
    yield w
    w.apply_theme('dark')
    w.close()


@pytest.mark.parametrize('description', ['', 'Protocol and signing checks'])
@pytest.mark.parametrize('running', [False, True])
@pytest.mark.parametrize('font_size', [13, 20])
@pytest.mark.parametrize('theme', ['dark', 'light'])
def test_group_title_does_not_overlap_checkbox_or_folder(window, description, font_size, theme, running):
    w = window
    w.apply_theme(theme)
    p = profile()
    p.step_groups = [dict(GROUP, description=description) for _ in NODES]
    w._open_collected_profile(p)
    view = w.profile_tree
    font = view.font()
    font.setPixelSize(font_size)
    view.setFont(font)
    view.setStyleSheet(f'QTreeView {{font-size:{font_size}px;}}')
    view.doItemsLayout()
    index = w.profile_model.index(0, 0)
    if running:
        w.profile_model.apply_execution(0, 0, READERS[0].index, NODES[0], Status.RUNNING)
    option = QStyleOptionViewItem()
    option.initFrom(view)
    option.widget = view
    option.rect = view.visualRect(index)
    option.font = view.font()
    option.fontMetrics = QFontMetrics(view.font())
    icon_size = view.style().pixelMetric(QStyle.PM_SmallIconSize)
    option.decorationSize = QSize(icon_size, icon_size)
    option.state |= QStyle.State_Selected
    delegate = view.itemDelegate()
    delegate.initStyleOption(option, index)
    style = view.style()
    check = style.subElementRect(QStyle.SE_ItemViewItemCheckIndicator, option, view)
    folder = style.subElementRect(QStyle.SE_ItemViewItemDecoration, option, view)
    calls = []
    colors = []

    class Painter(QPainter):
        def drawText(self, rect, *args):
            # qtawesome dessine aussi son glyphe avec drawText ; seules les
            # zones du titre et de la description doivent eviter les controles.
            text = args[-1]
            if rect.isValid() and isinstance(text, str) and (text.startswith(GROUP['name']) or text == description):
                calls.append(QRect(rect))
                colors.append(self.pen().color())
            return super().drawText(rect, *args)

    image = QImage(view.viewport().size(), QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = Painter(image)
    try:
        delegate.paint(painter, option, index)
    finally:
        painter.end()
    assert len(calls) == (2 if description else 1)
    assert colors[0] == QColor(t.ACCENT if running else t.TEXT)
    for rect in calls:
        assert rect.left() > max(check.right(), folder.right())
        assert option.rect.contains(rect)
    if description:
        assert calls[1].top() > calls[0].bottom()


def drag(header, edge, offset):
    viewport = header.viewport()
    y = header.height() // 2
    QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, QPoint(edge, y))
    for dx in (offset // 3, offset * 2 // 3, offset):
        local = QPointF(edge + dx, y)
        QApplication.sendEvent(viewport, QMouseEvent(
            QMouseEvent.MouseMove, local, viewport.mapToGlobal(local),
            Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
        QApplication.processEvents()
    QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, QPoint(edge + offset, y))


@pytest.mark.parametrize('profile_mode', [False, True])
@pytest.mark.parametrize('duration_visible', [False, True])
@pytest.mark.parametrize('reader_count', [1, 2])
def test_reader_width_can_be_dragged_from_either_edge_and_is_kept(
        window, qtbot, profile_mode, duration_visible, reader_count):
    w = window
    w._set_profile_tree_visible(profile_mode)
    tree = w._visible_test_tree()
    model = tree.model()
    model.set_readers(READERS[:reader_count])
    w._size_reader_columns(tree, model)
    w.set_duration_column_visible(duration_visible)
    header = tree.header()
    columns = w.profile_tree_columns if profile_mode else w.tree_columns
    qtbot.waitUntil(lambda: sum(header.sectionSize(i) for i in range(header.count())
                               if not header.isSectionHidden(i)) == tree.viewport().width())
    width = header.sectionSize(1)
    edge = header.sectionViewportPosition(1) - 1
    drag(header, edge, -45)
    qtbot.waitUntil(lambda: header.sectionSize(1) > width + 20)
    first_width = header.sectionSize(1)
    assert columns.remembered(1) == first_width
    edge = header.sectionViewportPosition(1) + first_width - 1
    drag(header, edge, -25)
    qtbot.waitUntil(lambda: header.sectionSize(1) < first_width - 10)
    kept = header.sectionSize(1)
    assert columns.remembered(1) == kept
    w._size_reader_columns(tree, model)
    assert header.sectionSize(1) == kept
    w.resize(1150, 800)
    qtbot.waitUntil(lambda: not tree.viewport().testAttribute(Qt.WA_PendingResizeEvent))
    assert header.sectionSize(1) == kept


def test_profile_reader_width_survives_a_new_window_and_reordering(window, qtbot):
    w = window
    header = w.profile_tree.header()
    qtbot.waitUntil(lambda: header.sectionSize(0) + header.sectionSize(1) + header.sectionSize(2)
                   + header.sectionSize(3) == w.profile_tree.viewport().width())
    drag(header, header.sectionViewportPosition(1) - 1, -45)
    width = header.sectionSize(1)
    assert w.profile_tree_columns.remembered(1) == width
    w.profile_tree_columns._save()
    other = MainWindow()
    qtbot.addWidget(other)
    other.workspace = w.workspace
    other._on_collected(Collection(tuple(NODES)))
    other._open_collected_profile(profile())
    other.profile_model.set_readers(tuple(reversed(READERS)))
    other._size_reader_columns(other.profile_tree, other.profile_model)
    assert other.profile_tree.columnWidth(2) == width
    other.close()
