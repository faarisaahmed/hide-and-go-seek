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
