const backend = "http://192.168.1.171:5000";

const EMOJIS = ["😀","😃","😄","😁","😆","😊","🙂","🥲","😢","😎","🤠","🥳","😺","🐸", "🌺"];

// =========================
// Navigation
// =========================

function goHome() {
    localStorage.removeItem("roomCode");
    window.location.href = backend + "/";
}

// =========================
// Username Validation
// =========================

function getDisplayName() {
    let name = document.getElementById("displayName").value;

    if (!name || name.trim() === "") {
        alert("Please enter a username");
        return null;
    }

    return name.trim();
}

// =========================
// Room Creation
// =========================

async function createRoom() {
    let name = getDisplayName();
    if (!name) return;

    let res = await fetch(backend + "/create_room", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ name: name })
    });

    let data = await res.json();

    if (!data.success) {
        alert("Room creation failed");
        return;
    }

    localStorage.setItem("roomCode", data.room_code);
    localStorage.setItem("playerName", name);

    window.location.href = backend + "/room_page";
}

// =========================
// Join Room
// =========================

async function joinRoom() {
    let name = getDisplayName();
    if (!name) return;

    let code = document.getElementById("roomCodeInput").value;

    if (!/^[0-9]+$/.test(code)) {
        alert("Room code must be numbers only");
        return;
    }

    let res = await fetch(backend + "/join_room", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            name: name,
            code: code
        })
    });

    let data = await res.json();

    if (!data.success) {
        alert("Room not found");
        return;
    }

    localStorage.setItem("roomCode", code);
    localStorage.setItem("playerName", name);

    window.location.href = backend + "/room_page";
}

// =========================
// Lobby Display
// =========================

async function refreshRoom() {

    let code = localStorage.getItem("roomCode");
    let name = localStorage.getItem("playerName");

    if (!code) return;

    document.getElementById("roomCodeDisplay").innerText =
        "Room Code: " + code + " | Player: " + name;

    let res = await fetch(backend + "/room/" + code);
    let data = await res.json();

    if (data && data.players) {
        updatePlayerList(data.players);
    }
}

// =========================
// Player List Rendering
// =========================

function updatePlayerList(players) {

    let list = document.getElementById("playerList");

    if (!list) return;

    list.innerHTML = "";

    players.forEach(p => {

        let li = document.createElement("li");
        li.innerText = p.emoji + " " + p.name;

        if (p.name === localStorage.getItem("playerName")) {
            li.style.cursor = "pointer";
            li.onclick = showEmojiPicker;
        }

        list.appendChild(li);
    });
}

// =========================
// Page Load Handler
// =========================

window.onload = function() {

    let path = window.location.pathname;

    if (path.includes("room_page")) {

        let roomCode = localStorage.getItem("roomCode");
        let playerName = localStorage.getItem("playerName");

        if (!roomCode || !playerName) {
            window.location.href = backend + "/";
            return;
        }

        refreshRoom();

        setInterval(refreshChat, 1500);
        setInterval(refreshRoom, 3000);
    }
}

// =========================
// Emoji System
// =========================

function showEmojiPicker() {

    let box = document.getElementById("emojiPicker");
    if (!box) return;

    box.style.display = "block";
    box.innerHTML = "";

    EMOJIS.forEach(e => {

        let div = document.createElement("div");
        div.className = "emoji-option";
        div.innerText = e;

        div.onclick = () => changeEmoji(e);

        box.appendChild(div);
    });
}

async function changeEmoji(emoji) {

    let code = localStorage.getItem("roomCode");
    let name = localStorage.getItem("playerName");

    let res = await fetch(backend + "/change_emoji", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            code: code,
            name: name,
            emoji: emoji
        })
    });

    let data = await res.json();

    let msgBox = document.getElementById("messageBox");

    if (!data.success) {
        msgBox.innerText = data.message || "Already taken!";
        return;
    }

    msgBox.innerText = "";

    document.getElementById("emojiPicker").style.display = "none";

    refreshRoom();
}

// =========================
// Chat System
// =========================

async function refreshChat() {

    let code = localStorage.getItem("roomCode");

    if (!code) return;

    let res = await fetch(backend + "/room/" + code);
    let data = await res.json();

    if (!data || !data.chat) return;

    let box = document.getElementById("chatBox");

    if (!box) return;

    box.innerHTML = "";

    data.chat.forEach(msg => {

        let div = document.createElement("div");
        div.innerText = msg.name + ": " + msg.message;

        box.appendChild(div);
    });

    box.scrollTop = box.scrollHeight;
}

async function sendChat() {

    let input = document.getElementById("chatInput");
    if (!input) return;

    let message = input.value.trim();
    if (!message) return;

    let code = localStorage.getItem("roomCode");
    let name = localStorage.getItem("playerName");

    await fetch(backend + "/send_chat", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            code: code,
            name: name,
            message: message
        })
    });

    input.value = "";
}

function toggleChat() {

    let panel = document.getElementById("chatPanel");
    let icon = document.getElementById("chatToggleIcon");

    if (!panel || !icon) return;

    panel.classList.toggle("collapsed");

    if (panel.classList.contains("collapsed")) {
        icon.innerText = "▲";   // Upside down triangle when collapsed
    } else {
        icon.innerText = "▼";   // Down triangle when expanded
    }
}