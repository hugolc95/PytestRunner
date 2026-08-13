"""Le plugin injecte qui impose le lecteur d'un run, sans toucher au code test.

Ces tests couvrent deux niveaux :
- `_construire_texte_modifie`, la construction du texte du fichier avec la cle
  Reader swappee, directement (fonction pure, sans dependre de l'environnement) ;
- le plugin genere complet, execute comme un vrai module Python (comme le ferait
  le subprocess pytest), pour verifier que `builtins.open` et
  `pathlib.Path.read_text`/`read_bytes` sont bien interceptes pour le fichier
  vise, et pour lui seul.

Le point central : getConfigReader() (ou equivalent) ne doit JAMAIS etre
remplacee. Elle doit s'executer normalement et lire un fichier qui, de son
point de vue, contient deja le bon lecteur -- meme si elle fait plus que
relire la cle brute (ce que l'ancienne approche par remplacement de fonction
cassait, voir l'entete de core/reader_plugin.py).
"""

import builtins
import pathlib
import types

import pytest

from core.reader_plugin import CONFIG_PATH_ENV, PLUGIN_MODULE, _PLUGIN_SOURCE, reader_plugin


@pytest.fixture(autouse=True)
def _restaurer_open():
    """Le plugin patche builtins.open/Path.read_text/read_bytes des son import,
    directement sur les objets globaux (c'est le mecanisme teste) : sans
    restauration explicite, un test patche laisserait tous les suivants lire
    un fichier virtuel perime."""
    reel_open = builtins.open
    reel_read_text = pathlib.Path.read_text
    reel_read_bytes = pathlib.Path.read_bytes
    yield
    builtins.open = reel_open
    pathlib.Path.read_text = reel_read_text
    pathlib.Path.read_bytes = reel_read_bytes


def _charger_plugin(monkeypatch, reader="", config_path=""):
    """Execute le code du plugin genere comme un module Python normal.

    Les variables du plugin sont lues depuis l'environnement au chargement :
    on le fixe donc avant d'executer le code, exactement comme le ferait le
    vrai subprocess pytest.
    """
    if reader:
        monkeypatch.setenv("PYTESTRUNNER_READER", reader)
    else:
        monkeypatch.delenv("PYTESTRUNNER_READER", raising=False)
    if config_path:
        monkeypatch.setenv(CONFIG_PATH_ENV, str(config_path))
    else:
        monkeypatch.delenv(CONFIG_PATH_ENV, raising=False)

    module = types.ModuleType("plugin_pytestrunner_sous_test")
    exec(compile(_PLUGIN_SOURCE, "<plugin genere>", "exec"), module.__dict__)
    return module


# ------------------------------------------------ _construire_texte_modifie

def test_construire_texte_modifie_swaps_the_least_indented_reader_line(monkeypatch):
    plugin = _charger_plugin(monkeypatch)
    brut = "Reader: Lecteur A\nSection:\n  Reader: ignore\n"

    modifie = plugin._construire_texte_modifie(brut, "Lecteur B")

    assert modifie == "Reader: Lecteur B\nSection:\n  Reader: ignore\n"


def test_construire_texte_modifie_preserves_quoting_and_trailing_comment(monkeypatch):
    plugin = _charger_plugin(monkeypatch)
    brut = "Reader: ancien  # commentaire\n"

    modifie = plugin._construire_texte_modifie(brut, "valeur: speciale")

    assert modifie == 'Reader: "valeur: speciale" # commentaire\n'


def test_construire_texte_modifie_returns_none_without_a_reader_key(monkeypatch):
    plugin = _charger_plugin(monkeypatch)
    brut = "Autre: valeur\n"

    assert plugin._construire_texte_modifie(brut, "Lecteur B") is None


def test_construire_texte_modifie_preserves_crlf(monkeypatch):
    plugin = _charger_plugin(monkeypatch)
    brut = "Reader: ancien\r\nAutre: x\r\n"

    modifie = plugin._construire_texte_modifie(brut, "nouveau")

    assert modifie == "Reader: nouveau\r\nAutre: x\r\n"


# --------------------------------------------------------- bout en bout, fichier

def test_open_of_the_target_file_returns_the_virtual_text(monkeypatch, tmp_path):
    config = tmp_path / "config.yml"
    config.write_text("Reader: Lecteur A\n", encoding="utf-8")

    _charger_plugin(monkeypatch, reader="Lecteur B", config_path=str(config))

    with open(str(config), "r", encoding="utf-8") as f:
        contenu = f.read()
    assert contenu == "Reader: Lecteur B\n"


def test_path_read_text_of_the_target_file_returns_the_virtual_text(monkeypatch, tmp_path):
    config = tmp_path / "config.yml"
    config.write_text("Reader: Lecteur A\n", encoding="utf-8")

    _charger_plugin(monkeypatch, reader="Lecteur B", config_path=str(config))

    assert pathlib.Path(str(config)).read_text() == "Reader: Lecteur B\n"


def test_a_getter_that_enriches_the_raw_reader_value_keeps_its_enrichment(monkeypatch, tmp_path):
    """Reproduction du bug signale : le getter du workspace ne se contente pas
    de relire `Reader`, il ajoute un champ a la valeur. Comme la fonction n'est
    jamais remplacee -- seul le fichier qu'elle lit est virtuellement different
    -- cet ajout doit survivre intact."""
    config = tmp_path / "config.yml"
    config.write_text("Reader: Lecteur A\n", encoding="utf-8")

    _charger_plugin(monkeypatch, reader="Lecteur B", config_path=str(config))

    def getConfigReader():
        # Un getter réel typique : il lit la cle Reader, puis lui ajoute un
        # champ construit -- exactement ce que l'ancien remplacement de
        # fonction perdait.
        with open(str(config), "r", encoding="utf-8") as f:
            for ligne in f:
                if ligne.startswith("Reader:"):
                    lecteur = ligne.split(":", 1)[1].strip()
                    return f"{lecteur} [verifie]"
        return ""

    assert getConfigReader() == "Lecteur B [verifie]"


def test_files_other_than_the_target_are_not_intercepted(monkeypatch, tmp_path):
    vise = tmp_path / "config.yml"
    vise.write_text("Reader: Lecteur A\n", encoding="utf-8")
    autre = tmp_path / "autre.yml"
    autre.write_text("Reader: ne pas toucher\n", encoding="utf-8")

    _charger_plugin(monkeypatch, reader="Lecteur B", config_path=str(vise))

    with open(str(autre), "r", encoding="utf-8") as f:
        assert f.read() == "Reader: ne pas toucher\n"
    assert pathlib.Path(str(autre)).read_text() == "Reader: ne pas toucher\n"


def test_writing_to_the_target_file_is_not_intercepted(monkeypatch, tmp_path):
    config = tmp_path / "config.yml"
    config.write_text("Reader: Lecteur A\n", encoding="utf-8")
    reel_open = builtins.open

    _charger_plugin(monkeypatch, reader="Lecteur B", config_path=str(config))

    with open(str(config), "w", encoding="utf-8") as f:
        f.write("Reader: ecrit pour de vrai\n")

    with reel_open(str(config), "r", encoding="utf-8") as f:
        assert f.read() == "Reader: ecrit pour de vrai\n"


# ------------------------------------------------------------------- erreurs

def test_missing_reader_key_sets_an_error_and_setup_raises(monkeypatch, tmp_path):
    config = tmp_path / "config.yml"
    config.write_text("Autre: valeur\n", encoding="utf-8")

    plugin = _charger_plugin(monkeypatch, reader="Lecteur B", config_path=str(config))

    assert plugin._erreur != ""
    assert plugin._texte_virtuel is None
    with pytest.raises(RuntimeError):
        plugin.pytest_runtest_setup(item=None)


def test_unreadable_config_path_sets_an_error(monkeypatch, tmp_path):
    introuvable = tmp_path / "n_existe_pas.yml"

    plugin = _charger_plugin(monkeypatch, reader="Lecteur B", config_path=str(introuvable))

    assert plugin._erreur != ""
    assert plugin._texte_virtuel is None
    with pytest.raises(RuntimeError):
        plugin.pytest_runtest_setup(item=None)


def test_without_reader_or_config_path_nothing_is_patched_or_reported(monkeypatch):
    plugin = _charger_plugin(monkeypatch)

    assert plugin._erreur == ""
    assert plugin._texte_virtuel is None
    plugin.pytest_runtest_setup(item=None)  # ne doit pas lever


# ------------------------------------------------------------- reader_plugin()

def test_reader_plugin_is_a_noop_without_a_config_path():
    with reader_plugin("") as (arguments, dossier):
        assert arguments == []
        assert dossier == ""


def test_reader_plugin_writes_the_generated_module_and_yields_its_args(tmp_path):
    config = tmp_path / "config.yml"
    config.write_text("Reader: Lecteur A\n", encoding="utf-8")

    with reader_plugin(str(config)) as (arguments, dossier):
        assert arguments == ["-p", PLUGIN_MODULE]
        chemin_module = pathlib.Path(dossier) / f"{PLUGIN_MODULE}.py"
        assert chemin_module.is_file()
        assert chemin_module.read_text(encoding="utf-8") == _PLUGIN_SOURCE

    assert not pathlib.Path(dossier).exists()
