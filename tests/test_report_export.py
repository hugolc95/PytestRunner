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
    # Le nodeid est rendu en deux morceaux (chemin grise, nom du test en
    # evidence) : on verifie donc les deux parties, pas la chaine entiere.
    assert "test_x.py::" in contenu
    assert "test_a" in contenu


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
    assert "test_x.py::" in contenu
    assert "test_b" in contenu
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


def test_export_shows_the_workspace_configuration(tmp_path):
    """Les reglages sous lesquels un run a tourne font partie de son resultat :
    un rapport relu six mois plus tard doit les porter."""
    dest = tmp_path / "report.html"
    entry = _entry(config={"LOG_PATH": "C:/traces", "Mode": "PERSO", "RSAkey": 3072})
    export_html_report(entry, "output", str(dest))

    contenu = dest.read_text(encoding="utf-8")
    assert "Configuration" in contenu
    assert "LOG_PATH" in contenu and "C:/traces" in contenu
    assert "PERSO" in contenu and "3072" in contenu


def test_export_omits_the_configuration_block_when_empty(tmp_path):
    dest = tmp_path / "report.html"
    export_html_report(_entry(config={}), "output", str(dest))
    assert "table class=\"config\"" not in dest.read_text(encoding="utf-8")


def test_export_skips_nested_and_runner_only_configuration_keys(tmp_path):
    """Une sous-section entiere ou un reglage propre a PytestRunner remplirait
    le rapport de details qui ne disent rien du run."""
    dest = tmp_path / "report.html"
    entry = _entry(config={
        "Mode": "PERSO",
        "Readers": ["A", "B"],
        "reader_mode": "parallel",
        "Debug": {"RSAkey": 3072},
    })
    export_html_report(entry, "output", str(dest))

    bloc = dest.read_text(encoding="utf-8").split("Configuration")[1].split("</table>")[0]
    assert "Mode" in bloc
    assert "Readers" not in bloc
    assert "reader_mode" not in bloc
    assert "Debug" not in bloc


def test_export_escapes_html_in_the_configuration(tmp_path):
    dest = tmp_path / "report.html"
    export_html_report(_entry(config={"Mode": "<b>x</b>"}), "output", str(dest))
    contenu = dest.read_text(encoding="utf-8")
    assert "<b>x</b>" not in contenu
    assert "&lt;b&gt;x&lt;/b&gt;" in contenu
