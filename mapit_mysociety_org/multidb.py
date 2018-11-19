"""
A getter/setter for a thread-local variable for using the primary database.
"""

import threading

_locals = threading.local()


def use_primary(val=None):
    """If passed no argument, return the current value (or False if unset);
    if passed an argument, set the variable to that."""
    if val is None:
        return getattr(_locals, 'primary', False)
    else:
        _locals.primary = val
