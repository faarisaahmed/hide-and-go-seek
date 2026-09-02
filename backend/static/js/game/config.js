/*
 * Numbers that shape how the game feels, in one place.
 */

/* Movement, in pixels per frame. */
export const PLAYER_SPEED = 10;
export const SPRINT_MULTIPLIER = 1.5;

/* Player square, in pixels. Also used as the collision box. */
export const PLAYER_SIZE = 40;

/* Where a player appears when the game starts. Mirrors SPAWN_X / SPAWN_Y
 * in the server's config.py, which is what other clients are told. */
export const SPAWN_X = 100;
export const SPAWN_Y = 100;

/* How often we tell the server where we are. ~60 times a second, sent
 * whether or not we moved, which keeps other clients from ever showing a
 * stale position. */
export const NETWORK_TICK_MS = 16;

/* Joystick input below this magnitude counts as centred, so a resting
 * thumb does not cause drift. */
export const JOYSTICK_DEADZONE = 0.01;

/* Which map to load. */
export const DEFAULT_MAP = "house1";

/* Colours. */
export const COLORS = {
    floor: "#eeeeee",
    wall: "#634646",
    baseZone: "#7fbd64",
    localPlayer: "#2abb67",
    remotePlayer: "#66b3ff",
    nameTag: "#000000",
};

export const NAME_TAG_FONT = "bold 14px Arial";

/* Gap between the bottom of a player square and their name. */
export const NAME_TAG_OFFSET = 15;
