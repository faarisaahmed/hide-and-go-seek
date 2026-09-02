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

# Which map the game loads. The server reads this file too, to hand out
# spawn points, so client and server cannot disagree about the map.
DEFAULT_MAP = "house1"

# Fallback spawn, used only if a map has no spawn_points.
SPAWN_X = 100
SPAWN_Y = 100

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
