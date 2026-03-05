/*
renderer.js
Handles all game drawing using HTML Canvas.
*/

const canvas = document.getElementById("gameCanvas");
const ctx = canvas.getContext("2d");

let player = {
    x: 100,
    y: 100,
    size: 20
};

/* =========================
Canvas Setup
========================= */

function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
}

window.addEventListener("resize", resizeCanvas);
resizeCanvas();

/* =========================
Draw Loop
========================= */

function renderGame() {

    playerControllerUpdate();

    if (!canvas || !ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    let map = getMap();

    if (map) {
        drawMap(map);
    }

    drawPlayer();

    requestAnimationFrame(renderGame);
}

/* =========================
Map Rendering
========================= */

function drawMap(map) {

    if (!map.walls) return;

    ctx.fillStyle = "#5c3a3aff";

    map.walls.forEach(w => {

        ctx.fillRect(
            w.x,
            w.y,
            w.w,
            w.h
        );
    });

}

/* =========================
Player Rendering
========================= */

function drawPlayer() {

    ctx.fillStyle = "#4CAF50";

    ctx.fillRect(
        player.x,
        player.y,
        player.size,
        player.size
    );
}

/* =========================
Start Renderer
========================= */

renderGame();