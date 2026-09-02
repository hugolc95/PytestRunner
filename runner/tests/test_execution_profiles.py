from __future__ import annotations

import json
import zipfile

import pytest
from PySide6.QtCore import Qt

from runner.domain.execution_profile import (
    ExecutionOptions,
    ExecutionProfile,
    ProfileStore,
    ProfileValidationError,
    ReportOptions,
    export_profile,
    inspect_profile,
)
from runner.ui.execution_profiles_page import AddTestsDialog, ExecutionProfilesPage


def sample_profile() -> ExecutionProfile:
    return ExecutionProfile(
        name="Certification RSA",
        description="Portable certification sequence",
        configuration_name="campaign.yml",
        configuration_text="Reader: OMNIKEY\nLOG_PATH: logs\n",
        sequence=[
            "tests/test_api.py::test_login[admin]",
            "tests/test_card.py::test_reset",
            "tests/test_api.py::test_login[admin]",
        ],
        execution=ExecutionOptions(
            repetitions=20, rerun_failures=2, stop_after_failure=False),
        reports=ReportOptions(
            generate_allure=True, save_complete_logs=True),
    )


def test_profile_round_trip_preserves_order_duplicates_and_configuration(tmp_path):
    source = sample_profile()
    path = export_profile(source, tmp_path / "rsa")

    validation = inspect_profile(path, source.sequence)
    loaded = validation.profile

    assert path.suffix == ".pytest-profile"
    assert loaded.sequence == source.sequence
    assert loaded.configuration_text == source.configuration_text
    assert loaded.execution == source.execution
    assert loaded.reports == source.reports
    assert loaded.total_executions == 60
    assert not validation.has_warnings


def test_import_reports_each_missing_sequence_occurrence(tmp_path):
    source = sample_profile()
    path = export_profile(source, tmp_path / "rsa.pytest-profile")

    validation = inspect_profile(
        path, ["tests/test_card.py::test_reset"])

    assert validation.missing_steps == (
        "tests/test_api.py::test_login[admin]",
        "tests/test_api.py::test_login[admin]",
    )


def test_import_rejects_checksum_mismatch(tmp_path):
    path = export_profile(sample_profile(), tmp_path / "rsa.pytest-profile")
    with zipfile.ZipFile(path, "r") as source:
        manifest = source.read("manifest.json")
    with zipfile.ZipFile(path, "w") as changed:
        changed.writestr("manifest.json", manifest)
        changed.writestr("configuration/campaign.yml", b"changed: true\n")

    with pytest.raises(ProfileValidationError, match="checksum"):
        inspect_profile(path)


def test_import_rejects_unknown_manifest_fields(tmp_path):
    path = export_profile(sample_profile(), tmp_path / "rsa.pytest-profile")
    with zipfile.ZipFile(path, "r") as source:
        manifest = json.loads(source.read("manifest.json"))
        config = source.read("configuration/campaign.yml")
    manifest["command"] = "do-something"
    with zipfile.ZipFile(path, "w") as changed:
        changed.writestr("manifest.json", json.dumps(manifest))
        changed.writestr("configuration/campaign.yml", config)

    with pytest.raises(ProfileValidationError, match="unknown fields"):
        inspect_profile(path)


def test_profile_rejects_absolute_windows_test_path(tmp_path):
    profile = sample_profile()
    profile.sequence = ["C:\\external\\test_api.py::test_login"]

    with pytest.raises(ProfileValidationError, match="Unsafe test path"):
        export_profile(profile, tmp_path / "unsafe.pytest-profile")


def test_profile_rejects_an_excessive_execution_total(tmp_path):
    profile = sample_profile()
    profile.sequence = profile.sequence * 1000
    profile.execution.repetitions = 1000

    with pytest.raises(ProfileValidationError, match="total executions"):
        export_profile(profile, tmp_path / "too-large.pytest-profile")


def test_store_does_not_overwrite_same_imported_identifier(tmp_path):
    source = sample_profile()
    external = export_profile(source, tmp_path / "external.pytest-profile")
    store = ProfileStore(tmp_path / "profiles")

    first = store.import_copy(external).profile
    second = store.import_copy(external).profile

    assert first.profile_id != second.profile_id
    assert len(store.list()) == 2


def test_profile_page_can_add_the_same_test_more_than_once(qapp, tmp_path):
    page = ExecutionProfilesPage(ProfileStore(tmp_path / "profiles"))
    try:
        page.set_workspace_context(
            ["tests/test_api.py::test_login[admin]"],
            str(tmp_path / "campaign.yml"))
        page._append_tests([
            "tests/test_api.py::test_login[admin]",
            "tests/test_api.py::test_login[admin]",
        ])

        assert page.sequence_list.count() == 2
        assert page.sequence_list.item(0).data(Qt.UserRole) == \
            page.sequence_list.item(1).data(Qt.UserRole)
        assert "2 sequence steps" in page.summary.text()
    finally:
        page.close()


def test_add_tests_tree_can_select_a_folder_and_a_single_test(qapp):
    nodeids = [
        "suite/test_api.py::test_login[admin]",
        "suite/test_api.py::test_login[user]",
        "suite/test_math.py::test_compute",
    ]
    dialog = AddTestsDialog(nodeids)
    added = []
    dialog.tests_added.connect(added.extend)
    try:
        folder = dialog.model.index(0, 0)
        assert dialog.model.setData(folder, Qt.Checked, Qt.CheckStateRole)
        dialog._add()
        assert added == nodeids
        assert dialog.model.checked_nodeids() == []

        leaf = dialog.model.index_for_nodeid(nodeids[1])
        assert dialog.model.setData(leaf, Qt.Checked, Qt.CheckStateRole)
        dialog._add()
        assert added == [*nodeids, nodeids[1]]
    finally:
        dialog.close()
