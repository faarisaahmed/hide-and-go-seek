# -*- coding: utf-8 -*-
"""Reading map files.

The server reads the same JSON the browser downloads, so spawn points can
be handed out authoritatively instead of every player starting stacked on
the same tile.
"""

import json
import os

import config

_MAPS_DIR = os.path.join(os.path.dirname(__file__), "static", "maps")

_cache = {}


def load(name):
    """Return a map's data, or None if there is no such map.

    Parsed once and cached: maps do not change while the server runs.
    """
    if name in _cache:
        return _cache[name]

    # Guard against a name like "../../secrets" reaching the filesystem.
    if not name.replace("_", "").replace("-", "").isalnum():
        return None

    path = os.path.join(_MAPS_DIR, f"{name}.json")
    if not os.path.isfile(path):
        return None

    with open(path, encoding="utf-8") as handle:
        _cache[name] = json.load(handle)

    return _cache[name]


def spawn_point(name, index):
    """Pick the ``index``-th spawn point of a map, wrapping around.

    Spreading players over the map's spawn_points keeps them from all
    appearing on top of each other. Falls back to the configured default
    if the map does not define any.
    """
    game_map = load(name)
    points = (game_map or {}).get("spawn_points") or []

    if not points:
        return config.SPAWN_X, config.SPAWN_Y

    point = points[index % len(points)]
    return point["x"], point["y"]


def _rects(name, key):
    return (load(name) or {}).get(key) or []


# ---------------------------------------------------------------------------
# Line of sight
# ---------------------------------------------------------------------------
#
# Walls stop sight. Only walls: you can see over a sofa, and furniture
# that concealed people would make the hiding-spot rule meaningless. The
# doorways are already holes in the wall rectangles rather than objects
# of their own, so seeing through a door falls out of the geometry
# instead of needing a rule.

_blockers = {}


def sight_blockers(name):
    """Walls as ``(x0, y0, x1, y1)``, worked out once per map."""
    if name not in _blockers:
        _blockers[name] = [
            (w["x"], w["y"], w["x"] + w["w"], w["y"] + w["h"])
            for w in _rects(name, "walls")
        ]
    return _blockers[name]


def _crosses(ax, ay, dx, dy, x0, y0, x1, y1):
    """Does the segment from (ax, ay) along (dx, dy) enter this rectangle?

    The slab method: clip the segment's parameter range against each axis
    in turn and see whether anything is left. Comparisons are strict, so
    a line that runs exactly along a wall's face — which is what a player
    hugging one gives you — grazes rather than blocks.
    """
    near, far = 0.0, 1.0

    for start, delta, low, high in ((ax, dx, x0, x1), (ay, dy, y0, y1)):
        if delta == 0:
            if start <= low or start >= high:
                return False
            continue

        first = (low - start) / delta
        last = (high - start) / delta
        if first > last:
            first, last = last, first

        near = max(near, first)
        far = min(far, last)
        if near >= far:
            return False

    return True


def blocks_sight(name, ax, ay, bx, by):
    """Is there a wall between these two points?

    Called for every pair of players who are otherwise in range, so the
    bounding-box reject earns its keep: most of a house's walls are
    nowhere near any given sight line.
    """
    dx, dy = bx - ax, by - ay
    lo_x, hi_x = (ax, bx) if ax <= bx else (bx, ax)
    lo_y, hi_y = (ay, by) if ay <= by else (by, ay)

    for x0, y0, x1, y1 in sight_blockers(name):
        if hi_x <= x0 or lo_x >= x1 or hi_y <= y0 or lo_y >= y1:
            continue
        if _crosses(ax, ay, dx, dy, x0, y0, x1, y1):
            return True

    return False


def base_zones(name):
    """The safe rectangles. Reaching one is how a hider gets home."""
    return _rects(name, "base_zones")


def base_center(name):
    """Centre of the home base, or the middle of the map if it has none.

    Used both to send hiders a direction to run and to measure the
    no-hiding radius around the base.
    """
    zones = base_zones(name)
    if zones:
        zone = zones[0]
        return zone["x"] + zone["w"] / 2, zone["y"] + zone["h"] / 2

    game_map = load(name) or {}
    return game_map.get("width", 0) / 2, game_map.get("height", 0) / 2


def hiding_spots(name):
    """Furniture a player can tuck themselves into.

    These are walkable, unlike solid furniture: standing on one hides you
    from the seeker until they come close enough to search it.
    """
    return [item for item in _rects(name, "furniture") if item.get("hide")]


def hiding_spot_at(name, cx, cy):
    """The hiding spot containing a point, or None.

    Takes the player's centre rather than their box, so half a foot
    sticking out of the wardrobe does not count as hidden.
    """
    for spot in hiding_spots(name):
        if (spot["x"] <= cx <= spot["x"] + spot["w"]
                and spot["y"] <= cy <= spot["y"] + spot["h"]):
            return spot
    return None


def hiding_places(name):
    """Top-left corners that put a player in the middle of a hiding spot.

    Where someone gets moved to if the count ends with them loitering
    next to the base.
    """
    half = config.PLAYER_SIZE / 2
    return [
        (spot["x"] + spot["w"] / 2 - half, spot["y"] + spot["h"] / 2 - half)
        for spot in hiding_spots(name)
    ]


def in_base(name, cx, cy):
    """Is this point inside a base zone?"""
    return any(
        zone["x"] <= cx <= zone["x"] + zone["w"]
        and zone["y"] <= cy <= zone["y"] + zone["h"]
        for zone in base_zones(name)
    )


def touches_base(name, x, y, size):
    """Does a player's whole box overlap a base zone?

    Reaching home is decided on a player's centre — half a foot over the
    line is not home. Keeping the seeker *out* is the opposite question
    and wants the whole box, because the base is a wall to them and you
    do not get to stand with your shoulder inside a wall.
    """
    return any(
        x < zone["x"] + zone["w"] and x + size > zone["x"]
        and y < zone["y"] + zone["h"] and y + size > zone["y"]
        for zone in base_zones(name)
    )
