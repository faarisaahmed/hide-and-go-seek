/*
 * The heads-up display: what phase the round is in, what you are meant
 * to be doing about it, and who is still out there.
 *
 * All of it is driven by the round state the server broadcasts. The
 * elements are written into game.html rather than built here, so the
 * page has something sensible in it before any JavaScript runs.
 *
 * draw() is called every frame, so every write to the DOM is guarded by
 * a comparison: the browser only does layout work when a value actually
 * changed, not sixty times a second.
 */

import { hideSpotAt } from "./map_loader.js";
import { getRound, playerNamed, roundSecondsLeft, secondsLeft } from "./round.js";
import { getStamina } from "./stamina.js";

const els = {
    role: document.getElementById("hudRole"),
    roleBadge: document.getElementById("hudRoleBadge"),
    name: document.getElementById("hudName"),
    tally: document.getElementById("hudTally"),
    clock: document.getElementById("hudClock"),
    mode: document.getElementById("hudMode"),

    countdown: document.getElementById("countdown"),
    countdownNumber: document.getElementById("countdownNumber"),
    countdownCaption: document.getElementById("countdownCaption"),

    objective: document.getElementById("objective"),
    hidingNote: document.getElementById("hidingNote"),
    stamina: document.getElementById("stamina"),
    staminaFill: document.getElementById("staminaFill"),
    keyHint: document.getElementById("keyHint"),

    overlay: document.getElementById("roundOverlay"),
    overlayTitle: document.getElementById("overlayTitle"),
    overlayNote: document.getElementById("overlayNote"),
    overlayPlayers: document.getElementById("overlayPlayers"),
    againButton: document.getElementById("againButton"),
    overlayHint: document.getElementById("overlayHint"),
    overlayProblem: document.getElementById("overlayProblem"),
};

/* Last value written to each element, so we can skip unchanged writes. */
const shown = {};

/* Whether the player has sprinted yet. The keyboard hint is there to be
 * outgrown: once they have used it, it goes and does not come back. */
let sprintFound = false;

function setText(element, text) {
    if (!element || shown[element.id] === text) return;
    shown[element.id] = text;
    element.textContent = text;
}

function setHidden(element, hidden) {
    if (!element || element.hidden === hidden) return;
    element.hidden = hidden;
}

function setClass(element, className, on) {
    if (!element) return;
    element.classList.toggle(className, on);
}

/* ===== What to tell the player to do =====
 *
 * Every mode is played in the same house, so most of what the HUD says
 * is the same in all of them. Only the lines that genuinely differ are
 * written down per mode; anything a mode leaves out falls through to
 * classic, which is why adding a mode here is a few strings rather than
 * another arm of a switch.
 *
 * The keys are the mode ids from the server's modes.py, and test_modes.py
 * checks that neither list has grown an entry the other has never heard
 * of — a mode with no copy would silently tell people to do the wrong
 * thing, which is worse than one that fails a test.
 */

const OBJECTIVES = {
    classic: {
        counting: {
            tagger: "Eyes shut. Count it out.",
            hider: "Run! Get well clear of the base, then hide.",
        },
        hunting: {
            tagger: "Search the house. Touch a hider to freeze them.",
            frozen: "Frozen. Sit tight — a free hider can thaw you.",
            safe: "You made it home. Now the rest have to.",
            hider: "Get back to the base — or go and thaw a frozen friend.",
        },
    },

    infection: {
        hunting: {
            tagger: "Hunt. Everyone you touch joins you.",
            hider: "Get home. Every catch puts another seeker in the house.",
        },
    },

    juggernaut: {
        counting: {
            hider: "Run! There is nowhere to hide in this one.",
        },
        hunting: {
            tagger: "Run them down. Nothing in this house hides anybody.",
            frozen: "Caught. No thawing in this one — sit it out.",
            hider: "Straight home. The furniture will not save you.",
        },
    },

    blackout: {
        counting: {
            tagger: "Eyes shut. You get a torch when you open them.",
            hider: "Run — it is pitch dark out there. Feel your way.",
        },
        hunting: {
            tagger: "Sweep the house. Your torch points wherever you last moved.",
            hider: "Stay out of the beam. Behind them is the safest place there is.",
        },
    },

    // Backwards: the lone player is the one hiding, and everybody else is
    // a "tagger" as far as the round is concerned.
    sardines: {
        counting: {
            tagger: "Eyes shut. Count, then go and look.",
            hider: "You are the only one hiding. Find somewhere good.",
        },
        hunting: {
            tagger: "Find them. Whoever is last to work it out loses.",
            hider: "Sit tight and stay quiet. They have to come to you.",
        },
    },
};

/* A line for this mode, or the classic one it did not bother to change. */
function line(mode, phase, key) {
    return OBJECTIVES[mode]?.[phase]?.[key]
        ?? OBJECTIVES.classic[phase]?.[key]
        ?? "";
}

function objectiveFor(round, me) {
    const role = me?.role;
    const state = me?.state;
    const mode = round.mode;

    switch (round.phase) {
        case "lobby":
            return "No round yet — the host starts it from the lobby.";
        case "gathering":
            return "Everyone to the base. Hold still…";
        case "counting":
            return line(mode, "counting", role === "tagger" ? "tagger" : "hider");
        case "hunting":
            if (role === "tagger") return line(mode, "hunting", "tagger");
            if (state === "frozen") return line(mode, "hunting", "frozen");
            if (state === "safe") return line(mode, "hunting", "safe");
            return line(mode, "hunting", "hider");
        default:
            return "";
    }
}

function outcomeTitle(round) {
    // Everybody ends up hidden in Sardines, so "hiders win" is true but
    // useless. What the round decided is who was last to work it out,
    // and the server puts that in the note.
    if (round.mode === "sardines") {
        return round.note ? "Found them" : "Everybody found them";
    }

    if (round.winner === "hiders") return "Hiders win";
    if (round.winner !== "tagger") return "Round over";

    // In a mode where the tagged change sides, naming the player who
    // started it as the winner is wrong by the end — most of the room is
    // seeking by then.
    if (round.mode === "infection") return "The seekers win";
    return `${round.tagger || "The seeker"} wins`;
}

function outcomeNote(round) {
    if (round.note) return round.note;
    if (round.mode === "sardines") return "Everybody squeezed in.";
    if (round.winner === "hiders") return "Everybody made it home.";
    if (round.winner === "tagger") {
        return round.mode === "infection"
            ? "Everybody was caught in the end."
            : "Nobody left to find.";
    }
    return "";
}

/* ===== Pieces ===== */

function drawRoleChip(round, me) {
    const role = me?.role;

    let badge = "—";
    if (role === "tagger") badge = "SEEKER";
    else if (role === "hider") badge = "HIDER";

    if (me?.state === "frozen") badge = "FROZEN";
    else if (me?.state === "safe") badge = "HOME";

    setText(els.roleBadge, badge);
    setClass(els.role, "is-seeker", role === "tagger");
    setClass(els.role, "is-frozen", me?.state === "frozen");
    setClass(els.role, "is-safe", me?.state === "safe");
}

function drawTally(round) {
    if (round.phase === "lobby") {
        setText(els.tally, `${round.players.length} in the room`);
        return;
    }

    const { hiders, frozen, safe, seekers } = round.tally;

    // Backwards: there is one person hiding and a roomful looking, and
    // the number worth watching is how few are still out there.
    if (round.mode === "sardines") {
        const hiding = hiders === 1 ? "1 hiding" : `${hiders} squeezed in`;
        setText(els.tally, `${seekers} still looking · ${hiding}`);
        return;
    }

    // Naming the seeker is the useful thing while there is one of them.
    // Once the tagged start changing sides it is the count that matters,
    // and "Alice seeking" would be quietly false.
    if (round.mode === "infection") {
        setText(els.tally, `${seekers} seeking · ${hiders - safe} still hiding · ${safe} home`);
        return;
    }

    const seeking = round.tagger ? `${round.tagger} seeking` : "no seeker";
    setText(els.tally, `${seeking} · ${safe}/${hiders} home · ${frozen} frozen`);
}

/* The mode, once there is a round to have one. */
function drawMode(round) {
    const playing = round.phase !== "lobby";
    setHidden(els.mode, !playing);
    if (playing) setText(els.mode, round.modeName);
}

function drawClock(round) {
    const left = roundSecondsLeft();

    if (round.phase !== "hunting" || left === null) {
        setHidden(els.clock, true);
        return;
    }

    setHidden(els.clock, false);
    const minutes = Math.floor(left / 60);
    const seconds = String(left % 60).padStart(2, "0");
    setText(els.clock, `${minutes}:${seconds}`);
}

/*
 * The big number in the middle: the wait to start, then the count. The
 * seeker sees it on a blacked-out canvas, which is the closest thing to
 * a hand over your eyes.
 */
function drawCountdown(round, me) {
    const counting = round.phase === "counting" || round.phase === "gathering";
    setHidden(els.countdown, !counting);
    if (!counting) return;

    const left = secondsLeft();
    setText(els.countdownNumber, left === null ? "" : String(left));

    if (round.phase === "gathering") {
        setText(els.countdownCaption, "Getting everyone in…");
    } else if (me?.role === "tagger") {
        setText(els.countdownCaption, "…counting");
    } else if (round.mode === "sardines") {
        // One of you is hiding and the rest of the house is counting, so
        // naming a single seeker would be picking one of them at random.
        setText(els.countdownCaption, "Everyone else is counting");
    } else {
        setText(els.countdownCaption, `${round.tagger || "The seeker"} is counting`);
    }

    setClass(els.countdown, "is-blindfolded",
             round.phase === "counting" && me?.role === "tagger");
}

/* "Hidden in the wardrobe", so you know the spot you are standing on is
 * doing something for you. */
function drawHidingNote(map, localPlayer, round, me) {
    const eligible = round.phase === "hunting"
        && round.rules.hidingConceals
        && me?.role === "hider"
        && me?.state === "free";

    const spot = eligible
        ? hideSpotAt(map, localPlayer.x + localPlayer.size / 2,
                     localPlayer.y + localPlayer.size / 2)
        : null;

    setHidden(els.hidingNote, !spot);
    if (spot) setText(els.hidingNote, `Hidden — ${spot.label || "out of sight"}`);
}

/*
 * The sprint bar. Written as a rounded percentage: at sixty frames a
 * second an exact width would be a layout recalculation every frame for
 * a change nobody can see.
 */
function drawStamina() {
    const { level, spent } = getStamina();
    const percent = Math.round(level * 100);

    if (shown.stamina !== percent) {
        shown.stamina = percent;
        els.staminaFill.style.width = `${percent}%`;
    }

    setClass(els.stamina, "is-spent", spent);
    setClass(els.stamina, "is-full", percent === 100);

    // The bar only drains while sprinting, so a level below full is
    // proof the player has found Shift. Latched, because the bar
    // refills and every round starts it back at one.
    if (!sprintFound && level < 1) {
        sprintFound = true;
        setClass(els.keyHint, "is-learnt", true);
    }
}


function drawOverlay(round, me) {
    const over = round.phase === "over";
    setHidden(els.overlay, !over);
    if (!over) return;

    setText(els.overlayTitle, outcomeTitle(round));
    setText(els.overlayNote, outcomeNote(round));

    // Rebuilt only when the roster line actually differs, since this is
    // called every frame while the overlay is up.
    const signature = round.players
        .map((p) => `${p.emoji}${p.name}${p.role}${p.state}`)
        .join("|");

    if (shown.roster !== signature) {
        shown.roster = signature;

        const rows = document.createDocumentFragment();
        for (const player of round.players) {
            const row = document.createElement("li");
            row.className = "result";

            const emoji = document.createElement("span");
            emoji.className = "result__emoji";
            emoji.textContent = player.emoji;

            const name = document.createElement("span");
            name.className = "result__name";
            name.textContent = player.name;

            const outcome = document.createElement("span");
            outcome.className = "result__state";
            if (player.role === "tagger") {
                outcome.textContent = "seeker";
                outcome.classList.add("result__state--seeker");
            } else if (player.state === "safe") {
                outcome.textContent = "home";
                outcome.classList.add("result__state--safe");
            } else if (player.state === "frozen") {
                outcome.textContent = "frozen";
                outcome.classList.add("result__state--frozen");
            } else {
                outcome.textContent = "still out";
            }

            row.append(emoji, name, outcome);
            rows.appendChild(row);
        }
        els.overlayPlayers.replaceChildren(rows);
    }

    const amHost = Boolean(me?.isHost);
    setHidden(els.againButton, !amHost);
    setText(els.overlayHint, amHost ? "" : "Waiting for the host to start another round…");
}

/* ===== Public ===== */

export function initHud({ name, onPlayAgain, onLeave }) {
    setText(els.name, name);
    els.againButton.addEventListener("click", () => {
        els.againButton.disabled = true;
        onPlayAgain();
    });
    document.getElementById("lobbyButton").addEventListener("click", onLeave);
}

/* Shown when the server turns down a request to start a round. Kept in
 * its own element so the next frame's redraw does not wipe it. */
export function showProblem(message) {
    setText(els.overlayProblem, message);
    els.againButton.disabled = false;
}

export function drawHud({ map, localPlayer, myName }) {
    const round = getRound();
    const me = playerNamed(myName);

    drawRoleChip(round, me);
    drawTally(round);
    drawMode(round);
    drawClock(round);
    drawCountdown(round, me);
    drawHidingNote(map, localPlayer, round, me);
    drawStamina();
    setText(els.objective, objectiveFor(round, me));
    drawOverlay(round, me);
}
