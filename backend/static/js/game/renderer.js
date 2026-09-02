/*
 * Drawing the world onto the canvas.
 *
 * Everything is drawn in world coordinates minus the camera offset. The
 * camera is centred on the local player, so the player stays in the middle
 * of the screen and the map moves underneath.
 */

import { COLORS, EMOJI_FONT, NAME_TAG_FONT, NAME_TAG_OFFSET } from "./config.js";

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

    /* One player: their square, their lobby emoji, and their name. */
    function drawPlayer(player, size, color) {
        const x = player.x - camera.x;
        const y = player.y - camera.y;

        ctx.fillStyle = color;
        ctx.fillRect(x, y, size, size);

        ctx.textAlign = "center";

        if (player.emoji) {
            ctx.font = EMOJI_FONT;
            ctx.textBaseline = "middle";
            ctx.fillText(player.emoji, x + size / 2, y + size / 2);
            ctx.textBaseline = "alphabetic";
        }

        ctx.fillStyle = COLORS.nameTag;
        ctx.font = NAME_TAG_FONT;
        ctx.fillText(player.name, x + size / 2, y + size + NAME_TAG_OFFSET);
    }

    function draw({ map, localPlayer, remotePlayers }) {
        camera.x = localPlayer.x - canvas.width / 2;
        camera.y = localPlayer.y - canvas.height / 2;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Floor, then walls and base zones on top of it.
        ctx.fillStyle = COLORS.floor;
        ctx.fillRect(-camera.x, -camera.y, map.width, map.height);

        fillRects(map.walls, COLORS.wall);
        fillRects(map.base_zones ?? [], COLORS.baseZone);

        drawPlayer(localPlayer, localPlayer.size, COLORS.localPlayer);

        for (const remote of Object.values(remotePlayers)) {
            // The server sends positions only, so remotes are drawn at the
            // same size as us.
            drawPlayer(remote, localPlayer.size, COLORS.remotePlayer);
        }
    }

    return { draw };
}
