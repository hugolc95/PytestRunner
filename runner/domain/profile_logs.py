"""Bind profile occurrences to their files before the next batch changes them."""
from pathlib import Path

from runner.domain.logs import find_test_log
from runner.domain.models import Reader


class ProfileLogIndex:
    def __init__(self, root: Path, build_number: int | None):
        self.root = Path(root)
        self.build_number = build_number
        self.paths: dict[tuple[str, int], Path | None] = {}
        self._used: set[Path] = set()

    def capture(self, execution: str, nodeid: str, reader: Reader,
                executed: bool) -> None:
        key = (execution, reader.index)
        if key in self.paths:
            return
        path = find_test_log(self.root, nodeid, reader.name,
                             build_number=self.build_number,
                             excluded=frozenset(self._used)) if executed else None
        self.paths[key] = path
        if path is not None:
            self._used.add(path)

    def for_execution(self, execution: str,
                      readers: tuple[Reader, ...]) -> dict[int, Path | None]:
        return {reader.index: self.paths.get((execution, reader.index))
                for reader in readers or (Reader("", 0),)}
