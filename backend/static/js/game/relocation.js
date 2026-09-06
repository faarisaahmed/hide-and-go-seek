/*
 * Being picked up and put down somewhere else, and being told why.
 *
 * The round moves players in two cases: a hider who never left the base
 * when the count ended, and a seeker who would not leave the base's room
 * alone. Both are rules rather than accidents, and both feel like a bug
 * if the floor simply changes underneath you — so the server sends a
 * reason with the correction and this holds onto it long enough for the
 * HUD to say it out loud.
 */

import { RELOCATION_FADE_SECONDS } from "./config.js";

const WORDS = {
    crowding: "Too close to home when the count ended — hidden for you.",
    camped: "No camping the hall. The house has put you somewhere else.",
};

let current = null;

export function noteRelocation(reason) {
    const words = WORDS[reason];
    if (!words) return;

    current = { words, at: performance.now() };
}

/* What to say right now, or null once it has had its moment. */
export function relocationNote(now) {
    if (current === null) return null;

    if (now - current.at > RELOCATION_FADE_SECONDS * 1000) {
        current = null;
        return null;
    }

    return current.words;
}
