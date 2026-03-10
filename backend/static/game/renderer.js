/*
renderer.js
Handles rendering and camera movement.
*/

const canvas = document.getElementById("gameCanvas");
const ctx = canvas.getContext("2d");

let map = null;

/* =========================
Canvas Resize
========================= */

function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
}

window.addEventListener("resize", resizeCanvas);
resizeCanvas();

/* =========================
Camera
========================= */

let camera = {
    x: 0,
    y: 0
};

/* =========================
Main Render Loop
========================= */

function gameLoop() {

    requestAnimationFrame(gameLoop);

    map = getMap();
    if (!map) return;

    /* Update player movement */
    if (typeof window.playerControllerUpdate === "function") {
        window.playerControllerUpdate();
    }

    /* Center camera on player */
    camera.x = player.x - canvas.width / 2;
    camera.y = player.y - canvas.height / 2;

    /* Clear screen */
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    /* Draw map background */
    ctx.fillStyle = "#eeeeee";
    ctx.fillRect(-camera.x, -camera.y, map.width, map.height);

    /* =========================
       Draw Walls
    ========================= */

    ctx.fillStyle = "#634646ff";

    for (let wall of map.walls) {
        ctx.fillRect(
            wall.x - camera.x,
            wall.y - camera.y,
            wall.w,
            wall.h
        );
    }

    /* =========================
       Draw Base Zones
    ========================= */

    if (map.base_zones) {
        ctx.fillStyle = "#7fbd64ff";
        for (let zone of map.base_zones) {
            ctx.fillRect(
                zone.x - camera.x,
                zone.y - camera.y,
                zone.w,
                zone.h
            );
        }
    }

    /* =========================
    Draw Player (Local)
    ========================= */

    ctx.fillStyle = "#2abb67ff";
    ctx.fillRect(
        player.x - camera.x,
        player.y - camera.y,
        player.size,
        player.size
    );

    // --- Draw local name ---
    ctx.fillStyle = "#000000";
    ctx.font = "bold 14px Arial";
    ctx.textAlign = "center";

    // Use the name stored in the window.playerName variable (we will set this next)
    const myDisplayName = window.currentName || "You"; 

    ctx.fillText(
        myDisplayName, 
        player.x - camera.x + (player.size / 2), 
        player.y - camera.y + player.size + 15 
    );

    /* =========================
    Draw Other Players
    ========================= */

    if (typeof otherPlayers !== 'undefined') {
        for (const id in otherPlayers) {
            // Skip drawing yourself to avoid the "ghost" overlap
            if (id === window.socket.id) continue;

            let p = otherPlayers[id];

            // --- REMOVED SMOOTHING ---
            // We no longer use p.x += (target - p.x) * 0.1
            // We set the position directly to the target for 1:1 precision.
            p.x = p.targetX !== undefined ? p.targetX : p.x;
            p.y = p.targetY !== undefined ? p.targetY : p.y;

            // Draw Player Square
            ctx.fillStyle = "#66b3ff"; // Light blue for others
            ctx.fillRect(
                p.x - camera.x,
                p.y - camera.y,
                player.size,
                player.size
            );

            // Draw Name Tag
            ctx.fillStyle = "#000000";
            ctx.font = "bold 14px Arial";
            ctx.textAlign = "center";
            ctx.fillText(
                p.name, 
                p.x - camera.x + (player.size / 2), 
                p.y - camera.y + player.size + 15
            );
        }
    }
}

/* =========================
Start Renderer
========================= */

gameLoop();