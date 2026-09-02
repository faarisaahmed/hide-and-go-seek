# -*- coding: utf-8 -*-
"""Map data has to be playable, not just well-formed.

The house is hand-written JSON, so the checks that matter are the ones a
human editing it would get wrong: a doorway too narrow to walk through, a
wardrobe with a table in front of it, a hiding spot close enough to the
base to make hiding pointless.
"""

import glob
import math
import os
from collections import deque

import pytest

import config
import maps

MAPS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "maps"
)

# Must match PLAYER_SIZE in static/js/game/config.js.
PLAYER_SIZE = 40


def map_names():
    return [
        os.path.splitext(os.path.basename(path))[0]
        for path in sorted(glob.glob(os.path.join(MAPS_DIR, "*.json")))
    ]


def overlaps(x, y, size, wall):
    return (
        x < wall["x"] + wall["w"]
        and x + size > wall["x"]
        and y < wall["y"] + wall["h"]
        and y + size > wall["y"]
    )


def rects_overlap(a, b):
    return (
        a["x"] < b["x"] + b["w"]
        and a["x"] + a["w"] > b["x"]
        and a["y"] < b["y"] + b["h"]
        and a["y"] + a["h"] > b["y"]
    )


def obstacles(data):
    """Everything a player is stopped by: walls plus solid furniture.

    Hiding spots are deliberately excluded — you have to be able to walk
    into a wardrobe to hide in it.
    """
    return data["walls"] + [
        item for item in data.get("furniture", []) if item.get("solid")
    ]


def blocked(data, x, y):
    """Would a player standing here be inside something?"""
    if not (0 <= x <= data["width"] - PLAYER_SIZE
            and 0 <= y <= data["height"] - PLAYER_SIZE):
        return True
    return any(overlaps(x, y, PLAYER_SIZE, r) for r in obstacles(data))


def reachable_cells(data, step=20):
    """Flood fill the house from the base, one player-sized box at a time.

    This is the check that actually keeps the map playable: it is easy to
    park a shoe rack across a doorway and not notice until somebody is
    trapped in the bedroom.

    The grid is anchored to the origin rather than to the base, because
    room and wall coordinates are not all multiples of ``step`` — with a
    grid anchored anywhere else, "is this cell reachable" silently
    becomes "is this cell even on the grid".
    """
    zone = data["base_zones"][0]
    start = (
        round((zone["x"] + zone["w"] / 2 - PLAYER_SIZE / 2) / step) * step,
        round((zone["y"] + zone["h"] / 2 - PLAYER_SIZE / 2) / step) * step,
    )
    assert not blocked(data, *start), "the base itself is blocked"

    seen = {start}
    queue = deque(seen)

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + step, y), (x - step, y), (x, y + step), (x, y - step)):
            if (nx, ny) in seen or blocked(data, nx, ny):
                continue
            seen.add((nx, ny))
            queue.append((nx, ny))

    return seen, step


def reaches(seen, rect):
    """Can a player get to any part of this rectangle?"""
    box = {"w": PLAYER_SIZE, "h": PLAYER_SIZE}
    return any(rects_overlap({**box, "x": x, "y": y}, rect) for x, y in seen)


def can_stand_inside(seen, rect):
    """Can a player get *fully* inside it? Hiding spots have to allow that."""
    return any(
        x >= rect["x"] and x + PLAYER_SIZE <= rect["x"] + rect["w"]
        and y >= rect["y"] and y + PLAYER_SIZE <= rect["y"] + rect["h"]
        for x, y in seen
    )


@pytest.mark.parametrize("name", map_names())
def test_map_parses_and_has_the_expected_shape(name):
    data = maps.load(name)
    assert data is not None

    assert data["width"] > 0 and data["height"] > 0
    assert data["walls"], "a map with no walls is not a house"

    for rect in data["walls"] + data.get("base_zones", []):
        assert all(k in rect for k in ("x", "y", "w", "h"))
        assert rect["w"] > 0 and rect["h"] > 0


@pytest.mark.parametrize("name", map_names())
def test_no_spawn_point_is_inside_a_wall(name):
    """A player spawned inside a wall is stuck the moment they arrive.

    Two of house1's four spawn points were inside walls, including the
    first one — so the host always started wedged in a wall.
    """
    data = maps.load(name)

    for point in data.get("spawn_points", []):
        inside = [
            wall for wall in data["walls"]
            if overlaps(point["x"], point["y"], PLAYER_SIZE, wall)
        ]
        assert not inside, (
            f"{name}: spawn {point['x']},{point['y']} is inside wall {inside[0]}"
        )


@pytest.mark.parametrize("name", map_names())
def test_spawn_points_are_inside_the_map(name):
    data = maps.load(name)

    for point in data.get("spawn_points", []):
        assert 0 <= point["x"] <= data["width"] - PLAYER_SIZE
        assert 0 <= point["y"] <= data["height"] - PLAYER_SIZE


@pytest.mark.parametrize("name", map_names())
def test_spawn_points_are_distinct(name):
    data = maps.load(name)
    points = [(p["x"], p["y"]) for p in data.get("spawn_points", [])]
    assert len(points) == len(set(points))


def test_the_default_map_has_enough_spawns_to_spread_players_out():
    data = maps.load(config.DEFAULT_MAP)
    assert len(data["spawn_points"]) >= 4


# ---------------------------------------------------------------------------
# The house
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", map_names())
def test_furniture_is_well_formed(name):
    data = maps.load(name)

    for item in data.get("furniture", []):
        assert item["w"] > 0 and item["h"] > 0
        assert "label" in item, f"{name}: furniture at {item['x']},{item['y']} has no label"
        # Solid and hideable are opposites: you cannot hide inside
        # something you cannot walk into.
        assert not (item.get("solid") and item.get("hide")), item["label"]


@pytest.mark.parametrize("name", map_names())
def test_no_furniture_is_buried_in_a_wall(name):
    data = maps.load(name)

    for item in data.get("furniture", []):
        inside = [wall for wall in data["walls"] if rects_overlap(item, wall)]
        assert not inside, f"{name}: {item['label']} overlaps wall {inside[0]}"


@pytest.mark.parametrize("name", map_names())
def test_no_spawn_point_is_inside_furniture(name):
    """Everyone starts on the base, so a console table there is fatal."""
    data = maps.load(name)

    for point in data.get("spawn_points", []):
        assert not blocked(data, point["x"], point["y"]), (
            f"{name}: spawn {point['x']},{point['y']} is blocked"
        )


@pytest.mark.parametrize("name", map_names())
def test_the_base_is_in_the_middle_of_the_house(name):
    """The rules say the middle, and the compass arrow assumes it."""
    data = maps.load(name)
    assert data["base_zones"], f"{name} has nowhere to run home to"

    cx, cy = maps.base_center(name)
    assert abs(cx - data["width"] / 2) <= data["width"] * 0.1
    assert abs(cy - data["height"] / 2) <= data["height"] * 0.1


@pytest.mark.parametrize("name", map_names())
def test_every_room_and_hiding_spot_can_be_walked_to_from_the_base(name):
    data = maps.load(name)
    seen, _ = reachable_cells(data)

    for spot in maps.hiding_spots(name):
        assert can_stand_inside(seen, spot), (
            f"{name}: cannot get inside {spot['label']} at {spot['x']},{spot['y']}"
        )

    for room in data.get("rooms", []):
        if room["name"]:
            assert reaches(seen, room), f"{name}: cannot reach {room['name']}"


@pytest.mark.parametrize("name", map_names())
def test_every_doorway_can_actually_be_walked_through(name):
    """A doorway is only drawn; the wall gap is what you walk through.

    Furniture parked against one on either side closes it without
    touching a single wall, which is how the bedroom once ended up
    sealed behind a shoe rack.
    """
    data = maps.load(name)
    seen, _ = reachable_cells(data)

    for door in data.get("doorways", []):
        assert reaches(seen, door), f"{name}: doorway at {door['x']},{door['y']} is blocked"


@pytest.mark.parametrize("name", map_names())
def test_doorways_are_gaps_rather_than_walls(name):
    data = maps.load(name)

    for door in data.get("doorways", []):
        walled = [wall for wall in data["walls"] if rects_overlap(door, wall)]
        assert not walled, (
            f"{name}: doorway at {door['x']},{door['y']} is drawn over wall {walled[0]}"
        )


@pytest.mark.parametrize("name", map_names())
def test_windows_are_set_into_an_outside_wall(name):
    """A window floating in a room would throw moonlight from nowhere."""
    data = maps.load(name)
    width, height = data["width"], data["height"]

    for win in data.get("windows", []):
        outside = (
            win["x"] <= 0 or win["y"] <= 0
            or win["x"] + win["w"] >= width or win["y"] + win["h"] >= height
        )
        assert outside, f"{name}: window at {win['x']},{win['y']} is not on an outside wall"
        assert any(rects_overlap(win, wall) for wall in data["walls"]), (
            f"{name}: window at {win['x']},{win['y']} is not in a wall"
        )


@pytest.mark.parametrize("name", map_names())
def test_every_room_declares_a_floor_the_renderer_knows(name):
    """An unknown material silently falls back and the room looks wrong."""
    data = maps.load(name)

    for room in data.get("rooms", []):
        assert room["floor"] in {"wood", "tile", "carpet", "concrete"}, room


# ---------------------------------------------------------------------------
# Hiding spots
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", map_names())
def test_a_player_fits_inside_every_hiding_spot(name):
    for spot in maps.hiding_spots(name):
        assert spot["w"] >= PLAYER_SIZE and spot["h"] >= PLAYER_SIZE, spot["label"]


@pytest.mark.parametrize("name", map_names())
def test_no_hiding_spot_is_within_the_no_hide_radius(name):
    """Hiders too close to the base get relocated to one of these.

    If a hiding spot were itself inside the forbidden ring, that
    relocation would drop them straight back into an illegal spot.
    """
    cx, cy = maps.base_center(name)

    for x, y in maps.hiding_places(name):
        half = config.PLAYER_SIZE / 2
        away = math.hypot(x + half - cx, y + half - cy)
        assert away >= config.NO_HIDE_RADIUS, (
            f"{name}: a hiding spot sits {away:.0f}px from the base"
        )


def test_the_default_map_has_plenty_of_places_to_hide():
    spots = maps.hiding_spots(config.DEFAULT_MAP)
    assert len(spots) >= 12, "one wardrobe per house makes for a short game"

    # Spread around, not all in the same room.
    corners = {
        (x > 1200, y > 800)
        for x, y in maps.hiding_places(config.DEFAULT_MAP)
    }
    assert len(corners) == 4, "every quarter of the house needs somewhere to hide"


def test_the_base_and_hiding_spot_tests_agree_with_the_server_helpers():
    cx, cy = maps.base_center(config.DEFAULT_MAP)
    assert maps.in_base(config.DEFAULT_MAP, cx, cy)
    assert not maps.in_base(config.DEFAULT_MAP, cx + config.NO_HIDE_RADIUS, cy)

    spot = maps.hiding_spots(config.DEFAULT_MAP)[0]
    assert maps.hiding_spot_at(
        config.DEFAULT_MAP, spot["x"] + spot["w"] / 2, spot["y"] + spot["h"] / 2,
    ) is spot
