# -*- coding: utf-8 -*-
"""Tunable constants for the server.

Kept in one place so gameplay numbers can be adjusted without hunting
through the request handlers.
"""

import os

# Dev server. 0.0.0.0 so phones on the same Wi-Fi can reach it, not just
# this machine. Override with HOST / PORT if 5000 is taken (macOS gives it
# to AirPlay Receiver when that is switched on).
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", 5000))
DEBUG = os.environ.get("DEBUG", "1") != "0"

# Room codes are numeric so they are easy to read out loud and type on a
# phone. Four digits gives 9000 possible codes, which is plenty for a
# game played over one Wi-Fi network.
ROOM_CODE_MIN = 1000
ROOM_CODE_MAX = 9999
ROOM_CODE_LENGTH = 4

# Joining players are handed the first unused emoji from this pool, so a
# room starts out with everyone visually distinct. They can still pick a
# different one in the lobby.
EMOJI_POOL = [
    "\U0001F600", "\U0001F603", "\U0001F604", "\U0001F601", "\U0001F606",
    "\U0001F60A", "\U0001F642", "\U0001F972", "\U0001F622", "\U0001F60E",
    "\U0001F920", "\U0001F973", "\U0001F63A", "\U0001F438", "\U0001F33A",
    "\U0001F400", "\U0001F913", "\U0001F425", "\U0001F413",
]

# Which map the game loads. The server reads this file too, so client and
# server cannot disagree about where the base is or what counts as a
# hiding spot.
DEFAULT_MAP = "house1"

# Fallback spawn, used only if a map has no spawn_points.
SPAWN_X = 100
SPAWN_Y = 100

# ---------------------------------------------------------------------------
# The round
# ---------------------------------------------------------------------------
# One player is the seeker. Everyone starts on the home base in the middle
# of the house; the seeker counts while the rest scatter and hide. After
# that the seeker hunts: a tagged hider is frozen until a free hider
# thaws them, and hiders win by getting every one of themselves back onto
# the base.

# Players are held still while the last few clients finish loading the
# game page, so nobody loses hiding time to a slow phone.
GATHER_SECONDS = 8

# The classic count of twenty. The seeker cannot move or see anyone while
# it runs — that is the whole point of counting.
COUNTDOWN_SECONDS = 20

# A hunt has to end even if the last hider never breaks cover. Running
# out of time is a win for the seeker: they held the house.
ROUND_SECONDS = 240

# Everything below is measured centre to centre, in pixels.

# Must match PLAYER_SIZE in static/js/game/config.js. The server needs it
# to work out player centres from the top-left corners it stores.
PLAYER_SIZE = 40

# Touching distance. Slightly more than PLAYER_SIZE so a tag lands when
# the two squares visibly overlap rather than only on an exact hit.
TAG_DISTANCE = 48

# How close the seeker must get before a hider tucked into a hiding spot
# is revealed. Larger than TAG_DISTANCE on purpose: you get a moment to
# bolt as they walk up to the wardrobe.
SEARCH_DISTANCE = 120

# Thawing a frozen team-mate: stand this close for this long. The hold is
# what makes a rescue a decision rather than an accident, since it leaves
# the rescuer standing still in the open.
RESCUE_DISTANCE = 60
RESCUE_HOLD_SECONDS = 1.5

# How far anyone can see. Positions beyond this are never sent to a
# client, so a dark house cannot be undone by reading the network.
VISION_RADIUS = 420

# Hiding right next to the base and stepping in the moment the count ends
# is not hiding. Anyone still this close when the count ends is moved out
# to a real hiding spot.
NO_HIDE_RADIUS = 400

# Being moved is the one time the server relocates a player who is
# otherwise free to move. Their client has position updates in flight
# that still claim the old spot, and accepting one would quietly undo the
# relocation, so their moves are refused for long enough to hear the
# correction back.
RELOCATE_PIN_SECONDS = 0.4

# How often the server re-checks tags, rescues and timers on its own.
# Movement also triggers a check, so this mainly drives the clock.
GAME_TICK_SECONDS = 0.1

# Ceiling on move-driven checks, so sixty position updates a second from
# each player do not mean sixty full passes each.
RESOLVE_INTERVAL_SECONDS = 0.03

# A seeker with nobody to seek is not a game.
MIN_PLAYERS = 2

# A player navigating from the lobby to the game briefly drops their
# socket. Rather than treat that as leaving, we keep them in the room for
# this long and only drop them if they never come back. This also means a
# refresh or a phone locking for a moment does not lose your place.
DISCONNECT_GRACE_SECONDS = 20

# Input limits. Names show up in the lobby and above players in the game,
# so they need to stay short enough to read.
MAX_NAME_LENGTH = 16
MAX_CHAT_LENGTH = 200

# Oldest chat messages are dropped past this many, so a long-running room
# cannot grow without bound.
MAX_CHAT_MESSAGES = 50
