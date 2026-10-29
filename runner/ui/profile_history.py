"""Historique borne des brouillons, sans reecrire les profils sauvegardes."""
import copy
import json
import zlib
from functools import wraps
from time import monotonic

from PySide6.QtGui import QUndoCommand


def _pack(state):
    # Des milliers d'occurrences repetent les memes chemins et metadonnees.
    # Compresser les instantanes evite de multiplier leur cout memoire par 50.
    return zlib.compress(json.dumps(state, ensure_ascii=False, allow_nan=False,
                                   separators=(',', ':')).encode('utf-8'), level=3)


def _unpack(state):
    return json.loads(zlib.decompress(state).decode('utf-8'))


def undoable(label, *, after_drop=False):
    def decorate(function):
        @wraps(function)
        def call(page, *args, **kwargs):
            outer = page._edit_depth == 0 and not page._building
            before = (copy.deepcopy(page._history_state) if after_drop else page._editor_state()) if outer else None
            page._edit_depth += 1
            try:
                result = function(page, *args, **kwargs)
            finally:
                page._edit_depth -= 1
            if outer:
                page._record_edit(before, label)
            return result
        return call
    return decorate


class ProfileEdit(QUndoCommand):
    def __init__(self, page, before, after, label, merge_key=None):
        super().__init__(label)
        self.page = page
        self.before = _pack(before)
        self.after = _pack(after)
        self.merge_key = merge_key
        self.time = monotonic()
        self.first = True

    def id(self):
        return 1 if self.merge_key is not None else -1

    def mergeWith(self, other):
        if self.merge_key != other.merge_key or other.time - self.time > 1:
            return False
        self.after = other.after
        self.time = other.time
        return True

    def undo(self):
        self.page._restore_editor_state(_unpack(self.before))

    def redo(self):
        if self.first:
            self.first = False
        else:
            self.page._restore_editor_state(_unpack(self.after))
