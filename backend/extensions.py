# -*- coding: utf-8 -*-
"""Flask extension objects.

These are created unbound and attached to the app in
:func:`app.create_app`. Keeping them in their own module lets ``routes``
and ``events`` import them without importing ``app`` (which would be a
circular import).
"""

from flask_socketio import SocketIO

socketio = SocketIO()
