/*
 * Drawing the world onto the canvas.
 *
 * Everything is drawn in world coordinates minus the camera offset. The
 * camera is centred on the local player, so the player stays in the middle
 * of the screen and the map moves underneath.
 */

import { COLORS, NAME_TAG_FONT, NAME_TAG_OFFSET } from "./config.js";

export function createRenderer(canvas) {
    const ctx = canvas.getContext("2d");
    const camera = { x: 0, y: 0 };

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    window.addEventListener("resize", resize);
    resize();

    function fillRects(rects, color) {
        ctx.fillStyle = color;
        for (const rect of rects) {
            ctx.fillRect(rect.x - camera.x, rect.y - camera.y, rect.w, rect.h);
        }
    }

    function drawPlayer(player, name, color) {
        ctx.fillStyle = color;
        ctx.fillRect(
            player.x - camera.x,
            player.y - camera.y,
            player.size,
            player.size,
        );

        ctx.fillStyle = COLORS.nameTag;
        ctx.font = NAME_TAG_FONT;
        ctx.textAlign = "center";
        ctx.fillText(
            name,
            player.x - camera.x + player.size / 2,
            player.y - camera.y + player.size + NAME_TAG_OFFSET,
        );
    }

    function draw({ map, localPlayer, localName, remotePlayers }) {
        camera.x = localPlayer.x - canvas.width / 2;
        camera.y = localPlayer.y - canvas.height / 2;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Floor, then walls and base zones on top of it.
        ctx.fillStyle = COLORS.floor;
        ctx.fillRect(-camera.x, -camera.y, map.width, map.height);

        fillRects(map.walls, COLORS.wall);
        fillRects(map.base_zones ?? [], COLORS.baseZone);

        drawPlayer(localPlayer, localName, COLORS.localPlayer);

        for (const remote of Object.values(remotePlayers)) {
            // Remote players are drawn at the local player's size; the
            // server only sends positions.
            const box = { x: remote.x, y: remote.y, size: localPlayer.size };
            drawPlayer(box, remote.name, COLORS.remotePlayer);
        }
    }

    return { draw };
}
