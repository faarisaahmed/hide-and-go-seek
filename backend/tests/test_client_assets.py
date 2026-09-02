# -*- coding: utf-8 -*-
"""Checks that the browser code and the server agree.

The client is plain JavaScript with no build step, so nothing else would
catch these two lists drifting apart, or a page pointing at a file that
was renamed.
"""

import json
import os
import re

import config

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


def read(*parts):
    with open(os.path.join(STATIC, *parts), encoding="utf-8") as handle:
        return handle.read()


def test_the_emoji_picker_offers_exactly_what_the_server_accepts():
    source = read("js", "lobby.js")
    listed = re.search(r"const EMOJIS = \[(.*?)\];", source, re.S).group(1)
    picker = re.findall(r'"([^"]+)"', listed)

    assert picker == config.EMOJI_POOL


def test_every_page_asset_exists(client):
    for path in ["/", "/room_page", "/game_page"]:
        html = client.get(path).get_data(as_text=True)
        for asset in re.findall(r'(?:src|href)="(/static/[^"]+)"', html):
            assert client.get(asset).status_code == 200, f"{path} -> {asset}"


def test_every_module_import_resolves():
    for root, _, files in os.walk(os.path.join(STATIC, "js")):
        for name in files:
            if not name.endswith(".js"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            for spec in re.findall(r'from\s+"([^"]+)"', source):
                target = os.path.normpath(os.path.join(root, spec))
                assert os.path.isfile(target), f"{path} imports missing {spec}"


def test_the_default_map_exists_and_has_spawn_points():
    data = json.loads(read("maps", f"{config.DEFAULT_MAP}.json"))
    assert data["spawn_points"], "players would all stack on the fallback spawn"
    assert data["walls"]


def test_elements_the_lobby_reveals_start_hidden():
    """lobby.js toggles these; the markup has to start them off.

    If the template dropped `hidden`, the emoji grid and both the host
    button and the waiting note would all show at once on load.
    """
    markup = read("..", "templates", "room.html")

    for element_id in ["emojiPicker", "startButton", "waitingNote"]:
        pattern = rf'id="{element_id}"[^>]*>'
        tag = re.search(pattern, markup, re.S)
        assert tag, f"{element_id} missing from room.html"
        assert "hidden" in tag.group(0), f"{element_id} does not start hidden"


def test_pages_load_nothing_from_the_internet():
    """The game is played over a LAN, which may have no internet.

    A CDN <script> for socket.io meant that on a router with no upstream
    connection the client never loaded and multiplayer silently died, so
    everything is served from this app.
    """
    import glob

    for path in glob.glob(os.path.join(os.path.dirname(STATIC), "templates", "*.html")):
        with open(path, encoding="utf-8") as handle:
            markup = handle.read()

        for url in re.findall(r'(?:src|href)="(https?://[^"]+)"', markup):
            raise AssertionError(f"{os.path.basename(path)} loads {url} remotely")


def test_socket_io_is_vendored_and_served(client):
    response = client.get("/static/vendor/socket.io.min.js")
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    assert "Socket.IO" in body
    assert len(body) > 10000, "looks truncated"


def test_no_hardcoded_host_in_the_client():
    # A hardcoded LAN address used to break play on any other network.
    for root, _, files in os.walk(os.path.join(STATIC, "js")):
        for name in files:
            if not name.endswith(".js"):
                continue
            with open(os.path.join(root, name), encoding="utf-8") as handle:
                source = handle.read()
            code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
            assert not re.search(r'"https?://', code), f"{name} hardcodes a host"
