"""
Gestion de l'historique des executions pytest.

L'historique est stocke en dehors du workspace teste, dans le dossier
utilisateur (~/.pytest_runner_gui/), pour ne jamais polluer les projets
sur lesquels l'outil est utilise.

Chaque run genere:
- une entree dans run_history.json (metadonnees + compteurs)
- un fichier .log avec la sortie console complete du run
- (optionnel) un fichier .xml JUnit produit nativement par pytest
  (option --junitxml, aucune dependance supplementaire requise)
"""

import json
import os
import time


BUILD_NUMBER_ENV = "PYTEST_RUNNER_BUILD_NUMBER"


def history_dir() -> str:
    """Dossier de stockage de l'historique (cree si absent)."""
    base = os.path.join(os.path.expanduser("~"), ".pytest_runner_gui", "history")
    os.makedirs(base, exist_ok=True)
    return base


def new_run_id() -> str:
    """Identifiant unique et lisible pour un run (utilise pour nommer les fichiers)."""
    return time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"


def _history_file() -> str:
    return os.path.join(history_dir(), "run_history.json")


def _build_counter_file() -> str:
    return os.path.join(history_dir(), "build_counter.txt")


class RunHistoryManager:
    """Charge, sauvegarde et interroge l'historique des executions."""

    def __init__(self, max_entries: int = 300):
        self.max_entries = max_entries
        self._entries: list[dict] = []
        self._load()

    def _load(self):
        path = _history_file()
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._entries = json.load(f)
            except Exception:
                self._entries = []
        else:
            self._entries = []

    def _save(self):
        try:
            with open(_history_file(), "w", encoding="utf-8") as f:
                json.dump(self._entries, f, indent=2, ensure_ascii=False)
        except Exception:
            # L'historique ne doit jamais faire planter l'appli.
            pass

    def next_build_number(self) -> int:
        """Reserve le prochain numero de build, independamment du run_id technique.

        Le compteur est conserve dans un fichier separe afin qu'un nettoyage du
        Run History ne reutilise pas les numeros d'anciens dossiers de logs.
        """
        entry_max = max(
            (int(entry.get("build_number") or 0) for entry in self._entries),
            default=0,
        )
        stored = 0
        try:
            with open(_build_counter_file(), "r", encoding="utf-8") as f:
                stored = int(f.read().strip() or 0)
        except (OSError, ValueError):
            pass

        number = max(entry_max, stored) + 1
        try:
            counter_path = _build_counter_file()
            os.makedirs(os.path.dirname(counter_path), exist_ok=True)
            with open(counter_path, "w", encoding="utf-8") as f:
                f.write(str(number))
        except OSError:
            # L'historique continuera a fonctionner ; les entrees deja en memoire
            # evitent au moins une reutilisation pendant cette session.
            pass
        return number

    def add_run(
        self,
        run_id: str,
        workspace: str,
        duration_seconds: float,
        exit_code: int,
        counts: dict,
        nodeids: list,
        failed_nodeids: list,
        output_text: str,
        junit_xml_path: str = "",
        source: str = "workspace",
        reader: str = "",
        config: dict | None = None,
        build_number: int | None = None,
    ) -> dict:
        """Enregistre un run termine et retourne l'entree creee.

        Avec plusieurs lecteurs, un run pytest par lecteur tourne : chacun a
        son propre resultat (compteurs, sortie, JUnit) et merite sa propre
        ligne d'historique, plutot qu'un total agrege qui masquerait lequel a
        echoue. `reader` porte alors le nom du lecteur ; vide pour un run a
        lecteur unique ou sans lecteur configure du tout.
        """

        output_path = os.path.join(history_dir(), f"{run_id}.log")
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(output_text or "")
        except Exception:
            output_path = ""

        has_junit = bool(junit_xml_path) and os.path.isfile(junit_xml_path)

        entry = {
            "id": run_id,
            "build_number": int(build_number) if build_number is not None else None,
            "timestamp": time.time(),
            "source": source,
            "workspace": workspace,
            "reader": reader,
            "config": dict(config) if isinstance(config, dict) else {},
            "duration_seconds": round(duration_seconds, 2),
            "exit_code": exit_code,
            "total": sum(counts.values()),
            "passed": counts.get("PASSED", 0),
            "failed": counts.get("FAILED", 0),
            "skipped": counts.get("SKIPPED", 0),
            "error": counts.get("ERROR", 0),
            "nodeids": list(nodeids or []),
            "failed_nodeids": list(failed_nodeids or []),
            "output_file": output_path,
            "junit_xml_path": junit_xml_path if has_junit else "",
        }

        self._entries.insert(0, entry)
        self._entries = self._entries[: self.max_entries]
        self._save()
        return entry

    def all_entries(self) -> list:
        return list(self._entries)

    def compute_flaky_tests(self, limit: int = 50) -> list[dict]:
        """Detecte les tests dont le resultat n'est pas constant d'un run a
        l'autre (parfois passe, parfois echoue), sur les `limit` runs les plus
        recents. Retourne une liste triee par taux d'echec decroissant."""
        seen: dict[str, int] = {}
        failed: dict[str, int] = {}

        for entry in self._entries[:limit]:
            failed_nodeids = set(entry.get("failed_nodeids") or [])
            for nodeid in entry.get("nodeids") or []:
                seen[nodeid] = seen.get(nodeid, 0) + 1
                if nodeid in failed_nodeids:
                    failed[nodeid] = failed.get(nodeid, 0) + 1

        flaky = [
            {
                "nodeid": nodeid,
                "seen": count,
                "failed": failed.get(nodeid, 0),
                "flaky_ratio": failed.get(nodeid, 0) / count,
            }
            for nodeid, count in seen.items()
            if 0 < failed.get(nodeid, 0) < count
        ]
        flaky.sort(key=lambda row: row["flaky_ratio"], reverse=True)
        return flaky

    def clear(self):
        # On efface aussi les fichiers .log/.xml associes pour ne rien laisser trainer.
        for entry in self._entries:
            for key in ("output_file", "junit_xml_path"):
                path = entry.get(key)
                if path and os.path.isfile(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
        self._entries = []
        self._save()

    @staticmethod
    def get_output(entry: dict) -> str:
        path = entry.get("output_file")
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return ""
        return ""
