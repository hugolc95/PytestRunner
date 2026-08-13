"""Export HTML d'une entree d'historique."""

from core.report_export import export_html_report


def _entry(**overrides):
    base = {
        "id": "abc.0",
        "timestamp": 1700000000,
        "workspace": "/ws",
        "reader": "",
        "duration_seconds": 1.5,
        "exit_code": 0,
        "total": 3,
        "passed": 3,
        "failed": 0,
        "skipped": 0,
        "error": 0,
        "nodeids": ["test_x.py::test_a", "test_x.py::test_b", "test_x.py::test_c"],
        "failed_nodeids": [],
    }
    base.update(overrides)
    return base


def test_export_writes_the_destination_file(tmp_path):
    dest = tmp_path / "report.html"
    export_html_report(_entry(), "some output", str(dest))
    assert dest.is_file()
    contenu = dest.read_text(encoding="utf-8")
    assert "<html" in contenu
    assert "test_x.py::test_a" in contenu


def test_export_shows_the_reader_badge_when_present(tmp_path):
    dest = tmp_path / "report.html"
    export_html_report(_entry(reader="Lecteur B"), "output", str(dest))
    assert "Lecteur B" in dest.read_text(encoding="utf-8")


def test_export_omits_the_reader_badge_when_absent(tmp_path):
    dest = tmp_path / "report.html"
    export_html_report(_entry(reader=""), "output", str(dest))
    assert "badge reader" not in dest.read_text(encoding="utf-8")


def test_export_lists_failed_tests(tmp_path):
    dest = tmp_path / "report.html"
    entry = _entry(failed=1, passed=2, failed_nodeids=["test_x.py::test_b"])
    export_html_report(entry, "output", str(dest))
    contenu = dest.read_text(encoding="utf-8")
    assert "test_x.py::test_b" in contenu
    assert "Failed tests" in contenu


def test_export_escapes_html_in_the_console_output(tmp_path):
    dest = tmp_path / "report.html"
    export_html_report(_entry(), "<script>alert(1)</script>", str(dest))
    contenu = dest.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in contenu
    assert "&lt;script&gt;" in contenu


def test_export_escapes_html_in_the_workspace_path(tmp_path):
    dest = tmp_path / "report.html"
    export_html_report(_entry(workspace="/ws/<injected>"), "output", str(dest))
    contenu = dest.read_text(encoding="utf-8")
    assert "<injected>" not in contenu
    assert "&lt;injected&gt;" in contenu
