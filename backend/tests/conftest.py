# -*- coding: utf-8 -*-
"""Shared test fixtures.

Room state is process-global, so every test starts from an empty store.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rooms  # noqa: E402
from app import app as flask_app  # noqa: E402
from extensions import socketio  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    rooms.reset()
    yield
    rooms.reset()


@pytest.fixture
def client():
    return flask_app.test_client()


@pytest.fixture
def sock():
    """Factory for Socket.IO test clients."""
    made = []

    def make():
        c = socketio.test_client(flask_app)
        c.get_received()
        made.append(c)
        return c

    yield make

    for c in made:
        if c.is_connected():
            c.disconnect()


def events(source, name=None):
    """Received events, optionally filtered by name.

    Accepts either a test client or an already-drained list, because
    get_received() empties the queue and some tests need two looks at the
    same batch.
    """
    got = source.get_received() if hasattr(source, "get_received") else source
    if name is None:
        return got
    return [e for e in got if e["name"] == name]


def payloads(source, name):
    return [e["args"][0] for e in events(source, name)]
