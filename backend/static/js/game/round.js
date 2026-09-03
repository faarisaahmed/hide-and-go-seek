/*
 * The round, as the client understands it.
 *
 * The server owns all of this: who the seeker is, who is frozen, who
 * made it home, and when each phase ends. This module just holds the
 * last thing it said and keeps the countdown ticking between messages,
 * since the server only broadcasts when something actually changes.
 */

const round = {
    phase: "lobby",
    /* Which mode the server started this round in. The rules are its
     * business; the client only needs it to say the right things. */
    mode: "classic",
    modeName: "Classic",
    tagger: null,
    winner: null,
    note: null,
    players: [],
    tally: { hiders: 0, free: 0, frozen: 0, safe: 0 },

    /* Whole seconds at the moment the message arrived, counted down from
     * there rather than re-asked for. */
    countdown: null,
    roundCountdown: null,
    receivedAt: 0,
};

export function getRound() {
    return round;
}

export function applyState(state) {
    if (!state) return;

    round.phase = state.phase;
    round.mode = state.mode ?? round.mode;
    round.modeName = state.modeName ?? round.modeName;
    round.tagger = state.tagger;
    round.winner = state.winner;
    round.note = state.note;
    round.players = state.players ?? [];
    round.tally = state.tally ?? round.tally;
    round.countdown = state.secondsLeft;
    round.roundCountdown = state.roundSecondsLeft;
    round.receivedAt = performance.now();
}

function tickDown(seconds) {
    if (seconds === null || seconds === undefined) return null;

    const elapsed = (performance.now() - round.receivedAt) / 1000;
    return Math.max(0, Math.ceil(seconds - elapsed));
}

/* Seconds left in the current phase — the count, or the wait to start. */
export function secondsLeft() {
    return tickDown(round.countdown);
}

/* Seconds left in the hunt as a whole. */
export function roundSecondsLeft() {
    return tickDown(round.roundCountdown);
}

/* A player's public round record, by name. */
export function playerNamed(name) {
    return round.players.find((player) => player.name === name) ?? null;
}

/*
 * Whether a player may move themselves, mirroring game.can_move on the
 * server. The server enforces it and will snap us back if we disagree;
 * this copy is so the joystick goes dead immediately instead of a round
 * trip later.
 */
export function canMove(role, state) {
    switch (round.phase) {
        case "gathering":
            return false;
        case "counting":
            return role !== "tagger";
        case "hunting":
            return state !== "frozen";
        default:
            return true;
    }
}
