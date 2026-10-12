"""Operation timeouts shared by the Settings page and all run contexts."""

DEFAULTS = {
    "collection_timeout": 120,
    "interpreter_timeout": 15,
    "reader_discovery_timeout": 10,
    "atr_startup_timeout": 10,
}
MIN_SECONDS = 1
MAX_SECONDS = 86400


def seconds(widget, key):
    """Read the owning window's preferences, including detached/run pages."""
    while widget is not None:
        controller = getattr(widget, "preferences", None)
        host = getattr(widget, "_run_host", None)
        if controller is None and host is not None:
            controller = getattr(host, "preferences", None)
        if controller is not None:
            return controller.values.get(key, DEFAULTS[key])
        widget = widget.parent()
    return DEFAULTS[key]
