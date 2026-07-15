# Modifs appliquées

Cette version garde la granularité pytest complète, y compris les tests paramétrés.

## Changement principal

Le `nodeid` pytest n'est plus utilisé comme identifiant interne de l'interface Qt.

- Qt utilise maintenant un UUID interne pour chaque item.
- Le `nodeid` pytest est stocké uniquement sur les feuilles exécutables.
- La sélection retourne uniquement les feuilles cochées, donc les paramètres précis comme `test_x[param]`.
- La collecte reste faite avec `pytest --collect-only -q`.
- Les nodeids restent relatifs au workspace, ce qui matche mieux la sortie `pytest -v`.

## Fichiers modifiés

- `core/test_discovery.py`
- `core/test_tree.py`
- `gui_qt/test_tree_view.py`

## Comportement attendu

Si pytest collecte :

```text
tests/test_api.py::test_login[admin]
tests/test_api.py::test_login[user]
```

L'arbre affiche :

```text
tests
  test_api.py
    test_login
      [admin]
      [user]
```

Si seulement `[admin]` est coché, le runner lance uniquement :

```bash
python -m pytest tests/test_api.py::test_login[admin] --import-mode=importlib --tb=no -v
```
