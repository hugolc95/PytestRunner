"""Gardes sur la publication de l'executable Windows courant."""

from pathlib import Path


def test_windows_build_validates_the_interface_it_packages():
    """Le workflow et le spec doivent viser la meme generation d'interface.

    Une release `latest` etait restee plusieurs commits en retard : le workflow
    construisait `runner/`, mais son etape de test lancait seulement la suite
    de l'ancienne interface `gui_qt/`. Une panne de cette derniere empechait
    donc de publier un correctif pourtant valide pour l'exe distribue.
    """
    racine = Path(__file__).parents[2]
    workflow = (racine / ".github" / "workflows" / "build-windows.yml").read_text(
        encoding="utf-8")
    spec = (racine / "PytestRunner.spec").read_text(encoding="utf-8")

    assert '["main_runner.py"]' in spec
    assert "pytest runner/tests -q" in workflow
    assert "pytest-xdist" in workflow
    assert "pytest tests -q" not in workflow
