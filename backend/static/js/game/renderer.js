/*
 * Drawing the world onto the canvas.
 *
 * Everything is drawn in world coordinates minus the camera offset. The
 * camera is centred on the local player, so the player stays in the middle
 * of the screen and the map moves underneath.
 *
 * Draw order is the reason the house reads as a house: floor, then the
 * things lying on it, then furniture, then walls over the top of both, so
 * nothing ever appears to sit on a wall. The darkness goes on last of
 * all, because it has to dim the house as well as the people in it.
 */

import {
    COLORS,
    CULL_MARGIN,
    EMOJI_FONT,
    FURNITURE_FONT_MAX,
    FURNITURE_FONT_MIN,
    MOONLIGHT_REACH,
    NAME_TAG_FONT,
    NAME_TAG_OFFSET,
    NO_HIDE_RADIUS,
    PLANK_HEIGHT,
    PLANK_LENGTH,
    RESCUE_DISTANCE,
    RESCUE_HOLD_SECONDS,
    ROOM_LABEL_FONT,
    SEARCH_DISTANCE,
    TILE_SIZE,
} from "./config.js";
import { hideSpotAt } from "./map_loader.js";
import { getRound, playerNamed } from "./round.js";

/*
 * Rounded rectangles, with a square fallback.
 *
 * ctx.roundRect only arrived in Safari 16.4, and this game gets opened
 * on whatever phone is on the Wi-Fi. Square furniture is a much smaller
 * problem than a blank canvas and a thrown exception.
 */
function pathRect(ctx, x, y, w, h, radius) {
    ctx.beginPath();
    if (ctx.roundRect) {
        ctx.roundRect(x, y, w, h, radius);
    } else {
        ctx.rect(x, y, w, h);
    }
}

export function createRenderer(canvas) {
    const ctx = canvas.getContext("2d");
    const camera = { x: 0, y: 0 };

    // Viewport in CSS pixels. The backing store is larger on a retina
    // screen, but everything we draw is in CSS pixels.
    let viewWidth = 0;
    let viewHeight = 0;

    // When each frozen player first had a rescuer standing next to them,
    // so the thaw can be drawn filling up. The server keeps the real
    // clock; this only has to look right.
    const rescueStartedAt = new Map();

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

    function screenX(worldX) {
        return worldX - camera.x;
    }

    function screenY(worldY) {
        return worldY - camera.y;
    }

    /* ===== The house ===== */

    /* The visible slice of a rectangle, in world coordinates, or null.
     * Floor texture is drawn line by line, so it has to be clipped to
     * what is actually on screen rather than to the whole room. */
    function visiblePart(rect) {
        const x0 = Math.max(rect.x, camera.x);
        const y0 = Math.max(rect.y, camera.y);
        const x1 = Math.min(rect.x + rect.w, camera.x + viewWidth);
        const y1 = Math.min(rect.y + rect.h, camera.y + viewHeight);

        return x1 > x0 && y1 > y0 ? { x0, y0, x1, y1 } : null;
    }

    /*
     * Floorboards: a seam every plank, plus staggered board ends. Two
     * rows of loops rather than a repeating pattern fill, because a
     * pattern has to be re-anchored to the camera every frame and this
     * is only a few dozen thin rectangles once culled.
     */
    function drawPlanks(room, part) {
        ctx.fillStyle = COLORS.plank;

        const width = part.x1 - part.x0;
        const first = room.y + Math.floor((part.y0 - room.y) / PLANK_HEIGHT) * PLANK_HEIGHT;

        for (let y = first; y < part.y1; y += PLANK_HEIGHT) {
            if (y < part.y0) continue;
            ctx.fillRect(screenX(part.x0), screenY(y), width, 1);

            // Board ends, offset on alternate rows so the floor does not
            // look like graph paper.
            const row = Math.round((y - room.y) / PLANK_HEIGHT);
            const stagger = (row % 2) * (PLANK_LENGTH / 2);
            const firstEnd = room.x + stagger
                + Math.floor((part.x0 - room.x - stagger) / PLANK_LENGTH) * PLANK_LENGTH;

            for (let x = firstEnd; x < part.x1; x += PLANK_LENGTH) {
                if (x < part.x0) continue;
                ctx.fillRect(screenX(x), screenY(y), 1,
                             Math.min(PLANK_HEIGHT, part.y1 - y));
            }
        }
    }

    /* Tiles: a plain grid, which is what makes a bathroom read as one. */
    function drawTiles(room, part) {
        ctx.fillStyle = COLORS.grout;

        const firstY = room.y + Math.floor((part.y0 - room.y) / TILE_SIZE) * TILE_SIZE;
        for (let y = firstY; y < part.y1; y += TILE_SIZE) {
            if (y >= part.y0) {
                ctx.fillRect(screenX(part.x0), screenY(y), part.x1 - part.x0, 1);
            }
        }

        const firstX = room.x + Math.floor((part.x0 - room.x) / TILE_SIZE) * TILE_SIZE;
        for (let x = firstX; x < part.x1; x += TILE_SIZE) {
            if (x >= part.x0) {
                ctx.fillRect(screenX(x), screenY(part.y0), 1, part.y1 - part.y0);
            }
        }
    }

    function drawFloor(map) {
        // Everything outside the house gets the void colour.
        ctx.fillStyle = COLORS.void;
        ctx.fillRect(0, 0, viewWidth, viewHeight);

        // A base coat over the footprint of the house, so the gaps
        // between rooms (walls, doorways) are never bare void.
        const shell = visiblePart({ x: 0, y: 0, w: map.width, h: map.height });
        if (shell) {
            ctx.fillStyle = COLORS.floorFallback;
            ctx.fillRect(screenX(shell.x0), screenY(shell.y0),
                         shell.x1 - shell.x0, shell.y1 - shell.y0);
        }

        for (const room of map.rooms) {
            const part = visiblePart(room);
            if (!part) continue;

            ctx.fillStyle = COLORS.floors[room.floor] ?? COLORS.floorFallback;
            ctx.fillRect(screenX(part.x0), screenY(part.y0),
                         part.x1 - part.x0, part.y1 - part.y0);

            if (room.floor === "wood") drawPlanks(room, part);
            else if (room.floor === "tile") drawTiles(room, part);
        }

        // A doorway is a hole in a wall; a threshold strip is what makes
        // it read as a door rather than as a missing wall.
        ctx.fillStyle = COLORS.threshold;
        for (const door of map.doorways) {
            if (!onScreen(door)) continue;
            ctx.fillRect(screenX(door.x), screenY(door.y), door.w, door.h);
        }
    }

    /*
     * Moonlight pooling in from each window. Purely atmosphere — the
     * vision radius is what actually decides what you can see — but it
     * breaks up a dark house and gives you something to steer by.
     */
    function drawMoonlight(map) {
        for (const win of map.windows) {
            const down = win.into === "down";
            const up = win.into === "up";
            const right = win.into === "right";

            const vertical = down || up;
            const pool = vertical
                ? {
                    x: win.x, w: win.w,
                    y: down ? win.y + win.h : win.y - MOONLIGHT_REACH,
                    h: MOONLIGHT_REACH,
                }
                : {
                    y: win.y, h: win.h,
                    x: right ? win.x + win.w : win.x - MOONLIGHT_REACH,
                    w: MOONLIGHT_REACH,
                };

            if (!onScreen(pool)) continue;

            // Brightest at the glass, gone by the far end.
            const near = down ? pool.y : up ? pool.y + pool.h
                : right ? pool.x : pool.x + pool.w;
            const far = down ? pool.y + pool.h : up ? pool.y
                : right ? pool.x + pool.w : pool.x;

            const gradient = vertical
                ? ctx.createLinearGradient(0, screenY(near), 0, screenY(far))
                : ctx.createLinearGradient(screenX(near), 0, screenX(far), 0);
            gradient.addColorStop(0, COLORS.moonlight);
            gradient.addColorStop(1, "rgba(154, 214, 255, 0)");

            ctx.fillStyle = gradient;
            ctx.fillRect(screenX(pool.x), screenY(pool.y), pool.w, pool.h);
        }
    }

    /*
     * Room names, tucked near the top of the room.
     *
     * Drawn after the furniture, not before it: a label under a wardrobe
     * set against the top wall is a label nobody can read, and in a dark
     * house knowing which room you have run into is most of what you
     * need. Faint enough not to fight the furniture it crosses.
     */
    function drawRoomLabels(map) {
        ctx.font = ROOM_LABEL_FONT;
        ctx.fillStyle = COLORS.roomLabel;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";

        for (const room of map.rooms) {
            if (!room.name || !onScreen(room)) continue;
            ctx.fillText(
                room.name.toUpperCase(),
                screenX(room.x + room.w / 2),
                screenY(room.y + Math.min(38, room.h / 2)),
            );
        }
    }

    /* One piece of furniture: its footprint, then its icon on top. */
    function drawFurniture(items, color) {
        for (const item of items) {
            if (!onScreen(item)) continue;

            const x = screenX(item.x);
            const y = screenY(item.y);

            ctx.fillStyle = color;
            pathRect(ctx, x, y, item.w, item.h, 6);
            ctx.fill();

            if (!item.icon) continue;

            // Shrink the icon to fit the smaller side, so a slim shelf
            // does not get an icon wider than itself.
            const size = Math.max(
                FURNITURE_FONT_MIN,
                Math.min(FURNITURE_FONT_MAX, Math.floor(Math.min(item.w, item.h) * 0.7)),
            );
            ctx.font = `${size}px sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(item.icon, x + item.w / 2, y + item.h / 2);
        }
    }

    function drawWalls(map) {
        // Shadows first, as a single pass. Done per wall they would fall
        // across the neighbouring wall instead of onto the floor.
        ctx.fillStyle = COLORS.wallShadow;
        for (const wall of map.walls) {
            if (!onScreen(wall)) continue;
            ctx.fillRect(screenX(wall.x) + 5, screenY(wall.y) + 6, wall.w, wall.h);
        }

        for (const wall of map.walls) {
            if (!onScreen(wall)) continue;

            const x = screenX(wall.x);
            const y = screenY(wall.y);

            ctx.fillStyle = COLORS.wall;
            ctx.fillRect(x, y, wall.w, wall.h);

            // A lighter lip along the top edge, which is enough to read
            // the walls as having height.
            ctx.fillStyle = COLORS.wallTop;
            ctx.fillRect(x, y, wall.w, 3);
        }

        // Glass, set into the wall it interrupts.
        for (const win of map.windows) {
            if (!onScreen(win)) continue;

            ctx.fillStyle = COLORS.windowFrame;
            ctx.fillRect(screenX(win.x), screenY(win.y), win.w, win.h);

            const inset = 6;
            ctx.fillStyle = COLORS.window;
            ctx.fillRect(screenX(win.x) + inset, screenY(win.y) + inset,
                         win.w - inset * 2, win.h - inset * 2);
        }
    }

    function drawBase(map, now) {
        // Breathes gently, so home is the thing your eye goes to in a
        // dark house.
        const pulse = 0.5 + 0.5 * Math.sin(now / 550);

        for (const zone of map.base_zones) {
            if (!onScreen(zone)) continue;

            const x = screenX(zone.x);
            const y = screenY(zone.y);

            ctx.save();
            ctx.shadowColor = COLORS.base;
            ctx.shadowBlur = 18 + 14 * pulse;

            ctx.fillStyle = COLORS.base;
            ctx.globalAlpha = 0.22 + 0.12 * pulse;
            pathRect(ctx, x, y, zone.w, zone.h, 12);
            ctx.fill();

            ctx.globalAlpha = 1;
            ctx.strokeStyle = COLORS.base;
            ctx.lineWidth = 3;
            ctx.stroke();
            ctx.restore();

            ctx.fillStyle = COLORS.base;
            ctx.font = "bold 12px Arial";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText("HOME", x + zone.w / 2, y + zone.h / 2);
        }
    }

    /* ===== Rings that explain a rule ===== */

    function ring(worldX, worldY, radius, color, dashed = false) {
        ctx.save();
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        if (dashed) ctx.setLineDash([10, 10]);
        ctx.beginPath();
        ctx.arc(screenX(worldX), screenY(worldY), radius, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
    }

    /*
     * While the seeker counts, hiders see the circle they have to get
     * out of. Standing inside it when the count ends gets you moved to a
     * hiding spot, so it is worth drawing rather than explaining.
     */
    function drawNoHideRing(map, round, you) {
        if (round.phase !== "counting" || you.role === "tagger") return;
        ring(map.baseCenter.x, map.baseCenter.y, NO_HIDE_RADIUS, COLORS.noHideRing, true);
    }

    /* The seeker's own screen shows how close they have to be to turn
     * out a hiding spot. Pointless in a mode where furniture hides
     * nobody, and drawing it there would promise a mechanic that is
     * switched off. */
    function drawSearchRing(round, you) {
        if (you.role !== "tagger" || round.phase !== "hunting") return;
        if (!round.rules.hidingConceals) return;
        ring(you.x + you.size / 2, you.y + you.size / 2, SEARCH_DISTANCE, COLORS.searchRing);
    }

    /* The hiding spot the local player is tucked into, outlined so they
     * can tell that they are actually in it. */
    function drawOwnHidingSpot(map, round, you) {
        if (!round.rules.hidingConceals) return;

        const spot = hideSpotAt(map, you.x + you.size / 2, you.y + you.size / 2);
        if (!spot) return;

        ctx.save();
        ctx.strokeStyle = COLORS.base;
        ctx.lineWidth = 3;
        ctx.setLineDash([8, 6]);
        pathRect(ctx, screenX(spot.x), screenY(spot.y), spot.w, spot.h, 6);
        ctx.stroke();
        ctx.restore();
    }

    /* ===== Players ===== */

    function colorFor(record) {
        if (!record) return COLORS.hider;
        if (record.state === "frozen") return COLORS.frozen;
        if (record.state === "safe") return COLORS.safe;
        return record.role === "tagger" ? COLORS.tagger : COLORS.hider;
    }

    function markerFor(record) {
        if (!record) return "";
        if (record.state === "frozen") return "❄";  /* snowflake */
        if (record.state === "safe") return "✓";    /* tick */
        return record.role === "tagger" ? "!" : "";
    }

    /*
     * A frozen player with a free hider next to them gets a ring that
     * fills as the thaw completes. Timed locally, because the exact
     * clock belongs to the server and this only has to look right.
     */
    function drawRescueProgress(player, record, remotePlayers, localPlayer, now) {
        if (!record || record.state !== "frozen") return;

        const cx = player.x + localPlayer.size / 2;
        const cy = player.y + localPlayer.size / 2;

        const candidates = [...Object.values(remotePlayers), localPlayer];
        const rescuing = candidates.some((other) => {
            if (other.name === player.name) return false;
            const theirs = playerNamed(other.name);
            if (!theirs || theirs.role !== "hider" || theirs.state !== "free") return false;

            const dx = other.x + localPlayer.size / 2 - cx;
            const dy = other.y + localPlayer.size / 2 - cy;
            return Math.hypot(dx, dy) <= RESCUE_DISTANCE;
        });

        if (!rescuing) {
            rescueStartedAt.delete(player.name);
            return;
        }

        if (!rescueStartedAt.has(player.name)) {
            rescueStartedAt.set(player.name, now);
        }

        const held = (now - rescueStartedAt.get(player.name)) / 1000;
        const progress = Math.min(1, held / RESCUE_HOLD_SECONDS);

        ctx.save();
        ctx.strokeStyle = COLORS.rescueRing;
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.arc(
            screenX(cx), screenY(cy), localPlayer.size * 0.85,
            -Math.PI / 2, -Math.PI / 2 + progress * Math.PI * 2,
        );
        ctx.stroke();
        ctx.restore();
    }

    /* One player: their square, their lobby emoji, their name, and
     * whatever the round has done to them. */
    function drawPlayer(player, size, { isYou = false } = {}) {
        const record = playerNamed(player.name);
        const x = screenX(player.x);
        const y = screenY(player.y);

        ctx.save();
        if (record && record.state === "frozen") ctx.globalAlpha = 0.75;

        ctx.fillStyle = colorFor(record);
        pathRect(ctx, x, y, size, size, 8);
        ctx.fill();

        // Your own square gets a bright outline, so you never lose
        // yourself among four other blue squares.
        if (isYou) {
            ctx.strokeStyle = COLORS.you;
            ctx.lineWidth = 2.5;
            ctx.stroke();
        }
        ctx.restore();

        if (player.emoji) {
            ctx.font = EMOJI_FONT;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(player.emoji, x + size / 2, y + size / 2);
        }

        const marker = markerFor(record);
        if (marker) {
            ctx.font = "bold 16px Arial";
            ctx.fillStyle = colorFor(record);
            ctx.textAlign = "center";
            ctx.textBaseline = "alphabetic";
            ctx.fillText(marker, x + size / 2, y - 6);
        }

        ctx.fillStyle = COLORS.nameTag;
        ctx.font = NAME_TAG_FONT;
        ctx.textAlign = "center";
        ctx.textBaseline = "alphabetic";
        ctx.fillText(player.name, x + size / 2, y + size + NAME_TAG_OFFSET);
    }

    /* ===== Darkness ===== */

    /*
     * The house stays visible past the vision radius but the people in
     * it do not, because the server never sent them. Dimming rather than
     * blacking out means you can still find your way to the kitchen in
     * the dark, which is the bit that feels like hide and seek.
     */
    function drawDarkness(round, you) {
        const cx = screenX(you.x + you.size / 2);
        const cy = screenY(you.y + you.size / 2);

        // The mode's reach, not the config's: the server stops sending
        // people at this distance, so drawing a wider circle of light
        // would just be a ring of floor nobody is ever in.
        const reach = round.rules.visionRadius;

        const gradient = ctx.createRadialGradient(
            cx, cy, reach * 0.5, cx, cy, reach,
        );
        gradient.addColorStop(0, "rgba(3, 6, 14, 0)");
        gradient.addColorStop(1, COLORS.darkness);

        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, viewWidth, viewHeight);
    }

    /* Eyes shut. The seeker gets a near-black screen while counting; the
     * count itself is in the HUD, on top of the canvas. */
    function drawBlindfold() {
        ctx.fillStyle = COLORS.blindfold;
        ctx.fillRect(0, 0, viewWidth, viewHeight);
    }

    /*
     * A chevron at the edge of the screen pointing home, with how far it
     * is. Hiders have to get back to a base they usually cannot see, and
     * hunting for it in the dark is tedious rather than tense.
     */
    function drawHomeCompass(map, round, you) {
        if (round.phase !== "hunting" || you.role !== "hider") return;

        const cx = screenX(map.baseCenter.x);
        const cy = screenY(map.baseCenter.y);
        const onCamera = cx > 0 && cx < viewWidth && cy > 0 && cy < viewHeight;
        if (onCamera) return;

        const centreX = viewWidth / 2;
        const centreY = viewHeight / 2;
        const angle = Math.atan2(cy - centreY, cx - centreX);
        const radius = Math.min(centreX, centreY) * 0.62;

        const tipX = centreX + Math.cos(angle) * radius;
        const tipY = centreY + Math.sin(angle) * radius;

        ctx.save();
        ctx.translate(tipX, tipY);
        ctx.rotate(angle);

        ctx.fillStyle = COLORS.base;
        ctx.globalAlpha = 0.85;
        ctx.beginPath();
        ctx.moveTo(11, 0);
        ctx.lineTo(-8, -8);
        ctx.lineTo(-8, 8);
        ctx.closePath();
        ctx.fill();
        ctx.restore();

        const away = Math.round(
            Math.hypot(map.baseCenter.x - you.x, map.baseCenter.y - you.y) / 10,
        );
        ctx.fillStyle = COLORS.base;
        ctx.font = "bold 12px Arial";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(`${away}m`, tipX, tipY + 20);
    }

    /* ===== The frame ===== */

    function draw({ map, localPlayer, remotePlayers }) {
        const round = getRound();
        const now = performance.now();

        camera.x = localPlayer.x - viewWidth / 2;
        camera.y = localPlayer.y - viewHeight / 2;

        drawFloor(map);
        drawMoonlight(map);

        drawFurniture(map.decor, COLORS.decor);
        drawFurniture(map.hideSpots, COLORS.hide);
        drawBase(map, now);
        drawFurniture(map.solidFurniture, COLORS.solid);

        drawRoomLabels(map);
        drawWalls(map);

        drawOwnHidingSpot(map, round, localPlayer);
        drawNoHideRing(map, round, localPlayer);
        drawSearchRing(round, localPlayer);

        for (const remote of Object.values(remotePlayers)) {
            drawRescueProgress(remote, playerNamed(remote.name),
                               remotePlayers, localPlayer, now);
            // The server sends positions only, so remotes are drawn at the
            // same size as us.
            drawPlayer(remote, localPlayer.size);
        }

        // Your own thaw is the one you most want to watch fill up.
        drawRescueProgress(localPlayer, playerNamed(localPlayer.name),
                           remotePlayers, localPlayer, now);

        // Drawn last so we are never hidden underneath someone else.
        drawPlayer(localPlayer, localPlayer.size, { isYou: true });

        // The count is the one time the seeker is meant to see nothing at
        // all, so it replaces the darkness rather than joining it.
        if (round.phase === "counting" && localPlayer.role === "tagger") {
            drawBlindfold();
        } else if (round.phase === "counting" || round.phase === "hunting") {
            drawDarkness(round, localPlayer);
        }

        drawHomeCompass(map, round, localPlayer);
    }

    return { draw };
}
