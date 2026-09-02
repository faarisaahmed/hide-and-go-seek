/*
 * Drawing the world onto the canvas.
 *
 * Everything is drawn in world coordinates minus the camera offset. The
 * camera is centred on the local player, so the player stays in the middle
 * of the screen and the map moves underneath.
 */

import {
    COLORS,
    CULL_MARGIN,
    EMOJI_FONT,
    NAME_TAG_FONT,
    NAME_TAG_OFFSET,
} from "./config.js";

export function createRenderer(canvas) {
    const ctx = canvas.getContext("2d");
    const camera = { x: 0, y: 0 };

    // Viewport in CSS pixels. The backing store is larger on a retina
    // screen, but everything we draw is in CSS pixels.
    let viewWidth = 0;
    let viewHeight = 0;

    /*
     * Match the canvas to the window *and* the display density. Without
     * the density step the whole game is drawn at half resolution on a
     * retina screen, which is what made it look soft.
     */
    function resize() {
        const ratio = window.devicePixelRatio || 1;

        viewWidth = window.innerWidth;
        viewHeight = window.innerHeight;

        canvas.width = Math.round(viewWidth * ratio);
        canvas.height = Math.round(viewHeight * ratio);
        canvas.style.width = `${viewWidth}px`;
        canvas.style.height = `${viewHeight}px`;

        // Draw in CSS pixels; the transform scales up to device pixels.
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    }

    window.addEventListener("resize", resize);
    resize();

    /* Is this rectangle anywhere near the screen? */
    function onScreen(rect) {
        return (
            rect.x + rect.w >= camera.x - CULL_MARGIN &&
            rect.x <= camera.x + viewWidth + CULL_MARGIN &&
            rect.y + rect.h >= camera.y - CULL_MARGIN &&
            rect.y <= camera.y + viewHeight + CULL_MARGIN
        );
    }

    /* Draw only the rectangles that can actually be seen. */
    function fillRects(rects, color) {
        ctx.fillStyle = color;
        for (const rect of rects) {
            if (!onScreen(rect)) continue;
            ctx.fillRect(rect.x - camera.x, rect.y - camera.y, rect.w, rect.h);
        }
    }

    /* One player: their square, their lobby emoji, and their name. */
    function drawPlayer(player, size, color) {
        const x = player.x - camera.x;
        const y = player.y - camera.y;

        ctx.fillStyle = color;
        ctx.fillRect(x, y, size, size);

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
        camera.x = localPlayer.x - viewWidth / 2;
        camera.y = localPlayer.y - viewHeight / 2;

        // Everything outside the map gets the void colour.
        ctx.fillStyle = COLORS.void;
        ctx.fillRect(0, 0, viewWidth, viewHeight);

        // Floor, clipped to what is on screen rather than painting the
        // whole map every frame.
        const floorX = Math.max(0, camera.x);
        const floorY = Math.max(0, camera.y);
        const floorRight = Math.min(map.width, camera.x + viewWidth);
        const floorBottom = Math.min(map.height, camera.y + viewHeight);

        if (floorRight > floorX && floorBottom > floorY) {
            ctx.fillStyle = COLORS.floor;
            ctx.fillRect(
                floorX - camera.x,
                floorY - camera.y,
                floorRight - floorX,
                floorBottom - floorY,
            );
        }

        fillRects(map.base_zones ?? [], COLORS.baseZone);
        fillRects(map.walls, COLORS.wall);

        // Text settings are the same for every player, so set them once.
        ctx.textAlign = "center";

        for (const remote of Object.values(remotePlayers)) {
            // The server sends positions only, so remotes are drawn at the
            // same size as us.
            drawPlayer(remote, localPlayer.size, COLORS.remotePlayer);
        }

        // Drawn last so we are never hidden underneath someone else.
        drawPlayer(localPlayer, localPlayer.size, COLORS.localPlayer);
    }

    return { draw };
}
