/*
 * Numbers that shape how the game feels, in one place.
 *
 * The distances and durations under "The round" are mirrors of the same
 * names in the server's config.py. The server is the one that decides
 * who is tagged, thawed or home; these copies exist so the client can
 * draw a search radius or grey out the joystick without waiting for a
 * round trip. If you change one, change both.
 */

/* Movement, in pixels per second.
 *
 * Per second, not per frame: the old per-frame value meant a 120Hz phone
 * moved twice as fast as a 60Hz laptop, which is not something players
 * should be able to win with.
 *
 * Paced for a house rather than an open field. Twenty seconds of
 * counting is enough to reach any room and tuck yourself away, but not
 * enough to case the whole place first. */
export const PLAYER_SPEED = 340;
export const SPRINT_MULTIPLIER = 1.55;

/* ===== Stamina =====
 *
 * A full bar of sprinting, and how long it takes to get back. Recovery
 * is deliberately slower than the burn, so a chase costs the seeker
 * something and a hider who bolted has to find cover rather than keep
 * running. */
export const SPRINT_SECONDS = 4;
export const RECOVER_SECONDS = 7;

/* A beat before recovery starts, so letting go for a frame does not
 * refill anything. */
export const RECOVERY_DELAY_SECONDS = 0.7;

/* Emptying the bar locks sprint off until it is back to this much, which
 * is what stops tapping the button for a permanent boost. */
export const EXHAUSTED_CLEARS_AT = 0.3;

/* Longest frame we will simulate. Without this, coming back to a tab
 * that was in the background hands us a multi-second delta and teleports
 * the player through walls. */
export const MAX_FRAME_SECONDS = 0.05;

/* Player square, in pixels. Also used as the collision box, and it must
 * match PLAYER_SIZE in the server's config.py, which works out player
 * centres from it. */
export const PLAYER_SIZE = 40;

/* How often we check whether our position is worth sending, and a
 * message only goes out when we actually moved.
 *
 * Twenty a second rather than sixty. Over a LAN the difference was free;
 * over the internet it is three times the packets for motion that gets
 * smoothed out at the far end anyway. Twenty updates plus interpolation
 * looks better than sixty raw ones on a jittery connection. */
export const NETWORK_TICK_MS = 50;

/* How quickly a remote player catches up to the last position the server
 * sent. Positions arrive unevenly over the internet, so they are eased
 * towards rather than snapped to; this costs a little under a tenth of a
 * second of lag and buys motion that is not a slideshow. */
export const REMOTE_SMOOTHING_SECONDS = 0.08;

/* Past this gap, easing would send somebody gliding across the house.
 * A jump that big is a relocation or a new round, so just put them
 * there. */
export const REMOTE_SNAP_DISTANCE = 260;

/* Resend our position at least this often even when standing still, so a
 * dropped packet cannot leave us frozen in someone else's view. */
export const POSITION_KEEPALIVE_MS = 1000;

/* Joystick input below this magnitude counts as centred, so a resting
 * thumb does not cause drift. */
export const JOYSTICK_DEADZONE = 0.01;

/* ===== The round ===== */

/* How far anyone can see. Past this the house is drawn but people are
 * not, because the server never sent them. */
export const VISION_RADIUS = 420;

/* How close the seeker has to get to a hiding spot to turn out whoever
 * is in it. Drawn as a ring around the seeker on their own screen. */
export const SEARCH_DISTANCE = 120;

/* Stand this close to a frozen team-mate for this long to thaw them. */
export const RESCUE_DISTANCE = 60;
export const RESCUE_HOLD_SECONDS = 1.5;

/* Hiders still inside this radius when the count ends get moved out to a
 * real hiding spot, so the ring is drawn as a warning while counting. */
export const NO_HIDE_RADIUS = 400;

/* ===== Colours ===== */

/* A night-time blue house: cool blues for the building, cyan for
 * anything that helps you (the base, a hiding spot), rose for the one
 * thing that does not (the seeker). */
export const COLORS = {
    void: "#03060e",         /* outside the map */

    /* One tone per floor material, so a room reads as a kind of room
     * before you have read its label. */
    floors: {
        wood: "#1b2c52",
        tile: "#1f3560",
        carpet: "#182849",
        concrete: "#141f3c",
    },
    floorFallback: "#1b2c52",
    plank: "rgba(0, 0, 0, 0.20)",       /* floorboard seams */
    grout: "rgba(126, 166, 226, 0.07)", /* tile lines */
    threshold: "#28477a",               /* the strip under a doorway */

    wall: "#3a5c94",
    wallTop: "#547cab",      /* lip along the top of each wall */
    wallShadow: "rgba(0, 0, 0, 0.34)",

    window: "#9ad6ff",
    windowFrame: "#5a86b8",
    /* Moonlight pooling on the floor under a window. */
    moonlight: "rgba(154, 214, 255, 0.16)",

    solid: "#2a4577",        /* furniture you cannot walk through */
    hide: "#2f6f96",         /* furniture you can hide inside */
    decor: "#1b2f58",        /* rugs and mats */

    base: "#2fd4c0",         /* home */
    baseRing: "rgba(47, 212, 192, 0.35)",
    noHideRing: "rgba(255, 107, 129, 0.5)",
    searchRing: "rgba(255, 107, 129, 0.28)",
    rescueRing: "rgba(94, 230, 168, 0.45)",

    tagger: "#ff6b81",
    hider: "#6fb8ff",
    frozen: "#a9d6ff",
    safe: "#5ee6a8",
    you: "#ffffff",          /* ring around your own square */

    nameTag: "#dce6fa",
    roomLabel: "rgba(150, 178, 224, 0.5)",

    /* Beyond the vision radius the house is still drawn, just dimmed —
     * you can find your way around a dark room, you just cannot see who
     * is standing in it. */
    darkness: "rgba(3, 6, 14, 0.82)",
    /* The seeker's own screen while they count. */
    blindfold: "rgba(3, 6, 14, 0.97)",
};

export const NAME_TAG_FONT = "bold 13px Arial";
export const ROOM_LABEL_FONT = "bold 15px Arial";

/* Floorboard and tile spacing, in world pixels. */
export const PLANK_HEIGHT = 44;
export const PLANK_LENGTH = 260;
export const TILE_SIZE = 76;

/* How far moonlight reaches into a room from its window. */
export const MOONLIGHT_REACH = 190;

/* Each player's chosen lobby emoji is drawn on their square. */
export const EMOJI_FONT = "24px sans-serif";

/* Furniture icons are drawn to fit, down to this floor. */
export const FURNITURE_FONT_MAX = 34;
export const FURNITURE_FONT_MIN = 16;

/* Gap between the bottom of a player square and their name. */
export const NAME_TAG_OFFSET = 14;

/* Walls this far outside the viewport are still drawn, so one that is
 * partly on screen does not pop in at the edge. */
export const CULL_MARGIN = 64;
