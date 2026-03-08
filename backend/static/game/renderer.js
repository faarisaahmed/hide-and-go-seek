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

    /* =========================
    Draw Other Players
    ========================= */

    if (typeof otherPlayers !== 'undefined') {
        for (const id in otherPlayers) {
            let p = otherPlayers[id];

            ctx.fillStyle = "#66b3ff"; // light blue

            ctx.fillRect(
                p.x - camera.x,
                p.y - camera.y,
                player.size,
                player.size
            );
        }
    }
}

/* =========================
Start Renderer
========================= */

gameLoop();