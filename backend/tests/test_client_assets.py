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


def test_the_colour_picker_offers_exactly_what_the_server_accepts():
    """A swatch the server refuses is a swatch that does nothing when
    tapped, which is worse than one that is not there."""
    source = read("js", "lobby.js")
    listed = re.search(r"const COLORS = \[(.*?)\];", source, re.S).group(1)
    picker = re.findall(r'"([^"]+)"', listed)

    assert picker == config.COLOR_POOL


def test_no_two_players_can_end_up_the_same_colour_by_default():
    """The pool has to be at least as long as a plausible room, or the
    fallback hands two people the same colour on join."""
    assert len(config.COLOR_POOL) == len(set(config.COLOR_POOL))
    assert len(config.COLOR_POOL) >= 8


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

    for element_id in ["emojiPicker", "startButton", "waitingNote", "chatDot"]:
        pattern = rf'id="{element_id}"[^>]*>'
        tag = re.search(pattern, markup, re.S)
        assert tag, f"{element_id} missing from room.html"
        assert "hidden" in tag.group(0), f"{element_id} does not start hidden"


def test_every_control_is_written_down_where_players_will_see_it():
    """A control is only a mechanic if people know it is there.

    Keyboard players had nothing to look at and played whole rounds
    without discovering that Shift runs; touch players had four
    identical circles and no idea which of them did anything. Both are
    spelled out now, on the way in and on the screen itself. If a
    redesign drops one, the mechanic quietly stops existing for half the
    players and nothing else would catch it.
    """
    for page in ["index.html", "room.html", "game.html"]:
        markup = read("..", "templates", page)
        assert "kbd" in markup, f"{page} has no keycaps to read"

        for key in ["Shift", ">Y<"]:
            assert key in markup, f"{page} never mentions {key}"


def test_every_lobby_tab_has_a_panel_to_show():
    """A tab with no panel is a tab that blanks the screen, and the two
    lists are written down a hundred lines apart in the same file."""
    markup = read("..", "templates", "room.html")

    tabs = re.findall(r'class="tab[^"]*"[^>]*data-tab="([^"]+)"', markup)
    panels = re.findall(r'class="tab-panel"[^>]*data-panel="([^"]+)"', markup)

    assert tabs, "room.html has no tabs"
    assert sorted(tabs) == sorted(panels), f"{tabs} vs {panels}"


def test_exactly_one_lobby_tab_starts_open():
    """Two open at once stacks them; none open is a blank screen."""
    markup = read("..", "templates", "room.html")

    panels = re.findall(r'class="tab-panel"[^>]*data-panel="[^"]+"[^>]*>', markup)
    showing = [tag for tag in panels if "hidden" not in tag]

    assert len(showing) == 1, f"{len(showing)} panels start visible"


def test_the_thumb_pad_says_what_its_buttons_do():
    """Four identical circles is a puzzle, not a control scheme."""
    markup = read("..", "templates", "game.html")

    for action in ["Run", "Shout", "Move"]:
        assert action in markup, f"no on-screen label for {action}"


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


# ---------------------------------------------------------------------------
# Numbers the client and the server both need
# ---------------------------------------------------------------------------

def js_constant(source, name):
    """Read `export const NAME = <number>;` out of a JS module."""
    match = re.search(rf"export const {name} = ([0-9.]+);", source)
    assert match, f"{name} is not exported from the game config"
    return float(match.group(1))


def test_the_client_and_server_agree_on_the_round_numbers():
    """The server decides tags and rescues; the client only draws them.

    They still have to agree, or the ring the client paints round the
    seeker is not the distance at which the seeker actually finds you.
    """
    source = read("js", "game", "config.js")

    for name in ["PLAYER_SIZE", "PLAYER_SPEED", "VISION_RADIUS",
                 "SEARCH_DISTANCE", "RESCUE_DISTANCE", "NO_HIDE_RADIUS",
                 "SEEKER_CAMP_SECONDS"]:
        assert js_constant(source, name) == float(getattr(config, name)), name


# ---------------------------------------------------------------------------
# Pages and the scripts that drive them
# ---------------------------------------------------------------------------

# Which page each script runs on, so an element it looks up can be
# checked for. Renaming an id in the markup otherwise breaks the HUD
# silently: getElementById just returns null.
SCRIPT_PAGES = {
    os.path.join("js", "home.js"): "index.html",
    os.path.join("js", "lobby.js"): "room.html",
    os.path.join("js", "game"): "game.html",
}


def page_for(path):
    for prefix, page in SCRIPT_PAGES.items():
        if path.startswith(prefix):
            return page
    return None


def test_every_element_the_scripts_look_up_exists_in_its_page():
    pages = {}

    for root, _, files in os.walk(os.path.join(STATIC, "js")):
        for name in sorted(files):
            if not name.endswith(".js"):
                continue

            path = os.path.join(root, name)
            relative = os.path.relpath(path, os.path.join(STATIC, "js"))
            page = page_for(os.path.join("js", relative))
            if page is None:
                continue

            if page not in pages:
                pages[page] = read("..", "templates", page)

            with open(path, encoding="utf-8") as handle:
                source = handle.read()

            for element_id in re.findall(r'getElementById\("([^"]+)"\)', source):
                assert f'id="{element_id}"' in pages[page], (
                    f"{relative} looks up #{element_id}, missing from {page}"
                )


def test_the_game_page_starts_its_overlays_hidden():
    """main.js and hud.js reveal these; the markup has to start them off.

    Without it the results card covers the game from the moment it loads.
    """
    markup = read("..", "templates", "game.html")

    for element_id in ["connectionBanner", "countdown", "hidingNote",
                       "roundOverlay", "againButton", "hudClock"]:
        tag = re.search(rf'id="{element_id}"[^>]*>', markup, re.S)
        assert tag, f"{element_id} missing from game.html"
        assert "hidden" in tag.group(0), f"{element_id} does not start hidden"


def test_the_map_the_client_loads_is_the_one_the_server_reads():
    """Both sides work out hiding spots and the base from this file."""
    data = json.loads(read("maps", f"{config.DEFAULT_MAP}.json"))

    assert data["base_zones"], "hiders would have nowhere to run home to"
    assert any(item.get("hide") for item in data["furniture"])
    assert any(item.get("solid") for item in data["furniture"])
