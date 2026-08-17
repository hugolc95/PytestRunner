"""Reecrire un config.yml sans le defigurer.

Un fichier de configuration de workspace est ecrit a la main : il porte des
commentaires qui expliquent pourquoi telle valeur est la, un ordre de cles qui
suit la pensee de celui qui l'a ecrit, et souvent des fins de ligne Windows.

L'ancienne interface l'enregistrait avec un `yaml.safe_dump` : commentaires
effaces, cles reordonnees, guillemets et indentation refaits, diff sur chaque
ligne. Ces tests verrouillent le comportement inverse -- seules les lignes dont
la valeur change sont touchees.
"""

from __future__ import annotations

import pytest

from runner.domain.config_file import charger, ecrire, ecrire_texte, valider

CONFIG = """\
# Configuration de la campagne CryptoWrapper.
# Ne pas committer de lecteur personnel ici.

Reader: Cosmo11Secured Reader   # le lecteur de reference
Readers:
  - TestBiosWrapperTU Reader

# Ou le conftest ecrit ses traces.
LOG_PATH: traces_apdu

python_executable: C:/Python311/python.exe
timeout: 30
verbose: false
"""


def _fichier(tmp_path, texte: str = CONFIG, nom: str = "config.yml"):
    chemin = tmp_path / nom
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        f.write(texte)
    return chemin


def _lignes(chemin) -> list[str]:
    with open(chemin, "r", encoding="utf-8", newline="") as f:
        return f.read().splitlines(keepends=True)


# --------------------------------------------------------- ce qui ne bouge pas

def test_only_the_changed_line_is_touched(tmp_path):
    """Le reste du fichier doit revenir octet pour octet."""
    chemin = _fichier(tmp_path)
    avant = _lignes(chemin)

    ok, message = ecrire(chemin, {"LOG_PATH": "autres_traces"})
    assert ok, message

    apres = _lignes(chemin)
    assert len(avant) == len(apres)
    differentes = [i for i, (a, b) in enumerate(zip(avant, apres)) if a != b]
    assert len(differentes) == 1, (
        "plus d'une ligne a change : " + "".join(apres[i] for i in differentes))
    assert "autres_traces" in apres[differentes[0]]


def test_the_comments_survive(tmp_path):
    """C'est tout l'interet : ils expliquent pourquoi une valeur est la."""
    chemin = _fichier(tmp_path)
    ecrire(chemin, {"LOG_PATH": "ailleurs", "timeout": 60})

    texte = chemin.read_text(encoding="utf-8")
    assert "# Configuration de la campagne CryptoWrapper." in texte
    assert "# Ne pas committer de lecteur personnel ici." in texte
    assert "# Ou le conftest ecrit ses traces." in texte


def test_a_trailing_comment_stays_on_its_line(tmp_path):
    chemin = _fichier(tmp_path)
    ecrire(chemin, {"Reader": "TestBiosWrapperTU Reader"})

    ligne = [l for l in _lignes(chemin) if l.startswith("Reader:")][0]
    assert "# le lecteur de reference" in ligne
    assert "TestBiosWrapperTU Reader" in ligne


def test_the_order_of_the_keys_is_kept(tmp_path):
    chemin = _fichier(tmp_path)
    ecrire(chemin, {"timeout": 60, "Reader": "X"})

    cles = [l.split(":")[0] for l in chemin.read_text(encoding="utf-8").splitlines()
            if l and not l.startswith((" ", "#", "-"))]
    assert cles == ["Reader", "Readers", "LOG_PATH", "python_executable",
                    "timeout", "verbose"]


def test_windows_line_endings_are_preserved(tmp_path):
    """Tout reecrire en LF donnerait un diff sur chaque ligne du fichier."""
    chemin = _fichier(tmp_path, CONFIG.replace("\n", "\r\n"))
    ecrire(chemin, {"timeout": 45})

    brut = chemin.read_bytes()
    assert b"\r\n" in brut
    assert brut.count(b"\n") == brut.count(b"\r\n"), "des fins de ligne sont mixtes"


def test_a_key_added_to_a_windows_file_gets_windows_endings(tmp_path):
    """Ajouter du LF a la fin d'un fichier CRLF donne un fichier mixte, que le
    prochain outil normalisera en entier."""
    chemin = _fichier(tmp_path, CONFIG.replace("\n", "\r\n"))
    ecrire(chemin, {"reader_mode": "sequential"})

    brut = chemin.read_bytes()
    assert b"reader_mode: sequential\r\n" in brut
    assert brut.count(b"\n") == brut.count(b"\r\n")


# -------------------------------------------------------------- les valeurs

def test_a_value_needing_quotes_gets_them(tmp_path):
    """Un deux-points nu dans une valeur casse le fichier entier."""
    chemin = _fichier(tmp_path)
    ecrire(chemin, {"LOG_PATH": "C:/traces: essais"})

    assert charger(chemin)["LOG_PATH"] == "C:/traces: essais"


@pytest.mark.parametrize("valeur, attendu", [
    (True, True), (False, False), (30, 30), (1.5, 1.5), ("", ""),
])
def test_types_survive_the_round_trip(tmp_path, valeur, attendu):
    chemin = _fichier(tmp_path)
    ecrire(chemin, {"verbose": valeur})
    assert charger(chemin)["verbose"] == attendu


@pytest.mark.parametrize("valeur, ecrit", [(True, "true"), (False, "false")])
def test_a_boolean_is_written_the_way_yaml_writes_them(tmp_path, valeur, ecrit):
    """`True` avec une majuscule se relit bien, mais detonne au milieu d'un
    fichier qui dit `false` partout ailleurs -- et c'est un fichier qu'on lit.

    En Python un booleen EST un entier : sans branche a lui, il passerait par
    `str()` et ressortirait capitalise.
    """
    chemin = _fichier(tmp_path)
    ecrire(chemin, {"verbose": valeur})

    ligne = [l for l in chemin.read_text(encoding="utf-8").splitlines()
             if l.startswith("verbose:")][0]
    assert ligne == f"verbose: {ecrit}"


def test_a_missing_key_is_added_at_the_end(tmp_path):
    chemin = _fichier(tmp_path)
    ecrire(chemin, {"reader_mode": "sequential"})

    lignes = chemin.read_text(encoding="utf-8").splitlines()
    assert lignes[-1] == "reader_mode: sequential"
    assert charger(chemin)["reader_mode"] == "sequential"


@pytest.mark.parametrize("ecrite", ["LOG_PATH", "log_path", "Log-Path", "log path"])
def test_a_key_is_found_however_it_is_spelled(tmp_path, ecrite):
    """La casse, les tirets et les espaces ne doivent pas creer un doublon.

    Les orthographes testees s'ecartent toutes de la forme normalisee : avec
    seulement `log_path`, qui est deja sa propre normalisation, le test passait
    meme sans normaliser quoi que ce soit.
    """
    chemin = _fichier(tmp_path)
    ecrire(chemin, {ecrite: "ailleurs"})

    texte = chemin.read_text(encoding="utf-8")
    assert texte.count("LOG_PATH") == 1
    assert len([l for l in texte.splitlines() if "ailleurs" in l]) == 1, (
        "une deuxieme cle a ete ajoutee a cote de celle du fichier")
    assert charger(chemin)["LOG_PATH"] == "ailleurs"


# ----------------------------------------------------------------- les listes

def test_a_list_is_rewritten_as_a_block(tmp_path):
    chemin = _fichier(tmp_path)
    ecrire(chemin, {"Readers": ["A Reader", "B Reader", "C Reader"]})

    assert charger(chemin)["Readers"] == ["A Reader", "B Reader", "C Reader"]
    assert "# Ou le conftest ecrit ses traces." in chemin.read_text(encoding="utf-8")


def test_a_shorter_list_leaves_no_orphan_behind(tmp_path):
    """Les anciens elements doivent partir avec le bloc, pas rester dessous."""
    chemin = _fichier(tmp_path, CONFIG.replace(
        "Readers:\n  - TestBiosWrapperTU Reader\n",
        "Readers:\n  - A\n  - B\n  - C\n"))
    ecrire(chemin, {"Readers": ["A"]})

    assert charger(chemin)["Readers"] == ["A"]
    assert " - B" not in chemin.read_text(encoding="utf-8")


def test_a_longer_list_does_not_swallow_the_key_below_it(tmp_path):
    """Le bloc s'allonge et decale tout ce qui suit : les autres remplacements
    sont appliques du bas vers le haut pour que leurs numeros restent bons."""
    chemin = _fichier(tmp_path)
    ecrire(chemin, {"Readers": ["A", "B", "C", "D"], "verbose": True})

    donnees = charger(chemin)
    assert donnees["Readers"] == ["A", "B", "C", "D"]
    assert donnees["LOG_PATH"] == "traces_apdu"
    assert donnees["verbose"] is True


def test_several_changes_at_once_all_land(tmp_path):
    chemin = _fichier(tmp_path)
    ecrire(chemin, {"Reader": "Z", "LOG_PATH": "ici", "timeout": 99,
                    "Readers": ["Y"], "nouveau": "oui"})

    donnees = charger(chemin)
    assert donnees["Reader"] == "Z"
    assert donnees["LOG_PATH"] == "ici"
    assert donnees["timeout"] == 99
    assert donnees["Readers"] == ["Y"]
    assert donnees["nouveau"] == "oui"


# ------------------------------------------------------------ les sections

def test_a_nested_key_of_the_same_name_is_left_alone(tmp_path):
    """Deux sections peuvent porter la meme cle. Les reecrire au jugé
    melangerait les reglages de l'une avec ceux de l'autre : seul le premier
    niveau est modifiable ici.

    La cle imbriquee vient AVANT celle du premier niveau. Placee apres, elle
    etait de toute facon vue en second et le test passait sans qu'on regarde
    jamais l'indentation.
    """
    chemin = _fichier(tmp_path, "campaign:\n  timeout: 300\ntimeout: 30\n")
    ecrire(chemin, {"timeout": 60})

    donnees = charger(chemin)
    assert donnees["timeout"] == 60
    assert donnees["campaign"]["timeout"] == 300


# --------------------------------------------------------------- robustesse

def test_nothing_is_half_written_when_the_disk_refuses(tmp_path, monkeypatch):
    """Une configuration a moitie ecrite rend le workspace incollectable."""
    import pathlib

    chemin = _fichier(tmp_path)
    avant = chemin.read_bytes()

    def refuser(self, cible):
        raise OSError("disque plein")

    monkeypatch.setattr(pathlib.Path, "replace", refuser)
    ok, message = ecrire(chemin, {"timeout": 60})

    assert not ok and message
    assert chemin.read_bytes() == avant
    assert not list(tmp_path.glob("*.tmp")), "le temporaire est reste"


def test_writing_the_whole_text_is_atomic_too(tmp_path):
    chemin = _fichier(tmp_path)
    ok, message = ecrire_texte(chemin, "Reader: X\n# garde\n")

    assert ok, message
    assert chemin.read_text(encoding="utf-8") == "Reader: X\n# garde\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_an_unreadable_file_does_not_stop_a_first_write(tmp_path):
    """Le fichier peut ne pas exister encore : on le cree."""
    chemin = tmp_path / "config.yml"
    ok, _ = ecrire(chemin, {"Reader": "A"})

    assert ok and charger(chemin) == {"Reader": "A"}


# --------------------------------------------------------------- validation

@pytest.mark.parametrize("texte", [
    "cle: [ pas ferme",
    "  indentation: de travers\nautre: x",
    "- une liste\n- pas des cles",
    "juste du texte",
])
def test_a_broken_text_is_refused_before_writing(texte):
    """Verifie AVANT d'ecrire : un fichier invalide rend le workspace
    incollectable, et l'erreur apparaitrait alors loin d'ici, sous la forme
    d'une collecte qui echoue sans raison apparente."""
    valide, message = valider(texte)
    assert not valide and message


@pytest.mark.parametrize("texte", ["", "# rien que des commentaires\n",
                                   "Reader: A\nReaders:\n  - B\n"])
def test_a_sound_text_is_accepted(texte):
    valide, message = valider(texte)
    assert valide and not message
