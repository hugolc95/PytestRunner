"""Savoir si une carte est dans un lecteur, sans jamais s'y connecter.

`SCardGetStatusChange` (PC/SC, winscard.dll) demande a Windows l'etat qu'il
suit deja pour chaque lecteur : il ne se connecte pas a la carte, ne
l'alimente pas et n'envoie rien. C'est ce qui permet de ne relire l'ATR --
lui, par `OpenReader`/`GetATR` -- que quand une carte arrive ou part, au lieu
d'ouvrir le lecteur a intervalle regulier.

Appel non bloquant (delai nul) et bibliotheque systeme presente en 32 comme en
64 bits : il peut tourner dans le processus de l'interface, contrairement a
PyHubReader.
"""

from __future__ import annotations

import ctypes
import sys

SCARD_SCOPE_USER = 0
SCARD_S_SUCCESS = 0
SCARD_E_TIMEOUT = 0x8010000A
SCARD_STATE_UNAWARE = 0x0000
SCARD_STATE_UNKNOWN = 0x0004
SCARD_STATE_UNAVAILABLE = 0x0008
SCARD_STATE_PRESENT = 0x0020


class _ReaderState(ctypes.Structure):
    _fields_ = [
        ("szReader", ctypes.c_wchar_p),
        ("pvUserData", ctypes.c_void_p),
        ("dwCurrentState", ctypes.c_ulong),
        ("dwEventState", ctypes.c_ulong),
        ("cbAtr", ctypes.c_ulong),
        ("rgbAtr", ctypes.c_ubyte * 36),
    ]


def _winscard():
    if sys.platform != "win32":
        return None
    try:
        lib = ctypes.WinDLL("winscard")
    except OSError:
        return None
    lib.SCardEstablishContext.argtypes = [
        ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)]
    lib.SCardEstablishContext.restype = ctypes.c_long
    lib.SCardReleaseContext.argtypes = [ctypes.c_size_t]
    lib.SCardReleaseContext.restype = ctypes.c_long
    lib.SCardGetStatusChangeW.argtypes = [
        ctypes.c_size_t, ctypes.c_ulong, ctypes.POINTER(_ReaderState), ctypes.c_ulong]
    lib.SCardGetStatusChangeW.restype = ctypes.c_long
    return lib


class CardPresence:
    """`check(lecteur)` rend une signature de l'etat de la carte, ou None.

    La signature est (carte presente, compteur d'evenements) : Windows compte
    dans les 16 bits hauts de l'etat les insertions et retraits, ce qui trahit
    aussi une carte changee entre deux appels. None quand on ne peut rien
    savoir : pas Windows, service carte a puce arrete, ou lecteur que PC/SC ne
    connait pas (un lecteur propre au hub, par exemple).
    """

    def __init__(self, lib=None):
        self._lib = lib if lib is not None else _winscard()
        self._context = None

    def check(self, reader: str):
        if self._lib is None or not reader:
            return None
        if self._context is None and not self._establish():
            return None
        state = _ReaderState()
        state.szReader = reader
        state.dwCurrentState = SCARD_STATE_UNAWARE
        status = self._lib.SCardGetStatusChangeW(self._context, 0, ctypes.byref(state), 1)
        if status not in (SCARD_S_SUCCESS, SCARD_E_TIMEOUT):
            # Lecteur inconnu, service arrete, contexte perime : on repartira
            # d'un contexte neuf au prochain appel.
            self.close()
            return None
        event = state.dwEventState
        if event & (SCARD_STATE_UNKNOWN | SCARD_STATE_UNAVAILABLE):
            return None
        return bool(event & SCARD_STATE_PRESENT), (event >> 16) & 0xFFFF

    def _establish(self) -> bool:
        context = ctypes.c_size_t()
        if self._lib.SCardEstablishContext(SCARD_SCOPE_USER, None, None,
                                           ctypes.byref(context)) != SCARD_S_SUCCESS:
            return False
        self._context = context.value
        return True

    def close(self) -> None:
        if self._context is not None and self._lib is not None:
            try:
                self._lib.SCardReleaseContext(self._context)
            except OSError:
                pass
        self._context = None
