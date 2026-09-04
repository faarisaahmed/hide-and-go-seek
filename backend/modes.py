# -*- coding: utf-8 -*-
"""The game modes, as data.

Every mode is played in the same house with the same movement and the
same phases. What differs is a handful of answers about what a tag does
and how the round is won, and those live here rather than as branches
scattered through :mod:`game` — a new mode should be a dict, not a rewrite
of the round.

The host picks a mode in the lobby and it is fixed when the round starts,
so nobody can change the rules out from under a hunt already in progress.

The keys
--------

``seekers``
    ``"one"``          — one seeker, everybody else hides.
    ``"all_but_one"``  — one player hides, everybody else seeks. Sardines.

``on_tag``
    What contact between a seeker and a hider does.
    ``"freeze"``   — the hider stops where they stand.
    ``"convert"``  — the hider becomes a second seeker.
    ``"recruit"``  — the *seeker* joins the hider. Only sensible with
                     ``all_but_one``, where contact means you found them.

``rescues``
    Whether a free hider can thaw a frozen one. Only meaningful with
    ``on_tag="freeze"``; nothing else leaves anyone frozen to thaw.

``hiding_conceals``
    Whether furniture hides you from the seeker at all. Off makes the
    round a chase rather than a search.

``home_is_safety``
    Whether standing on the base takes a hider out of play. Off in
    sardines, where there is nothing to run home to.

``vision_radius``
    How far anyone can see. Enforced on the server, so a shorter one is
    a real restriction rather than a darker drawing.

``cone_degrees``
    The seeker's field of view, in degrees, or ``None`` for all round.
    A cone means a seeker can be walked around behind.

``cone_reach``
    How far down that cone they see. Worth having separate from
    ``vision_radius``: a torch that is narrower *and* shorter is only a
    punishment, while one that trades width for distance is a trade.

``round_seconds``
    How long the hunt lasts before the seekers have simply held the house.
"""

import config

# Everything a mode does not say for itself is taken from here, so adding
# a mode means writing down only what makes it different.
_DEFAULTS = {
    "seekers": "one",
    "on_tag": "freeze",
    "rescues": True,
    "hiding_conceals": True,
    "home_is_safety": True,
    "vision_radius": config.VISION_RADIUS,
    "cone_degrees": None,
    "cone_reach": config.VISION_RADIUS,
    "round_seconds": config.ROUND_SECONDS,
}

# Ordered: this is also the order the lobby offers them in, so the plain
# one is first and the odd one out is last.
_MODES = [
    {
        "id": "classic",
        "name": "Classic",
        "blurb": "One seeker. Tagged players freeze until a team-mate "
                 "thaws them. Everybody has to get home.",
    },
    {
        "id": "infection",
        "name": "Infection",
        "blurb": "Get tagged and you join the seekers. The house fills up "
                 "with them, so the last one hiding is in real trouble.",
        "on_tag": "convert",
        # Nobody is ever frozen, so there is nothing to thaw.
        "rescues": False,
        # Shorter, because the hunt accelerates on its own: every catch
        # adds a hunter, and a full-length round would be over long
        # before the clock was.
        "round_seconds": 150,
    },
    {
        "id": "juggernaut",
        "name": "Juggernaut",
        "blurb": "No hiding and no rescues. One seeker, a short clock, and "
                 "a straight run for the base.",
        # Furniture is just furniture. Nothing to search, nowhere to wait
        # it out — the only thing between you and the base is the seeker.
        "hiding_conceals": False,
        # Tagged is out. Without anywhere to hide, a thawed player would
        # be caught again within seconds of standing up.
        "rescues": False,
        # Short on purpose. A pure chase is exhausting rather than tense
        # once it has gone on for minutes.
        "round_seconds": 100,
    },
    {
        "id": "blackout",
        "name": "Blackout",
        "blurb": "The lights are out. Everyone sees barely a room's worth, "
                 "and the seeker has a torch you can step around.",
        # Enough to make out the room you are standing in and not much
        # else. Applies to the seeker too, for anything outside the beam.
        "vision_radius": 200,
        # Narrow, but it reaches most of the way down a corridor. The
        # trade is the point: the seeker sees further than anybody, and
        # only in the direction they last moved.
        "cone_degrees": 70,
        "cone_reach": 560,
        # Longer than Classic. Finding people takes longer in the dark,
        # and a hunt that cannot finish is not a tense one.
        "round_seconds": 300,
    },
]

DEFAULT_MODE = "classic"


def _build():
    built = {}
    for mode in _MODES:
        merged = dict(_DEFAULTS)
        merged.update(mode)
        built[mode["id"]] = merged
    return built


MODES = _build()

# The order the lobby lists them in.
ORDER = [mode["id"] for mode in _MODES]


def get(mode_id):
    """The rules for a mode, falling back to the default if it is unknown.

    Unknown ids arrive from clients, and an unplayable round is a worse
    answer than a classic one.
    """
    return MODES.get(mode_id) or MODES[DEFAULT_MODE]


def is_mode(mode_id):
    return mode_id in MODES


def listing():
    """Modes as the lobby shows them: id, name and one line of blurb."""
    return [
        {
            "id": mode_id,
            "name": MODES[mode_id]["name"],
            "blurb": MODES[mode_id]["blurb"],
        }
        for mode_id in ORDER
    ]
