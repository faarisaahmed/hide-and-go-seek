# -*- coding: utf-8 -*-
"""Reading map files.

The server reads the same JSON the browser downloads, so spawn points can
be handed out authoritatively instead of every player starting stacked on
the same tile.
"""

import json
import os
import random

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


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

def rooms_of(name):
    """The rooms of a map: the walkable interiors, not counting walls."""
    return _rects(name, "rooms")


def in_rect(rect, cx, cy):
    """Is this point inside a rectangle?"""
    return (rect["x"] <= cx <= rect["x"] + rect["w"]
            and rect["y"] <= cy <= rect["y"] + rect["h"])


def room_at(name, cx, cy):
    """The room containing a point, or None if it is in a wall or doorway."""
    for room in rooms_of(name):
        if in_rect(room, cx, cy):
            return room
    return None


def base_room(name):
    """The room the home base sits in, or None.

    What the seeker is not allowed to loiter in. The base itself is a
    small square and standing beside it is as good as standing on it, so
    the rule that matters is about the *room*.
    """
    return room_at(name, *base_center(name))


def _solid_furniture(name):
    return [item for item in _rects(name, "furniture") if item.get("solid")]


def random_standing_spot(name, avoid=None, attempts=80):
    """A random top-left corner somewhere a player can stand.

    Used to move a seeker on when they will not leave the base room
    alone. Random rather than a fixed penalty spot, because a penalty you
    can predict is one you can plan around — being flung somewhere and
    having to work out where you are is the point.

    Rooms are interiors, so anywhere inside one with a player's width of
    margin is clear of the walls; only the solid furniture has to be
    checked. Falls back to a spawn point if a map is so cluttered that
    eighty tries find nothing, since a seeker left standing where they
    were is worse than one moved somewhere dull.
    """
    size = config.PLAYER_SIZE
    choices = [
        room for room in rooms_of(name)
        if room is not avoid
        and room["w"] > size * 3 and room["h"] > size * 3
    ]
    if not choices:
        return spawn_point(name, 0)

    blocked = _solid_furniture(name)

    for _ in range(attempts):
        room = random.choice(choices)
        x = random.uniform(room["x"] + size, room["x"] + room["w"] - size * 2)
        y = random.uniform(room["y"] + size, room["y"] + room["h"] - size * 2)

        box = {"x": x, "y": y, "w": size, "h": size}
        if any(_overlaps(box, item) for item in blocked):
            continue

        return x, y

    return spawn_point(name, 0)


def random_standing_spot_center(name, avoid=None):
    """:func:`random_standing_spot`, as a centre rather than a corner."""
    x, y = random_standing_spot(name, avoid=avoid)
    half = config.PLAYER_SIZE / 2
    return x + half, y + half


def _overlaps(a, b):
    return (a["x"] < b["x"] + b["w"] and a["x"] + a["w"] > b["x"]
            and a["y"] < b["y"] + b["h"] and a["y"] + a["h"] > b["y"])


# ---------------------------------------------------------------------------
# Getting about
# ---------------------------------------------------------------------------
#
# Bots need to cross the house, which means knowing that the kitchen
# connects to the living room and not to the cellar. The map already says
# so, in the doorways: each one is a hole punched through the wall
# between exactly two rooms, so probing either side of it gives an
# adjacency list for free rather than needing a grid and a pathfinder.

_navs = {}


def _navigation(name):
    """``(rooms, links)`` for a map, worked out once.

    ``links`` maps a room's index to a list of ``(neighbour index, door
    centre)``. Corridors are rooms like any other here — they have no
    name, but they are what most of the house connects *through*.
    """
    if name in _navs:
        return _navs[name]

    rooms = rooms_of(name)
    at = {id(room): index for index, room in enumerate(rooms)}
    links = {index: [] for index in range(len(rooms))}

    for door in _rects(name, "doorways"):
        cx = door["x"] + door["w"] / 2
        cy = door["y"] + door["h"] / 2

        # A doorway is a gap in a wall, so it is long along the wall and
        # thin across it. Probing just past each thin end lands in the
        # two rooms it joins.
        if door["w"] >= door["h"]:
            sides = [(cx, door["y"] - 2), (cx, door["y"] + door["h"] + 2)]
        else:
            sides = [(door["x"] - 2, cy), (door["x"] + door["w"] + 2, cy)]

        both = [room_at(name, *side) for side in sides]
        if any(room is None for room in both):
            continue

        first, second = (at[id(room)] for room in both)
        if first == second:
            continue

        links[first].append((second, (cx, cy)))
        links[second].append((first, (cx, cy)))

    _navs[name] = (rooms, links)
    return _navs[name]


def _nearest_room(name, cx, cy):
    """Index of the room containing a point, or of the closest one.

    Somebody standing in a doorway is in no room at all, which is exactly
    the moment they most need to be told where to go next.
    """
    rooms, _ = _navigation(name)

    best = None
    best_gap = None

    for index, room in enumerate(rooms):
        if in_rect(room, cx, cy):
            return index

        gap_x = max(room["x"] - cx, 0, cx - (room["x"] + room["w"]))
        gap_y = max(room["y"] - cy, 0, cy - (room["y"] + room["h"]))
        gap = gap_x * gap_x + gap_y * gap_y

        if best_gap is None or gap < best_gap:
            best, best_gap = index, gap

    return best


def route(name, start, goal):
    """Waypoints from ``start`` to ``goal``: the doors, then the goal.

    A breadth-first walk of the room graph, so a bot crossing the house
    aims at the next doorway rather than at the wall between it and where
    it wants to be. Returns just ``[goal]`` when both ends are in the
    same room, and ``[]`` when there is no way through at all — which on
    a sane map means the goal is somewhere nobody can stand.
    """
    rooms, links = _navigation(name)
    if not rooms:
        return [goal]

    here = _nearest_room(name, *start)
    there = _nearest_room(name, *goal)
    if here is None or there is None:
        return [goal]
    if here == there:
        return [goal]

    # Breadth-first: every edge is a doorway, so the fewest doorways is
    # a good enough answer and a much cheaper one than weighing them.
    came_from = {here: None}
    queue = [here]

    while queue:
        current = queue.pop(0)
        if current == there:
            break

        for neighbour, door in links[current]:
            if neighbour in came_from:
                continue
            came_from[neighbour] = (current, door)
            queue.append(neighbour)

    if there not in came_from:
        return []

    doors = []
    step = there
    while came_from[step] is not None:
        previous, door = came_from[step]
        doors.append(door)
        step = previous

    doors.reverse()
    return doors + [goal]


def walk(name, x, y, dx, dy, size):
    """Move a box and stop it at whatever it runs into. Returns ``(x, y)``.

    The mirror of moveWithCollision in the browser's physics.js, and
    resolved the same way — one axis at a time, so a bot sliding along a
    wall slides rather than sticking. It exists because bots are moved by
    the server and nothing else on this side had ever needed to know that
    walls are solid: every human player brings their own collision.
    """
    obstacles = _rects(name, "walls") + _solid_furniture(name)

    x += dx
    box = {"x": x, "y": y, "w": size, "h": size}
    for item in obstacles:
        if not _overlaps(box, item):
            continue
        if dx > 0:
            x = item["x"] - size
        elif dx < 0:
            x = item["x"] + item["w"]
        box["x"] = x

    y += dy
    box["y"] = y
    for item in obstacles:
        if not _overlaps(box, item):
            continue
        if dy > 0:
            y = item["y"] - size
        elif dy < 0:
            y = item["y"] + item["h"]
        box["y"] = y

    return x, y


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
