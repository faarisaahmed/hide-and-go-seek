/*
 * The lobby (/room_page): player list, emoji picker, chat, and the host's
 * Start Game button.
 *
 * Room state is polled over HTTP rather than pushed, which is simple and
 * good enough for a lobby. The socket is used for the two things that
 * must feel instant: the host starting the game, and emoji changes.
 */

import { changeEmoji, fetchRoom, sendChat } from "./api.js";
import { goHome, requireSession } from "./session.js";

/* Emoji a player can choose from. The server only checks that a pick is
 * not already taken, so this list can grow freely. */
const EMOJIS = [
    "😀", "😃", "😄", "😁", "😆", "😊", "🙂", "🥲", "😢", "😎",
    "🤠", "🥳", "😺", "🐸", "🌺", "🐀", "🤓", "🐥", "🐓", "🐦‍🔥",
];

const POLL_INTERVAL_MS = 2000;

let session;
let socket;

const els = {
    roomCode: document.getElementById("roomCodeDisplay"),
    playerList: document.getElementById("playerList"),
    startButton: document.getElementById("startButton"),
    emojiPicker: document.getElementById("emojiPicker"),
    message: document.getElementById("messageBox"),
    chatToggle: document.querySelector(".chat-toggle"),
    chatPanel: document.getElementById("chatPanel"),
    chatToggleIcon: document.getElementById("chatToggleIcon"),
    chatBox: document.getElementById("chatBox"),
    chatInput: document.getElementById("chatInput"),
    homeButton: document.getElementById("homeButton"),
    sendChatButton: document.getElementById("sendChatButton"),
    refreshButton: document.getElementById("refreshButton"),
};

/* =========================
 * Rendering
 * ========================= */

function renderPlayers(players) {
    els.playerList.innerHTML = "";
    let amHost = false;

    for (const player of players) {
        const item = document.createElement("li");
        item.innerText = `${player.emoji} ${player.name}${player.isHost ? " 👑" : ""}`;

        if (player.name === session.name) {
            // Our own row doubles as the emoji picker trigger.
            item.classList.add("is-me");
            item.addEventListener("click", showEmojiPicker);
            amHost = player.isHost;
        }

        els.playerList.appendChild(item);
    }

    els.startButton.style.display = amHost ? "block" : "none";
}

function renderChat(messages) {
    els.chatBox.innerHTML = "";
    for (const message of messages) {
        const line = document.createElement("div");
        line.innerText = `${message.name}: ${message.message}`;
        els.chatBox.appendChild(line);
    }
    els.chatBox.scrollTop = els.chatBox.scrollHeight;
}

function renderRoom(room) {
    if (!room) return;
    renderPlayers(room.players);
    renderChat(room.chat);
}

/* One request keeps both the player list and the chat current. */
async function refresh() {
    renderRoom(await fetchRoom(session.code));
}

/* =========================
 * Emoji picker
 * ========================= */

function showEmojiPicker() {
    els.emojiPicker.style.display = "flex";
    els.emojiPicker.innerHTML = "";

    for (const emoji of EMOJIS) {
        const option = document.createElement("div");
        option.className = "emoji-option";
        option.innerText = emoji;
        option.addEventListener("click", () => pickEmoji(emoji));
        els.emojiPicker.appendChild(option);
    }
}

async function pickEmoji(emoji) {
    const result = await changeEmoji(session.code, session.name, emoji);

    if (!result.success) {
        els.message.innerText = result.message || "Already taken!";
        return;
    }

    els.message.innerText = "";
    els.emojiPicker.style.display = "none";
    refresh();
}

/* =========================
 * Chat
 * ========================= */

async function onSendChat() {
    const message = els.chatInput.value.trim();
    if (!message) return;

    els.chatInput.value = "";
    await sendChat(session.code, session.name, message);
    refresh();
}

function toggleChat() {
    const collapsed = els.chatPanel.classList.toggle("collapsed");
    els.chatToggleIcon.innerText = collapsed ? "▲" : "▼";
}

/* =========================
 * Startup
 * ========================= */

function start() {
    els.roomCode.innerText = `Room Code: ${session.code} | Player: ${session.name}`;

    els.homeButton.addEventListener("click", goHome);
    els.refreshButton.addEventListener("click", refresh);
    els.sendChatButton.addEventListener("click", onSendChat);
    els.chatToggle.addEventListener("click", toggleChat);
    els.startButton.addEventListener("click", () => {
        socket.emit("start_game_request", { code: session.code });
    });

    // The host pressed start: everyone in the room follows.
    socket.on("trigger_start_game", () => {
        window.location.href = "/game_page";
    });

    // Someone changed their emoji; the server hands us the new player list.
    socket.on("player_updated", renderRoom);

    // Joining the socket room is what subscribes us to the broadcasts above.
    socket.emit("join_game", { code: session.code, name: session.name });

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
