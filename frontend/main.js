const backend = "http://localhost:5000";

// ------------------------
// Navigation
// ------------------------

function goHome() {
    localStorage.removeItem("roomCode");
    window.location.href = "index.html";
}

// ------------------------
// Username validation
// ------------------------

function getDisplayName() {
    let name = document.getElementById("displayName").value;

    if (!name || name.trim() === "") {
        alert("Please enter a username");
        return null;
    }

    return name.trim();
}

// ------------------------
// Room Creation
// ------------------------

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

    localStorage.setItem("roomCode", data.room_code);
    localStorage.setItem("playerName", name);

    window.location.href = "room.html";
}

// ------------------------
// Join Room
// ------------------------

async function joinRoom() {
    let name = getDisplayName();
    if (!name) return;

    let code = document.getElementById("roomCodeInput").value;

    // Number-only code rule
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

    window.location.href = "room.html";
}

// ------------------------
// Room Display
// ------------------------

async function refreshRoom() {
    let code = localStorage.getItem("roomCode");

    if (!code) return;

    document.getElementById("roomCodeDisplay").innerText =
        "Room Code: " + code;

    let res = await fetch(backend + "/room/" + code);
    let data = await res.json();

    if (data && data.players) {
        updatePlayerList(data.players);
    }
}

// ------------------------

function updatePlayerList(players) {
    let list = document.getElementById("playerList");
    list.innerHTML = "";

    players.forEach(p => {
        let li = document.createElement("li");
        li.innerText = p;
        list.appendChild(li);
    });
}

// ------------------------
// Auto run on room page
// ------------------------

window.onload = function() {

    let path = window.location.pathname;

    // If user is trying to open room page
    if (path.includes("room.html")) {

        let roomCode = localStorage.getItem("roomCode");
        let playerName = localStorage.getItem("playerName");

        // If no room or username → force home
        if (!roomCode || !playerName) {
            window.location.href = "index.html";
            return;
        }

        refreshRoom();
    }
}