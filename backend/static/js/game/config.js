/*
 * Numbers that shape how the game feels, in one place.
 */

/* Movement, in pixels per frame. */
export const PLAYER_SPEED = 10;
export const SPRINT_MULTIPLIER = 1.5;

/* Player square, in pixels. Also used as the collision box. */
export const PLAYER_SIZE = 40;

/* How often we check whether our position is worth sending. ~60 times a
 * second, but a message only goes out when we actually moved. */
export const NETWORK_TICK_MS = 16;

/* Resend our position at least this often even when standing still, so a
 * dropped packet cannot leave us frozen in someone else's view. */
export const POSITION_KEEPALIVE_MS = 1000;

/* Joystick input below this magnitude counts as centred, so a resting
 * thumb does not cause drift. */
export const JOYSTICK_DEADZONE = 0.01;

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

/* Each player's chosen lobby emoji is drawn on their square. */
export const EMOJI_FONT = "26px sans-serif";

/* Gap between the bottom of a player square and their name. */
export const NAME_TAG_OFFSET = 15;
