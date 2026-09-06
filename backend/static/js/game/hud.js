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

import { SEEKER_CAMP_SECONDS } from "./config.js";
import { hideSpotAt } from "./map_loader.js";
import { relocationNote } from "./relocation.js";
import { getRound, playerNamed, roundSecondsLeft, secondsLeft } from "./round.js";
import { compassWord, latestShout } from "./shouts.js";
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
    shout: document.getElementById("shoutNote"),
    nudge: document.getElementById("nudgeNote"),

    roleCard: document.getElementById("roleCard"),
    roleCardTitle: document.getElementById("roleCardTitle"),
    roleCardBlurb: document.getElementById("roleCardBlurb"),
    hidingNote: document.getElementById("hidingNote"),
    stamina: document.getElementById("stamina"),
    staminaFill: document.getElementById("staminaFill"),

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
            tagger: "Search the house. Touch a hider to freeze them — "
                    + "but you cannot set foot on the base.",
            frozen: "Frozen. Sit tight — a free hider runs into you to "
                    + "get you up again.",
            safe: "Safe — while you are stood on it. Step off and you "
                  + "are fair game again.",
            hider: "Get back to the base — or run into a frozen friend "
                   + "to free them.",
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
            frozen: "Caught. Nobody can free you in this one — sit it out.",
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

/* ===== Which side you are on =====
 *
 * The objective line above says what to *do* this second. This says what
 * you *are* for the whole round, and it is a separate thing because
 * people were reading "Run! Get well clear of the base" without ever
 * working out that everybody else was hiding too, or that the person
 * counting was going to come looking for them specifically.
 *
 * Shown big while the round is gathering and counting, which is the one
 * stretch where there is nothing else to read. Same shape as OBJECTIVES:
 * a mode writes down only the lines it changes, and test_modes.py checks
 * neither table has grown a mode the other has never heard of.
 */

const ROLES = {
    classic: {
        tagger: {
            title: "You are the SEEKER",
            blurb: "Everybody else is hiding. Count, then find them and "
                   + "touch them — a tagged player freezes where they stand. "
                   + "You cannot stand on the base.",
        },
        hider: {
            title: "You are HIDING",
            blurb: "One player is looking for all of you. Tuck into "
                   + "furniture to vanish, free frozen friends by running "
                   + "into them, and win by getting everybody onto the base "
                   + "at once.",
        },
    },

    infection: {
        tagger: {
            title: "You are the SEEKER",
            blurb: "Everybody you touch joins your side, so the house fills "
                   + "up with seekers. Nobody freezes; they change teams.",
        },
        hider: {
            title: "You are HIDING",
            blurb: "Get tagged and you become a seeker hunting the people "
                   + "you were hiding with. Get to the base instead.",
        },
    },

    juggernaut: {
        tagger: {
            title: "You are the SEEKER",
            blurb: "No furniture hides anybody and nobody gets thawed. It is "
                   + "a chase, and the clock is short.",
        },
        hider: {
            title: "You are RUNNING",
            blurb: "Nowhere to hide in this one — the wardrobe will not save "
                   + "you. Straight for the base, and a tag is final.",
        },
    },

    blackout: {
        tagger: {
            title: "You are the SEEKER",
            blurb: "The lights are out. You carry a torch that points where "
                   + "you last moved: it reaches further than anyone can see, "
                   + "and it can be walked around behind.",
        },
        hider: {
            title: "You are HIDING",
            blurb: "It is pitch dark and you can see about a room's worth. "
                   + "The seeker has a torch — stay out of the beam, and get "
                   + "everybody home.",
        },
    },

    // Backwards: the lone player is the one hiding, and everybody else is
    // a "tagger" as far as the round is concerned.
    sardines: {
        tagger: {
            title: "You are LOOKING",
            blurb: "One person is hiding and the whole room is after them. "
                   + "Find them and you squeeze in beside them. Last one "
                   + "still looking loses.",
        },
        hider: {
            title: "You are the ONE HIDING",
            blurb: "Everybody else is counting, and then all of them come "
                   + "looking for you. Find somewhere good — they pile in "
                   + "beside you as they work it out.",
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

function roleFor(mode, role) {
    const key = role === "tagger" ? "tagger" : "hider";
    return ROLES[mode]?.[key] ?? ROLES.classic[key];
}

/*
 * The big "here is what you are" card, up while the room gathers and the
 * count runs. It goes away when the hunt starts: by then the objective
 * line is saying something more useful, and a paragraph of text is the
 * last thing you want over a house you are trying to run through.
 */
function drawRoleCard(round, me) {
    const showing = (round.phase === "gathering" || round.phase === "counting")
        && Boolean(me?.role);

    setHidden(els.roleCard, !showing);
    if (!showing) return;

    const role = roleFor(round.mode, me.role);
    setText(els.roleCardTitle, role.title);
    setText(els.roleCardBlurb, role.blurb);
    setClass(els.roleCard, "is-seeker", me.role === "tagger");
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

    // The card explaining the role is only up during the count, so the
    // chip carries the same words for the rest of the round.
    if (role && shown.roleTitle !== role) {
        shown.roleTitle = role;
        const explains = roleFor(round.mode, role);
        els.role.title = `${explains.title}. ${explains.blurb}`;
    }

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
 * What you just heard, in words. The arrow on the canvas says which way;
 * this says who and how far, because "Bob — close, north-west" is a
 * thing you can act on and a chevron on its own is not.
 */
function drawShout() {
    const shout = latestShout(performance.now());

    setHidden(els.shout, !shout);
    if (!shout) return;

    const how = shout.nearness === "close" ? "close by"
        : shout.nearness === "nearby" ? "not far"
        : "a long way off";

    setText(els.shout,
            `\uD83D\uDD0A ${shout.name} — ${how}, to the ${compassWord(shout.bearing)}`);
    setClass(els.shout, "is-close", shout.nearness === "close");
}

/* When the local seeker walked into the base's room, so the warning can
 * count down. The server keeps the real clock and will move them whether
 * this agrees or not; this only has to stop the eviction arriving out of
 * a clear blue sky. */
let campingSince = null;

/*
 * "Move on" — the seeker's clock in the room the base is in.
 *
 * They cannot stand on the base, but standing beside it is nearly as
 * good, so the room is on a timer. Counting it down in front of them
 * turns a teleport into a rule they can see coming, and gives them the
 * few seconds they are actually entitled to.
 */
function drawCampClock(map, localPlayer, round, me) {
    const watched = round.phase === "hunting"
        && me?.role === "tagger"
        && round.rules.homeIsSafety
        && Boolean(map.baseRoom);

    const room = map.baseRoom;
    const inside = watched
        && localPlayer.x + localPlayer.size / 2 >= room.x
        && localPlayer.x + localPlayer.size / 2 <= room.x + room.w
        && localPlayer.y + localPlayer.size / 2 >= room.y
        && localPlayer.y + localPlayer.size / 2 <= room.y + room.h;

    if (!inside) {
        campingSince = null;
        return false;
    }

    const now = performance.now();
    if (campingSince === null) campingSince = now;

    const left = Math.max(
        0, Math.ceil(SEEKER_CAMP_SECONDS - (now - campingSince) / 1000));

    setText(els.nudge, `No camping — move on in ${left}`);
    setClass(els.nudge, "is-urgent", left <= 2);
    return true;
}

/*
 * One line for both of the things that shove you about: the countdown
 * warning you are about to be moved, and the explanation once you have
 * been. They share an element because they are the same conversation,
 * and because they can never both be true — being moved puts you
 * somewhere the countdown does not run.
 */
function drawNudge(map, localPlayer, round, me) {
    const moved = relocationNote(performance.now());
    if (moved) {
        campingSince = null;
        setText(els.nudge, moved);
        setClass(els.nudge, "is-urgent", true);
        setHidden(els.nudge, false);
        return;
    }

    setHidden(els.nudge, !drawCampClock(map, localPlayer, round, me));
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
}


function drawOverlay(round, me) {
    const over = round.phase === "over";
    setHidden(els.overlay, !over);

    // Pressing "play again" disables the button so it cannot be sent
    // twice. A round that has been played since then is a new card, so
    // give it back rather than leaving a dead button on the screen.
    if (shown.overlayOpen !== over) {
        shown.overlayOpen = over;
        if (over) {
            els.againButton.disabled = false;
            setText(els.overlayProblem, "");
        }
    }

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

    // The round is over, so anybody may deal again — waiting on a host
    // who has put their phone down is not part of the game.
    setHidden(els.againButton, false);
    setText(els.overlayHint, me?.isHost
        ? "" : "Anyone can start the next one — the seeker rotates.");
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
    drawRoleCard(round, me);
    drawHidingNote(map, localPlayer, round, me);
    drawShout();
    drawNudge(map, localPlayer, round, me);
    drawStamina();
    setText(els.objective, objectiveFor(round, me));
    drawOverlay(round, me);
}
