"""Occurrence settings must survive editing, archives and cached conftest getters."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from runner.domain.execution_profile import (
    ExecutionProfile, ProfileStore, ProfileValidationError,
    export_profile, inspect_profile, validate_profile,
)
from runner.domain.history_profile import capture_profile, profile_from_entry
from runner.domain.models import Reader, RunRequest, Status
from runner.services.run_service import RunService
from runner.ui.execution_profiles_page import ExecutionProfilesPage


def profile():
    return ExecutionProfile("T0 then T1", ["test_card.py::test_card"] * 3,
                            "configEnv.yml", "card:\n  protocol: T0\n  timeout: 15\nReader: local\n",
                            step_overrides=[{}, {"card": {"protocol": "T1"}}, {}])


def test_step_parameters_survive_archive_and_history(tmp_path):
    original = profile()
    restored = inspect_profile(export_profile(original, tmp_path / "profile")).profile
    assert restored.step_overrides == original.step_overrides
    config = tmp_path / "configEnv.yml"
    config.write_text(original.configuration_text, encoding="utf-8")
    request = RunRequest(str(tmp_path), sys.executable, tuple(original.sequence), (), str(config))
    saved = capture_profile(request, original)
    entry = SimpleNamespace(replay_profile=saved)
    assert profile_from_entry(entry).step_overrides == original.step_overrides


@pytest.mark.parametrize("patches", [[{}], [None] * 3, [{"x": float("nan")}] * 3,
                                    [{"x": object()}] * 3])
def test_invalid_step_parameters_are_rejected(patches):
    value = profile()
    value.step_overrides = patches
    with pytest.raises(ProfileValidationError):
        validate_profile(value)


def test_dialog_parameters_duplicate_move_reset_and_save(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog
    from runner.ui.profile_dialogs import StepParametersDialog
    page = ExecutionProfilesPage(ProfileStore(tmp_path / "profiles"))
    qtbot.addWidget(page)
    original = profile()
    original.profile_id = page.current_profile().profile_id
    page._profiles[page.profile_list.currentRow()] = original
    page._populate(original)
    page.sequence_list.setCurrentItem(page._step_items()[1])
    def edit(dialog):
        mode, editor = dialog.controls[("card", "protocol")]
        assert mode.currentText() == "Custom value"
        editor.setCurrentText("T0")
        return QDialog.Accepted
    monkeypatch.setattr(StepParametersDialog, 'exec', edit)
    page.edit_step_parameters()
    assert page._step_patches()[1] == {"card": {"protocol": "T0"}}
    page.duplicate_steps()
    assert page._step_patches() == [{}, {"card": {"protocol": "T0"}},
                                  {"card": {"protocol": "T0"}}, {}]
    page._move_step(-1)
    assert page._step_patches()[1] == {"card": {"protocol": "T0"}}
    def reset(dialog):
        dialog.reset()
        return QDialog.Accepted
    monkeypatch.setattr(StepParametersDialog, 'exec', reset)
    page.edit_step_parameters()
    assert page._step_patches()[1] == {}
    assert page.save_current()
    assert page.store.list()[0].step_overrides[2] == {"card": {"protocol": "T0"}}


def test_invalid_numeric_edit_cannot_be_applied(qtbot):
    from runner.ui.profile_dialogs import StepParametersDialog
    dialog = StepParametersDialog('test_card.py::test_card', {'timeout': 15}, {})
    qtbot.addWidget(dialog)
    mode, editor = dialog.controls[("timeout",)]
    assert not editor.isEnabled()
    mode.setCurrentText("Custom value")
    editor.setText("oops")
    assert not dialog.apply_button.isEnabled()
    dialog.accept()
    assert not dialog.result()
    editor.setText("20")
    assert dialog.patch == {"timeout": 20}
    assert dialog.apply_button.isEnabled()
    mode.setCurrentText("Profile value")
    assert dialog.patch == {}
    assert editor.text() == "15"
    assert not editor.isEnabled()


def test_each_step_reloads_conftest_getters_and_session_fixtures(qtbot, tmp_path):
    config = tmp_path / "configEnv.yml"
    original = "Reader: local\ncard:\n  protocol: DEFAULT\n  timeout: 15\n"
    config.write_text(original, encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        "from pathlib import Path\nimport pytest\nimport yaml\n"
        "CACHED = yaml.safe_load(Path('configEnv.yml').read_text(encoding='utf-8'))\n"
        "def get_protocol():\n    return CACHED['card']['protocol']\n"
        "@pytest.fixture(scope='session')\n"
        "def settings():\n    return CACHED, get_protocol()\n", encoding="utf-8")
    (tmp_path / "test_card.py").write_text(
        "from pathlib import Path\nimport json\nimport os\n"
        "def test_card(settings):\n"
        "    cached, protocol = settings\n"
        "    assert cached['card']['timeout'] == 15\n"
        "    with Path(cached['Reader'] + '.jsonl').open('a', encoding='utf-8') as f:\n"
        "        f.write(json.dumps([protocol, os.getpid()]) + '\\n')\n"
        "    retried = Path(cached['Reader'] + '.retried')\n"
        "    if protocol == 'T1' and not retried.exists():\n"
        "        retried.write_text('once')\n"
        "        assert False, 'Retry must keep T1'\n", encoding="utf-8")
    nodeid = "test_card.py::test_card"
    request = RunRequest(str(tmp_path), sys.executable, (nodeid,),
                         (Reader("A", 0), Reader("B", 1)), str(config))
    service = RunService()
    finished = []
    batches = []
    service.profile_batch_report.connect(
        lambda position, count, attempt, report: batches.append(
            (position, attempt, report.reader.name, report.exit_code, report.counts)))
    service.finished.connect(finished.extend)
    try:
        assert service.start_profile(request, dict(os.environ), [nodeid] * 3, repetitions=2, rerun_failures=1,
                                     step_overrides=[{"card": {"protocol": "T0"}},
                                                     {"card": {"protocol": "T1"}}, {}])
        paths = list(service._profile_config_paths.values())
        qtbot.waitUntil(lambda: bool(finished), timeout=60000)
        service.wait(5000)
        for reader in ("A", "B"):
            rows = [json.loads(row) for row in (tmp_path / f"{reader}.jsonl").read_text().splitlines()]
            assert [row[0] for row in rows] == ["T0", "T1", "T1", "DEFAULT", "T0", "T1", "DEFAULT"], batches
            assert len({row[1] for row in rows}) == 7
        assert all(report.counts == {Status.PASSED: 6} for report in finished)
        assert config.read_text(encoding="utf-8") == original
        assert all(not Path(path).exists() for path in paths)
    finally:
        if service.busy:
            service.cancel()
        service.wait(5000)
