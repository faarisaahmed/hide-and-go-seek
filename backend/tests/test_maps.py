# -*- coding: utf-8 -*-
"""Map data has to be playable, not just well-formed."""

import glob
import json
import os

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
