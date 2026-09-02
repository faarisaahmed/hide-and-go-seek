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
