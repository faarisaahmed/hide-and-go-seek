/*
 * The minimap: the shape of the house, the base, and you.
 *
 * Deliberately not everybody. A map with the other players on it would
 * answer the only question the game is asking — a seeker would walk
 * straight to each dot in turn and a hider would never have to guess
 * where the seeker was. What people actually get lost about is the
 * *house*: which way the hall runs, where the base is from here, whether
 * the door they want is behind them. That is geography, and geography is
 * the same for everybody, so it costs nothing to hand over.
 *
 * The house never moves, so it is drawn once into an offscreen canvas
 * and blitted each frame with a single marker on top. That is the whole
 * reason this can run at sixty frames a second next to the main view.
 */

import { MINIMAP_HEIGHT, MINIMAP_WIDTH, COLORS } from "./config.js";

/* Colours of their own rather than the world's: at this size the night
 * blues all collapse into one another, so the map is drawn as a plan. */
const INK = {
    backdrop: "rgba(4, 9, 21, 0.55)",
    room: "rgba(120, 160, 220, 0.20)",
    wall: "rgba(150, 186, 236, 0.62)",
    door: "rgba(47, 212, 192, 0.45)",
};

export function createMinimap(canvas) {
    const ctx = canvas.getContext("2d");

    /* The house, pre-drawn. Rebuilt only when the map changes, or when
     * the mode stops having a base to mark on it. */
    const plan = { canvas: document.createElement("canvas"), of: null,
                   withBase: null };

    let scale = 1;
    let offsetX = 0;
    let offsetY = 0;

    function fit(map) {
        // Letterboxed rather than stretched: a squashed plan is worse
        // than useless, because it lies about which way is further.
        scale = Math.min(MINIMAP_WIDTH / map.width, MINIMAP_HEIGHT / map.height);
        offsetX = (MINIMAP_WIDTH - map.width * scale) / 2;
        offsetY = (MINIMAP_HEIGHT - map.height * scale) / 2;
    }

    function mapX(worldX) {
        return offsetX + worldX * scale;
    }

    function mapY(worldY) {
        return offsetY + worldY * scale;
    }

    function buildPlan(map, hasBase) {
        plan.canvas.width = MINIMAP_WIDTH;
        plan.canvas.height = MINIMAP_HEIGHT;

        const p = plan.canvas.getContext("2d");
        p.clearRect(0, 0, MINIMAP_WIDTH, MINIMAP_HEIGHT);

        p.fillStyle = INK.backdrop;
        p.fillRect(0, 0, MINIMAP_WIDTH, MINIMAP_HEIGHT);

        // Rooms as filled blocks, so the plan reads as a floor plan and
        // not as a tangle of lines.
        p.fillStyle = INK.room;
        for (const room of map.rooms) {
            p.fillRect(mapX(room.x), mapY(room.y),
                       room.w * scale, room.h * scale);
        }

        // Walls over the top. Floored at one pixel, or a 24-pixel wall
        // scales down to nothing and the house loses its outline.
        p.fillStyle = INK.wall;
        for (const wall of map.walls) {
            p.fillRect(mapX(wall.x), mapY(wall.y),
                       Math.max(1, wall.w * scale),
                       Math.max(1, wall.h * scale));
        }

        // Doorways punched back through, since at this scale a house
        // with no visible way between its rooms is a maze.
        p.fillStyle = INK.door;
        for (const door of map.doorways) {
            p.fillRect(mapX(door.x), mapY(door.y),
                       Math.max(1, door.w * scale),
                       Math.max(1, door.h * scale));
        }

        // Home, which is the one place worth being able to find from
        // anywhere in the house — in the modes that have one.
        if (hasBase) {
            p.fillStyle = COLORS.base;
            for (const zone of map.base_zones) {
                p.fillRect(mapX(zone.x), mapY(zone.y),
                           Math.max(3, zone.w * scale),
                           Math.max(3, zone.h * scale));
            }
        }

        plan.of = map;
        plan.withBase = hasBase;
    }

    function resize() {
        const ratio = window.devicePixelRatio || 1;

        canvas.width = Math.round(MINIMAP_WIDTH * ratio);
        canvas.height = Math.round(MINIMAP_HEIGHT * ratio);
        canvas.style.width = `${MINIMAP_WIDTH}px`;
        canvas.style.height = `${MINIMAP_HEIGHT}px`;

        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    }

    window.addEventListener("resize", resize);
    resize();

    /* You, as an arrow pointing the way you last moved. An arrow rather
     * than a dot because half of getting lost is not knowing which way
     * you are already facing. */
    function drawYou(localPlayer, colour) {
        const x = mapX(localPlayer.x + localPlayer.size / 2);
        const y = mapY(localPlayer.y + localPlayer.size / 2);

        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(localPlayer.facing);

        ctx.fillStyle = colour;
        ctx.beginPath();
        ctx.moveTo(5, 0);
        ctx.lineTo(-4, -3.5);
        ctx.lineTo(-4, 3.5);
        ctx.closePath();
        ctx.fill();

        ctx.strokeStyle = COLORS.you;
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.restore();
    }

    function draw({ map, localPlayer, hasBase }) {
        if (plan.of !== map || plan.withBase !== hasBase) {
            fit(map);
            buildPlan(map, hasBase);
        }

        ctx.clearRect(0, 0, MINIMAP_WIDTH, MINIMAP_HEIGHT);
        ctx.drawImage(plan.canvas, 0, 0, MINIMAP_WIDTH, MINIMAP_HEIGHT);

        drawYou(localPlayer, localPlayer.color
            || (localPlayer.role === "tagger" ? COLORS.tagger : COLORS.hider));
    }

    return { draw };
}
