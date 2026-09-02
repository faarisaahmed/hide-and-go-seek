# -*- coding: utf-8 -*-
"""The documented way to start the server must actually start it."""

import os
import socket
import subprocess
import sys
import time

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_app_py_serves_the_home_page():
    """`python app.py` used to die on a Werkzeug safety check."""
    port = free_port()
    env = {**os.environ, "PORT": str(port), "DEBUG": "0", "PYTHONUNBUFFERED": "1"}

    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=BACKEND, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            if proc.poll() is not None:
                pytest.fail(f"server exited:\n{proc.stdout.read()}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("server never started listening")

        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
            assert response.status == 200
            body = response.read().decode()

        # Assert on something functional rather than on wording, which is
        # free to change with the design.
        assert 'id="createRoomButton"' in body
        assert "js/home.js" in body
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_readme_run_command_matches_reality():
    readme = open(os.path.join(os.path.dirname(BACKEND), "README.md"), encoding="utf-8").read()
    assert "python app.py" in readme
    assert os.path.isfile(os.path.join(BACKEND, "app.py"))
