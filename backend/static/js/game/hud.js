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

/* ===== What to tell the player to do ===== */

function objectiveFor(round, me) {
    const role = me?.role;
    const state = me?.state;

    switch (round.phase) {
        case "lobby":
            return "No round yet — the host starts it from the lobby.";
        case "gathering":
            return "Everyone to the base. Hold still…";
        case "counting":
            return role === "tagger"
                ? "Eyes shut. Count it out."
                : "Run! Get well clear of the base, then hide.";
        case "hunting":
            if (role === "tagger") return "Search the house. Touch a hider to freeze them.";
            if (state === "frozen") return "Frozen. Sit tight — a free hider can thaw you.";
            if (state === "safe") return "You made it home. Now the rest have to.";
            return "Get back to the base — or go and thaw a frozen friend.";
        default:
            return "";
    }
}

function outcomeTitle(round) {
    if (round.winner === "hiders") return "Hiders win";
    if (round.winner === "tagger") return `${round.tagger || "The seeker"} wins`;
    return "Round over";
}

function outcomeNote(round) {
    if (round.note) return round.note;
    if (round.winner === "hiders") return "Everybody made it home.";
    if (round.winner === "tagger") return "Nobody left to find.";
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

    const { hiders, frozen, safe } = round.tally;
    const seeking = round.tagger ? `${round.tagger} seeking` : "no seeker";
    setText(els.tally, `${seeking} · ${safe}/${hiders} home · ${frozen} frozen`);
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
    drawClock(round);
    drawCountdown(round, me);
    drawHidingNote(map, localPlayer, round, me);
    drawStamina();
    setText(els.objective, objectiveFor(round, me));
    drawOverlay(round, me);
}
