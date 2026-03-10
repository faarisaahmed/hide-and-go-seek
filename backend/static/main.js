// 1. Define constants FIRST
const backend = "http://192.168.4.43:5000";
const EMOJIS = ["😀","😃","😄","😁","😆","😊","🙂","🥲","😢","😎","🤠","🥳","😺","🐸", "🌺", "🐀", "🤓", "🐥", "🐓", "🐦‍🔥"];

// 2. Initialize socket after constants
const socket = io(backend);

// 3. Socket Listeners
socket.on("trigger_start_game", () => {
    sessionStorage.setItem("gameStarted", "true");
    window.location.href = "/game_page";
});

// =========================
// Navigation
// =========================

function goHome() {
    sessionStorage.removeItem("roomCode");
    sessionStorage.removeItem("playerName");
    window.location.href = "/";
}

// =========================
// Username Validation
// =========================

function getDisplayName() {
    let name = document.getElementById("displayName")?.value;
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

    try {
        let res = await fetch(backend + "/create_room", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: name })
        });

        let data = await res.json();
        
        if (data.success) {
            // 1. Clear ALL old session data to prevent "old name" bugs
            sessionStorage.clear();
            
            // 2. Also clear localStorage just in case an old script used it
            localStorage.clear();

            // 3. Save the FRESH credentials
            sessionStorage.setItem("roomCode", data.room_code);
            sessionStorage.setItem("playerName", name);

            // 4. Redirect
            window.location.href = "/room_page";
        } else {
            alert("Room creation failed");
        }
    } catch (error) {
        console.error("Error creating room:", error);
        alert("Could not connect to server.");
    }
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name, code: code })
    });

    let data = await res.json();
    if (!data.success) {
        alert("Room not found or name already taken");
        return;
    }

    sessionStorage.setItem("roomCode", code);
    sessionStorage.setItem("playerName", name);
    window.location.href = "/room_page";
}

// =========================
// Lobby Display
// =========================

async function refreshRoom() {
    let code = sessionStorage.getItem("roomCode");
    let name = sessionStorage.getItem("playerName");
    if (!code) return;

    let title = document.getElementById("roomCodeDisplay");
    if (title) {
        title.innerText = "Room Code: " + code + " | Player: " + name;
    }

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
    let amIHost = false;
    const myName = sessionStorage.getItem("playerName");

    players.forEach(p => {
        let li = document.createElement("li");
        li.innerText = p.emoji + " " + p.name + (p.isHost ? " 👑" : "");

        if (p.name === myName) {
            li.style.cursor = "pointer";
            li.style.fontWeight = "bold";
            li.style.textDecoration = "underline";
            
            // Re-attach the emoji picker click
            li.onclick = function() {
                showEmojiPicker();
            };

            if (p.isHost) amIHost = true;
        }
        list.appendChild(li);
    });

    let startBtn = document.getElementById("startButton") || document.querySelector("button[onclick='startGame()']");
    if (startBtn) {
        startBtn.style.display = amIHost ? "block" : "none";
    }
}

// =========================
// Page Load Handler
// =========================

window.onload = function() {
    let path = window.location.pathname;

    if (path.includes("room_page")) {
        let roomCode = sessionStorage.getItem("roomCode");
        let playerName = sessionStorage.getItem("playerName");

        if (!roomCode || !playerName) {
            window.location.href = "/";
            return;
        }

        socket.emit("join_game", { code: roomCode, name: playerName });

        refreshRoom();
        setInterval(refreshChat, 2000);
        setInterval(refreshRoom, 3000);
    }
}

// =========================
// Emoji System
// =========================

function showEmojiPicker() {
    let box = document.getElementById("emojiPicker");
    if (!box) return;

    box.style.display = "flex";
    box.style.flexWrap = "wrap";
    box.innerHTML = "";

    EMOJIS.forEach(e => {
        let div = document.createElement("div");
        div.className = "emoji-option";
        div.innerText = e;
        div.style.cursor = "pointer";
        div.style.padding = "5px";
        div.style.fontSize = "24px";

        div.onclick = () => changeEmoji(e);
        box.appendChild(div);
    });
}

async function changeEmoji(emoji) {
    let code = sessionStorage.getItem("roomCode");
    let name = sessionStorage.getItem("playerName");

    let res = await fetch(backend + "/change_emoji", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            code: code,
            name: name,
            emoji: emoji
        })
    });

    let data = await res.json();
    let msgBox = document.getElementById("messageBox");

    if (!data.success) {
        if (msgBox) msgBox.innerText = data.message || "Already taken!";
        return;
    }

    if (msgBox) msgBox.innerText = "";
    document.getElementById("emojiPicker").style.display = "none";
    refreshRoom();
}

// =========================
// Chat System
// =========================

async function refreshChat() {
    let code = sessionStorage.getItem("roomCode");
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

    let code = sessionStorage.getItem("roomCode");
    let name = sessionStorage.getItem("playerName");

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
    icon.innerText = panel.classList.contains("collapsed") ? "▲" : "▼";
}

// =========================
// Game Management
// =========================

function startGame() {
    let code = sessionStorage.getItem("roomCode");
    socket.emit("start_game_request", { code: code });
}