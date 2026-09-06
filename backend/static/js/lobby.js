/*
 * The lobby (/room_page): player list, emoji picker, chat, and the host's
 * Start Game button.
 *
 * The server pushes room_updated whenever anything changes, so this is
 * event-driven rather than polling. The slow poll left in place is only a
 * safety net for a missed push.
 */

import {
    changeBots,
    changeEmoji,
    fetchRoom,
    kickPlayer,
    sendChat,
    setMode,
    setVolunteer,
} from "./api.js";
import { goHome, requireSession } from "./session.js";

/* Emoji a player can choose from. Must stay in step with EMOJI_POOL in
 * the server's config.py, which is what actually validates a pick. */
const EMOJIS = [
    "😀", "😃", "😄", "😁", "😆", "😊", "🙂", "🥲", "😢", "😎",
    "🤠", "🥳", "😺", "🐸", "🌺", "🐀", "🤓", "🐥", "🐓",
];

const POLL_INTERVAL_MS = 15000;
const COPIED_FEEDBACK_MS = 1200;

let session;
let socket;

/* The last room we rendered, so the emoji picker knows what is taken. */
let currentRoom = null;

/* Whether we are the host, which decides both the Start button and
 * whether the mode picker does anything. */
let amHost = false;

const els = {
    roomCode: document.getElementById("roomCodeDisplay"),
    playerList: document.getElementById("playerList"),
    playerCount: document.getElementById("playerCount"),
    startButton: document.getElementById("startButton"),
    waitingNote: document.getElementById("waitingNote"),
    emojiPicker: document.getElementById("emojiPicker"),
    modePicker: document.getElementById("modePicker"),
    modeNote: document.getElementById("modeNote"),
    volunteerButton: document.getElementById("volunteerButton"),
    volunteerNote: document.getElementById("volunteerNote"),
    botCard: document.getElementById("botCard"),
    botCount: document.getElementById("botCount"),
    addBotButton: document.getElementById("addBotButton"),
    removeBotButton: document.getElementById("removeBotButton"),
    message: document.getElementById("messageBox"),
    chatToggle: document.getElementById("chatToggle"),
    chatPanel: document.getElementById("chatPanel"),
    chatBox: document.getElementById("chatBox"),
    chatForm: document.getElementById("chatForm"),
    chatInput: document.getElementById("chatInput"),
    homeButton: document.getElementById("homeButton"),
};

/* =========================
 * Rendering
 * ========================= */

function playerRow(player) {
    const row = document.createElement("li");
    row.className = "player";

    const emoji = document.createElement("span");
    emoji.className = "player__emoji";
    emoji.textContent = player.emoji;

    const name = document.createElement("span");
    name.className = "player__name";
    name.textContent = player.name;

    row.append(emoji, name);

    if (player.bot) {
        const badge = document.createElement("span");
        badge.className = "player__badge player__badge--bot";
        badge.textContent = "Bot";
        row.appendChild(badge);
    }

    // Who has offered to be the seeker, so the room can see the draw it
    // is about to make rather than being surprised by it.
    if (player.volunteer) {
        const hand = document.createElement("span");
        hand.className = "player__badge player__badge--volunteer";
        hand.textContent = "Wants it";
        row.appendChild(hand);
    }

    if (player.isHost) {
        const badge = document.createElement("span");
        badge.className = "player__badge";
        badge.textContent = "Host";
        row.appendChild(badge);
    }

    // Briefly offline or moving between pages: faded, not removed.
    if (!player.connected) {
        row.classList.add("player--away");
    }

    if (player.name === session.name) {
        // Our own row doubles as the emoji picker trigger.
        row.classList.add("player--me");
        row.addEventListener("click", toggleEmojiPicker);
    } else if (amHost) {
        // Only on other people's rows, and only for the host. The server
        // checks that too — hiding a button is not enforcing it.
        row.appendChild(removeButton(player));
    }

    return row;
}

function removeButton(player) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "player__remove";
    button.title = `Remove ${player.name}`;
    button.setAttribute("aria-label", `Remove ${player.name}`);
    button.textContent = "\u00d7";

    button.addEventListener("click", (event) => {
        // The row behind it opens the emoji picker; this is not that.
        event.stopPropagation();
        remove(player.name);
    });

    return button;
}

async function remove(name) {
    const result = await kickPlayer(session.code, session.name, name);
    els.message.textContent = result.success
        ? "" : (result.message || "Could not remove them.");
}

function renderPlayers(players) {
    const me = players.find((p) => p.name === session.name);

    // Worked out before the rows are built, since it decides whether
    // each of them gets a remove button.
    amHost = Boolean(me && me.isHost);

    const rows = document.createDocumentFragment();
    for (const player of players) {
        rows.appendChild(playerRow(player));
    }

    els.playerList.replaceChildren(rows);
    els.playerCount.textContent = players.length;

    els.startButton.hidden = !amHost;
    els.waitingNote.hidden = amHost;

    renderVolunteer(players, me);
    renderBots(players);
}

/* =========================
 * Bots
 * ========================= */

/*
 * Everybody sees how many there are, since it changes what the round is;
 * only the host gets to change it, the same way the mode works.
 */
function renderBots(players) {
    const count = players.filter((p) => p.bot).length;

    els.botCount.textContent = count;
    els.addBotButton.hidden = !amHost;
    els.removeBotButton.hidden = !amHost;
    els.removeBotButton.disabled = count === 0;
}

async function changeBotCount(action) {
    const result = await changeBots(session.code, session.name, action);
    els.message.textContent = result.success
        ? "" : (result.message || "Could not do that.");
}

/* =========================
 * Volunteering
 * ========================= */

/*
 * Being the seeker used to be something that happened to you. Now you
 * can ask for it: if anybody has, the round draws from them, and if
 * nobody has it is an even draw among everybody who did not do it last
 * time.
 */
function renderVolunteer(players, me) {
    const wanted = Boolean(me && me.volunteer);
    const others = players.filter((p) => p.volunteer && p.name !== session.name);

    els.volunteerButton.classList.toggle("is-on", wanted);
    els.volunteerButton.setAttribute("aria-pressed", String(wanted));
    els.volunteerButton.textContent = wanted
        ? "You are up for being the seeker"
        : "I'll be the seeker";

    els.volunteerNote.textContent = describeDraw(wanted, others);
}

function describeDraw(wanted, others) {
    if (!wanted && others.length === 0) {
        return "Nobody has asked, so it is an even draw between everybody.";
    }

    if (wanted && others.length === 0) {
        return "You are the only one asking, so it is you.";
    }

    const count = others.length + (wanted ? 1 : 0);
    const who = others.map((p) => p.name).join(", ");

    return wanted
        ? `Drawn between the ${count} of you: you and ${who}.`
        : `${who} asked for it, so the draw is between them.`;
}

async function toggleVolunteer() {
    const wanted = !els.volunteerButton.classList.contains("is-on");

    const result = await setVolunteer(session.code, session.name, wanted);
    if (!result.success) {
        els.message.textContent = result.message || "Could not do that.";
    }
    // The server pushes room_updated to everyone, including us.
}

/* =========================
 * Mode picker
 * ========================= */

/*
 * The buttons themselves are rendered by the server, from the same list
 * the rules are read from, so this only ever marks one as chosen and
 * decides whether pressing them does anything.
 */
function renderModes(mode) {
    for (const button of els.modePicker.querySelectorAll(".mode")) {
        button.classList.toggle("is-selected", button.dataset.mode === mode);
        button.classList.toggle("is-locked", !amHost);
        button.disabled = !amHost;
    }

    // Everybody else is told why the list does not respond, rather than
    // being left to press it and wonder.
    els.modeNote.hidden = amHost;
}

async function pickMode(mode) {
    if (!amHost) return;

    const result = await setMode(session.code, session.name, mode);
    if (!result.success) {
        els.message.textContent = result.message || "Could not change the mode.";
        return;
    }

    els.message.textContent = "";
    // The server pushes room_updated to everyone, including us.
}

function renderChat(messages) {
    if (messages.length === 0) {
        const empty = document.createElement("p");
        empty.className = "chat__empty";
        empty.textContent = "No messages yet.";
        els.chatBox.replaceChildren(empty);
        return;
    }

    const lines = document.createDocumentFragment();
    for (const message of messages) {
        const line = document.createElement("div");
        line.className = "chat__msg";
        if (message.name === session.name) {
            line.classList.add("chat__msg--mine");
        }

        const author = document.createElement("span");
        author.className = "chat__author";
        author.textContent = `${message.name} `;

        // textContent throughout, so a message can never inject markup.
        line.append(author, document.createTextNode(message.message));
        lines.appendChild(line);
    }

    els.chatBox.replaceChildren(lines);
    els.chatBox.scrollTop = els.chatBox.scrollHeight;
}

function renderRoom(room) {
    if (!room) return;

    currentRoom = room;
    renderPlayers(room.players);
    // After renderPlayers, which is what works out whether we are the host.
    renderModes(room.mode);
    renderChat(room.chat);

    // Keep an open picker in step with who has taken what.
    if (!els.emojiPicker.hidden) {
        renderEmojiPicker();
    }
}

async function refresh() {
    renderRoom(await fetchRoom(session.code));
}

/* =========================
 * Emoji picker
 * ========================= */

function renderEmojiPicker() {
    const players = currentRoom ? currentRoom.players : [];
    const mine = players.find((p) => p.name === session.name)?.emoji;
    const taken = new Set(players.map((p) => p.emoji));

    const options = document.createDocumentFragment();

    for (const emoji of EMOJIS) {
        const option = document.createElement("button");
        option.type = "button";
        option.className = "emoji-option";
        option.textContent = emoji;

        if (emoji === mine) {
            option.classList.add("emoji-option--mine");
            option.disabled = true;
        } else if (taken.has(emoji)) {
            // Show it greyed rather than hiding it, so the grid does not
            // reshuffle every time somebody picks something.
            option.classList.add("emoji-option--taken");
            option.disabled = true;
        } else {
            option.addEventListener("click", () => pickEmoji(emoji));
        }

        options.appendChild(option);
    }

    els.emojiPicker.replaceChildren(options);
}

function toggleEmojiPicker() {
    els.emojiPicker.hidden = !els.emojiPicker.hidden;
    if (!els.emojiPicker.hidden) {
        renderEmojiPicker();
    }
}

async function pickEmoji(emoji) {
    const result = await changeEmoji(session.code, session.name, emoji);

    if (!result.success) {
        els.message.textContent = result.message || "Already taken!";
        return;
    }

    els.message.textContent = "";
    els.emojiPicker.hidden = true;
    // The server pushes room_updated to everyone, including us.
}

/* =========================
 * Room code
 * ========================= */

async function copyRoomCode() {
    try {
        await navigator.clipboard.writeText(session.code);
    } catch {
        // Clipboard needs a secure context, which plain http:// on a LAN
        // is not. The code is on screen anyway, so this is not worth an
        // error message.
        return;
    }

    els.roomCode.textContent = "Copied";
    els.roomCode.classList.add("is-copied");

    setTimeout(() => {
        els.roomCode.textContent = session.code;
        els.roomCode.classList.remove("is-copied");
    }, COPIED_FEEDBACK_MS);
}

/* =========================
 * Chat
 * ========================= */

async function onSendChat(event) {
    event.preventDefault();

    const message = els.chatInput.value.trim();
    if (!message) return;

    els.chatInput.value = "";
    await sendChat(session.code, session.name, message);
}

function toggleChat() {
    const collapsed = els.chatPanel.classList.toggle("is-collapsed");
    els.chatToggle.setAttribute("aria-expanded", String(!collapsed));
}

/* =========================
 * Startup
 * ========================= */

function start() {
    els.roomCode.textContent = session.code;

    els.homeButton.addEventListener("click", goHome);
    els.roomCode.addEventListener("click", copyRoomCode);
    els.chatForm.addEventListener("submit", onSendChat);
    els.chatToggle.addEventListener("click", toggleChat);

    for (const button of els.modePicker.querySelectorAll(".mode")) {
        button.addEventListener("click", () => pickMode(button.dataset.mode));
    }
    els.volunteerButton.addEventListener("click", toggleVolunteer);
    els.addBotButton.addEventListener("click", () => changeBotCount("add"));
    els.removeBotButton.addEventListener("click", () => changeBotCount("remove"));
    els.startButton.addEventListener("click", () => {
        els.startButton.disabled = true;
        socket.emit("start_game_request", { code: session.code });
    });

    // The host pressed start: everyone in the room follows.
    socket.on("trigger_start_game", () => {
        window.location.href = "/game_page";
    });

    // The server would not start the round — too few players, most
    // likely. Say why and let them try again.
    socket.on("start_rejected", (data) => {
        els.message.textContent = data.message || "Could not start a round.";
        els.startButton.disabled = false;
    });

    // Anything that changes the room — a join, an emoji, a message, someone
    // leaving — arrives here, so the list stays live without polling for it.
    socket.on("room_updated", renderRoom);

    // The host removed us. Say so and go home, rather than sitting on a
    // room we are no longer part of.
    socket.on("kicked", () => {
        els.message.textContent = "The host removed you from the room.";
        setTimeout(goHome, 1800);
    });

    // The room expired while we were away, so there is nothing to show.
    socket.on("join_rejected", (data) => {
        els.message.textContent = data.message || "That room has closed.";
        setTimeout(goHome, 1500);
    });

    // Re-announce ourselves after a dropped connection, otherwise we stop
    // receiving the room's broadcasts.
    socket.on("connect", () => {
        socket.emit("join_lobby", { code: session.code, name: session.name });
    });

    refresh();
    setInterval(refresh, POLL_INTERVAL_MS);
}

// requireSession sends us home when there is nothing stored, in which case
// there is no point setting any of this up.
session = requireSession();
if (session) {
    socket = io();
    start();
}
