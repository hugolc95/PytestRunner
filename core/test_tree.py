import uuid
from dataclasses import dataclass, field


@dataclass
class TestNode:
    name: str
    nodeid: str | None = None
    kind: str = "group"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    children: list["TestNode"] = field(default_factory=list)

    def get_or_create_child(
        self,
        name: str,
        *,
        nodeid: str | None = None,
        kind: str = "group",
    ) -> "TestNode":
        for child in self.children:
            if child.name == name and child.kind == kind:
                # Ne jamais transformer un noeud group en test par accident.
                if child.nodeid is None and nodeid is not None:
                    child.nodeid = nodeid
                return child

        child = TestNode(name=name, nodeid=nodeid, kind=kind)
        self.children.append(child)
        return child


def _split_param(test_name: str) -> tuple[str, str | None]:
    """Retourne ('test_func', '[param]') pour test_func[param]."""
    if "[" not in test_name or not test_name.endswith("]"):
        return test_name, None
    func, param = test_name.split("[", 1)
    return func, "[" + param


def build_test_tree(nodeids: list[str], workspace: str | None = None) -> list[TestNode]:
    """
    Construit un arbre stable a partir de nodeids pytest RELATIFS.

    Le nodeid pytest complet est stocke uniquement sur les feuilles executables.
    Les dossiers, fichiers, classes et fonctions parametrees sont des groupes.
    L'UI utilise ensuite des UUID internes, pas les nodeids, pour identifier les items.
    """
    roots: dict[str, TestNode] = {}

    for raw_nodeid in nodeids:
        if "::" not in raw_nodeid:
            continue

        nodeid = raw_nodeid.replace("\\", "/").strip()
        file_path, *test_parts = nodeid.split("::")
        path_parts = [p for p in file_path.split("/") if p]

        if not path_parts or not test_parts:
            continue

        root_name = path_parts[0]
        current = roots.setdefault(root_name, TestNode(root_name, kind="folder"))

        # Dossiers intermediaires + fichier.
        for index, part in enumerate(path_parts[1:], start=1):
            kind = "file" if index == len(path_parts) - 1 else "folder"
            current = current.get_or_create_child(part, kind=kind)

        # Classes eventuelles + test final.
        for part in test_parts[:-1]:
            current = current.get_or_create_child(part, kind="class")

        last = test_parts[-1]
        function_name, param_label = _split_param(last)

        if param_label is None:
            # Test non parametre: la fonction est directement une feuille executable.
            current.get_or_create_child(function_name, nodeid=nodeid, kind="case")
        else:
            # Test parametre: fonction = groupe, parametre = feuille executable.
            function_node = current.get_or_create_child(function_name, kind="function")
            function_node.get_or_create_child(param_label, nodeid=nodeid, kind="case")

    return list(roots.values())
