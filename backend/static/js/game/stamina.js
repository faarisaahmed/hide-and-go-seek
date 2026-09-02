/*
 * Sprint stamina.
 *
 * Sprinting is only a real decision if it runs out. A full bar buys
 * SPRINT_SECONDS of running; emptying it locks sprint off entirely until
 * the bar has come back a good way, so you cannot tap the button on and
 * off to get a permanent speed boost.
 *
 * This is a feel mechanic and lives on the client. The server does not
 * check movement speed — it takes each client's word for its own
 * position, as it always has — so this is not a rule anyone is being
 * held to, it is the thing that makes a chase have a shape.
 */

import {
    EXHAUSTED_CLEARS_AT,
    RECOVER_SECONDS,
    RECOVERY_DELAY_SECONDS,
    SPRINT_SECONDS,
} from "./config.js";

/* 0 to 1. */
let level = 1;

/* Seconds since we last sprinted, so recovery does not start the instant
 * you let go of the button. */
let resting = 0;

/* True from the moment the bar empties until it has recovered enough to
 * be worth using again. */
let spent = false;

export function getStamina() {
    return { level, spent };
}

/* A new round starts everybody fresh. */
export function resetStamina() {
    level = 1;
    resting = 0;
    spent = false;
}

/*
 * Advance the bar by one frame and answer the only question the game
 * loop actually has: are we sprinting right now?
 */
export function stepStamina(dt, wantsToSprint) {
    const sprinting = wantsToSprint && !spent && level > 0;

    if (sprinting) {
        level = Math.max(0, level - dt / SPRINT_SECONDS);
        resting = 0;
        if (level === 0) spent = true;
        return true;
    }

    resting += dt;
    if (resting >= RECOVERY_DELAY_SECONDS) {
        level = Math.min(1, level + dt / RECOVER_SECONDS);
    }
    if (spent && level >= EXHAUSTED_CLEARS_AT) {
        spent = false;
    }

    return false;
}
