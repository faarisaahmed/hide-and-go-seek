/*
 * Numbers that shape how the game feels, in one place.
 */

/* Movement, in pixels per second.
 *
 * Per second, not per frame: the old per-frame value meant a 120Hz phone
 * moved twice as fast as a 60Hz laptop, which is not something players
 * should be able to win with. 600 matches what the old value of 10 px per
 * frame worked out to at 60fps. */
export const PLAYER_SPEED = 600;
export const SPRINT_MULTIPLIER = 1.5;

/* Longest frame we will simulate. Without this, coming back to a tab
 * that was in the background hands us a multi-second delta and teleports
 * the player through walls. */
export const MAX_FRAME_SECONDS = 0.05;

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

/* Colours, matching the dusk palette the rest of the UI uses. */
export const COLORS = {
    void: "#0c0f24",        /* outside the map */
    floor: "#232a52",
    wall: "#4a3a6b",
    baseZone: "#2f7d5b",
    localPlayer: "#ffc75a",  /* you are the warm one, easy to find */
    remotePlayer: "#6fb8ff",
    nameTag: "#eceefc",
};

export const NAME_TAG_FONT = "bold 14px Arial";

/* Each player's chosen lobby emoji is drawn on their square. */
export const EMOJI_FONT = "26px sans-serif";

/* Gap between the bottom of a player square and their name. */
export const NAME_TAG_OFFSET = 15;

/* Walls this far outside the viewport are still drawn, so one that is
 * partly on screen does not pop in at the edge. */
export const CULL_MARGIN = 64;
