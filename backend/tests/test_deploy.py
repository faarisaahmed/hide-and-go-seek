# -*- coding: utf-8 -*-
"""The files that put this game on the internet.

None of this runs in CI beyond being read, but every one of these is a
mistake that only shows up once friends are already trying to join, so
they are worth pinning down here rather than discovering live.
"""

import os
import re

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Every way this app gets started by a host, and where that config lives.
LAUNCHERS = ["Procfile", "render.yaml", "Dockerfile"]


def read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as handle:
        return handle.read()


def launch_commands():
    """The gunicorn invocation out of each deploy file."""
    for name in LAUNCHERS:
        body = " ".join(read(name).split())      # collapse YAML line folds
        match = re.search(r"gunicorn .*?app:app", body)
        assert match, f"{name} does not start the app with gunicorn"
        yield name, match.group(0)


@pytest.mark.parametrize("name", LAUNCHERS)
def test_the_deploy_file_exists(name):
    assert os.path.isfile(os.path.join(REPO, name))


def test_every_deploy_target_runs_exactly_one_worker():
    """Rooms live in one process's memory, so a second worker is a second
    set of rooms — and half your friends join a room the rest cannot see.

    Nothing about that fails loudly, which is exactly why it is pinned.
    """
    for name, command in launch_commands():
        assert re.search(r"-w\s+1\b", command), f"{name} does not pin a single worker"


def test_every_deploy_target_can_serve_websockets():
    """Plain gunicorn workers cannot, and everybody silently drops to
    long-polling, which is miserable over the internet."""
    for name, command in launch_commands():
        assert "GeventWebSocketWorker" in command, f"{name} has no websocket worker"


def test_every_deploy_target_points_at_the_real_app():
    for name, command in launch_commands():
        assert "--chdir backend" in command, f"{name} will not find app.py"
        assert os.path.isfile(os.path.join(REPO, "backend", "app.py"))


def test_every_deploy_target_binds_the_port_the_host_gives_it():
    for name, command in launch_commands():
        assert "$PORT" in command, f"{name} hardcodes a port"


def test_the_websocket_worker_is_actually_installed_by_the_deploy_requirements():
    body = read("backend", "requirements-deploy.txt")

    assert "-r requirements.txt" in body, "deploying would miss Flask itself"
    for package in ["gunicorn", "gevent", "gevent-websocket"]:
        assert package in body, f"{package} is missing"


def test_the_dev_server_can_still_serve_websockets():
    """simple-websocket is what upgrades the Werkzeug dev server.

    Without it, LAN and tunnelled play both fall back to long-polling.
    """
    assert "simple-websocket" in read("backend", "requirements.txt")

    import simple_websocket  # noqa: F401  - the point is that it imports


def test_the_share_script_is_executable():
    path = os.path.join(REPO, "scripts", "share.sh")
    assert os.access(path, os.X_OK), "scripts/share.sh is not executable"


def test_the_share_script_has_more_than_one_tunnel_to_try():
    """These are free services and either can be having a bad day.

    Observed: cloudflared connected fine and printed an address that
    never got a DNS record, so a single-provider script hands over a
    URL that simply does not resolve.
    """
    body = read("scripts", "share.sh")

    assert "cloudflared" in body and "trycloudflare" in body
    # "lhr" rather than "lhr.life": the hostnames appear as escaped
    # regexes in the script, so the literal string is "lhr\.life".
    assert "localhost.run" in body and "lhr" in body


def test_the_share_script_checks_an_address_works_before_handing_it_over():
    """Printing an address is not the same as that address answering."""
    body = read("scripts", "share.sh")

    # It curls the candidate URL before printing it, and moves on if
    # nothing answers.
    assert re.search(r'curl -fs .*"\$url/"', body), "no readiness check on the tunnel"
    assert "trying the next one" in body


def test_the_share_script_avoids_bash_4_only_syntax():
    """macOS ships bash 3.2, where `wait -n` fails instantly and takes
    the tunnel down a second after printing its address."""
    code = [
        line for line in read("scripts", "share.sh").splitlines()
        if not line.lstrip().startswith("#")
    ]
    assert not any("wait -n" in line for line in code)


def test_the_readme_documents_both_ways_to_play_with_distant_friends():
    readme = read("README.md")
    assert "scripts/share.sh" in readme
    assert "DEPLOY.md" in readme
