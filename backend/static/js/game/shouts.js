/*
 * Shouting: the noise you make, and the noises you hear.
 *
 * Sound is the only thing in this house that goes through walls. Sight
 * stops at the plaster and positions stop at the vision radius, so a
 * shout is the one way to tell somebody in the next room that it is
 * clear, or that you are frozen behind the sofa and could use a hand.
 * It costs what it should: the seeker has ears too.
 *
 * The server never sends a shouter's position — only a bearing rounded
 * to a few degrees and one of three words for how far off it was. So
 * what arrives here is a direction and a volume, which is what a noise
 * in a dark house actually gives you.
 *
 * The tone is synthesised rather than loaded, because the game is played
 * over Wi-Fi that may have no internet and everything else on these
 * pages is served locally too.
 */

import { SHOUT_FADE_SECONDS } from "./config.js";

/* Shouts heard recently, newest last, each with when it landed so it can
 * be drawn fading out. */
const heard = [];

/* One context for the page. Browsers refuse to start one before the
 * player has touched something, so it is created on the first input and
 * nudged awake on every shout after that — a tab that was backgrounded
 * comes back with a suspended context. */
let audio = null;

export function unlockAudio() {
    if (audio) {
        if (audio.state === "suspended") audio.resume();
        return;
    }

    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (Ctor) audio = new Ctor();
}

/* How loud a shout of each kind lands. Distance is the whole information
 * content of the sound, so it has to be audible in the volume as well as
 * readable in the HUD. */
const LOUDNESS = { close: 0.24, nearby: 0.13, far: 0.06 };

/*
 * Two quick descending blips — a shout, not a beep. Distinct enough from
 * a notification that nobody looks at their phone, short enough that a
 * room full of people shouting does not become a drone.
 */
function blip(at, from, to, gain) {
    if (!audio) return;

    const osc = audio.createOscillator();
    const level = audio.createGain();

    osc.type = "triangle";
    osc.frequency.setValueAtTime(from, at);
    osc.frequency.exponentialRampToValueAtTime(to, at + 0.13);

    level.gain.setValueAtTime(0.0001, at);
    level.gain.exponentialRampToValueAtTime(gain, at + 0.012);
    level.gain.exponentialRampToValueAtTime(0.0001, at + 0.16);

    osc.connect(level).connect(audio.destination);
    osc.start(at);
    osc.stop(at + 0.18);
}

function play(gain) {
    unlockAudio();
    if (!audio) return;

    const now = audio.currentTime;
    blip(now, 700, 430, gain);
    blip(now + 0.14, 560, 340, gain * 0.8);
}

/* Your own shout, quieter than anybody else's: you already know where
 * you are, and this is only here so the button does something when you
 * are alone at the far end of the house. */
export function playOwnShout() {
    play(0.10);
}

export function noteShout(data) {
    play(LOUDNESS[data.nearness] ?? LOUDNESS.far);
    heard.push({ ...data, at: performance.now() });
}

/* Compass words, because "north-east" is something you can act on and
 * 0.78 radians is not. Screen coordinates, so +y is south. */
const POINTS = ["east", "south-east", "south", "south-west",
                "west", "north-west", "north", "north-east"];

export function compassWord(bearing) {
    const eighth = Math.PI / 4;
    const index = Math.round(bearing / eighth) & 7;
    return POINTS[index];
}

/* Shouts still worth drawing, oldest first, each with how far through
 * its fade it is. Trims the list as it goes, so nothing has to remember
 * to tidy up. */
export function activeShouts(now) {
    while (heard.length && now - heard[0].at > SHOUT_FADE_SECONDS * 1000) {
        heard.shift();
    }

    return heard.map((shout) => ({
        ...shout,
        life: 1 - (now - shout.at) / (SHOUT_FADE_SECONDS * 1000),
    }));
}

/* The most recent one, for the HUD line. Null once they have all faded. */
export function latestShout(now) {
    const live = activeShouts(now);
    return live.length ? live[live.length - 1] : null;
}
