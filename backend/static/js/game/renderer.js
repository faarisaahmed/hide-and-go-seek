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
    DARKNESS_ALPHA,
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
    ROOM_LABEL_FONT,
    SEARCH_DISTANCE,
    SHADOW_INK,
    TILE_SIZE,
} from "./config.js";
import { hideSpotAt } from "./map_loader.js";
import { baseIsWall, getRound, playerNamed } from "./round.js";
import { activeShouts } from "./shouts.js";

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

    // Where the darkness is assembled before being laid over the frame.
    // Kept at CSS-pixel size rather than device pixels: it is a mask of
    // large flat shapes, so a retina backing store would quadruple the
    // fill for an edge nobody can see the softness of.
    const shadow = {};
    shadow.canvas = document.createElement("canvas");
    shadow.ctx = shadow.canvas.getContext("2d");

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

    function drawBase(map, now, walled) {
        // Breathes gently, so home is the thing your eye goes to in a
        // dark house.
        const pulse = 0.5 + 0.5 * Math.sin(now / 550);

        // To the seeker it is a wall rather than a destination, so it is
        // drawn as one: their colour, a hard edge, and "NO ENTRY" where
        // everybody else reads "HOME". An invisible wall you can see is
        // a rule; one you cannot is a bug report.
        const tone = walled ? COLORS.tagger : COLORS.base;

        for (const zone of map.base_zones) {
            if (!onScreen(zone)) continue;

            const x = screenX(zone.x);
            const y = screenY(zone.y);

            ctx.save();
            ctx.shadowColor = tone;
            ctx.shadowBlur = 18 + 14 * pulse;

            ctx.fillStyle = tone;
            ctx.globalAlpha = 0.22 + 0.12 * pulse;
            pathRect(ctx, x, y, zone.w, zone.h, 12);
            ctx.fill();

            ctx.globalAlpha = 1;
            ctx.strokeStyle = tone;
            ctx.lineWidth = 3;
            if (walled) ctx.setLineDash([9, 6]);
            ctx.stroke();
            ctx.restore();

            ctx.fillStyle = tone;
            ctx.font = "bold 12px Arial";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(walled ? "NO ENTRY" : "HOME",
                         x + zone.w / 2, y + zone.h / 2);
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

    /*
     * Two colours per player, and they answer different questions.
     *
     * The fill is theirs: the one they picked in the lobby, so "which of
     * these squares is Bob" has an answer at a glance. The ring is the
     * round's: rose for a seeker, pale for somebody frozen, green for
     * somebody standing on home. Roles used to be the fill, which meant
     * personalising a player would have hidden the one thing you have to
     * read instantly — so the ring took the job instead, and it is drawn
     * thick enough to read at the edge of the light.
     */
    function fillFor(player, record) {
        return player.color || (record?.role === "tagger"
            ? COLORS.tagger : COLORS.hider);
    }

    function roleColorFor(record) {
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
     * The circle you have to run into to thaw somebody, drawn round every
     * frozen player. A rescue is instant on contact, so there is no
     * progress to show — what there is to show is where "contact" starts,
     * which is the one thing a player arriving at a frozen team-mate
     * actually wants to know.
     *
     * Pulses, so it reads as something waiting for you rather than as
     * decoration painted on the floor.
     */
    function drawRescueRing(player, record, round, size, now) {
        if (!record || record.state !== "frozen") return;
        if (!round.rules.rescues) return;

        const cx = player.x + size / 2;
        const cy = player.y + size / 2;
        const pulse = 0.5 + 0.5 * Math.sin(now / 320);

        ctx.save();
        ctx.strokeStyle = COLORS.rescueRing;
        ctx.globalAlpha = 0.5 + 0.5 * pulse;
        ctx.lineWidth = 2.5;
        ctx.setLineDash([7, 7]);
        ctx.beginPath();
        ctx.arc(screenX(cx), screenY(cy), RESCUE_DISTANCE, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
    }

    /* One player: their square in their own colour, ringed in whatever
     * the round has made of them, their lobby emoji, and their name. */
    function drawPlayer(player, size, { isYou = false } = {}) {
        const record = playerNamed(player.name);
        const x = screenX(player.x);
        const y = screenY(player.y);

        ctx.save();
        if (record && record.state === "frozen") ctx.globalAlpha = 0.75;

        ctx.fillStyle = fillFor(player, record);
        pathRect(ctx, x, y, size, size, 8);
        ctx.fill();

        // The round's answer, over the player's own. Inset by half the
        // line width so the ring sits on the square rather than growing
        // it, which would make a seeker read as physically bigger.
        ctx.strokeStyle = roleColorFor(record);
        ctx.lineWidth = 4;
        pathRect(ctx, x + 2, y + 2, size - 4, size - 4, 6);
        ctx.stroke();

        // And your own square gets a bright hairline inside that, so you
        // never lose yourself in a crowd.
        if (isYou) {
            ctx.strokeStyle = COLORS.you;
            ctx.lineWidth = 1.5;
            pathRect(ctx, x + 5, y + 5, size - 10, size - 10, 4);
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
            ctx.fillStyle = roleColorFor(record);
            ctx.textAlign = "center";
            ctx.textBaseline = "alphabetic";
            ctx.fillText(marker, x + size / 2, y - 6);
        }

        ctx.fillStyle = player.color || COLORS.nameTag;
        ctx.font = NAME_TAG_FONT;
        ctx.textAlign = "center";
        ctx.textBaseline = "alphabetic";
        ctx.fillText(player.name, x + size / 2, y + size + NAME_TAG_OFFSET);
    }

    /* ===== Darkness ===== */

    /* ===== Darkness, and the shadows walls throw into it =====
     *
     * Built up on an offscreen canvas rather than painted straight onto
     * the frame, because it is made by *subtraction*: start with the
     * whole viewport dark, rub out what the player can see, then put the
     * dark back wherever a wall is in the way. Doing that in place would
     * mean overlapping shadows stacking into black patches, and a torch
     * beam that shone through the kitchen wall.
     *
     * The shadows are not decoration. game.can_see refuses to send a
     * player's position through a wall, so a room you cannot see into is
     * a room the server is keeping from you — the drawing is there to
     * make that legible rather than to enforce it.
     */

    function shadowSize() {
        if (shadow.canvas.width !== viewWidth || shadow.canvas.height !== viewHeight) {
            shadow.canvas.width = viewWidth;
            shadow.canvas.height = viewHeight;
        }
    }

    /*
     * The shadow a single wall throws, as one quad per edge facing away
     * from the player.
     *
     * Away, not towards: the quads then start at the wall's far side and
     * the wall itself stays lit, which is what you want when the wall is
     * also the thing you are navigating by. For a rectangle the union of
     * those quads is exactly the region behind it, so overlapping them
     * costs nothing but fill.
     */
    function castShadow(s, wall, lx, ly, far) {
        const x0 = screenX(wall.x);
        const y0 = screenY(wall.y);
        const x1 = x0 + wall.w;
        const y1 = y0 + wall.h;

        // Clockwise, which fixes the sign of the outward normal below.
        const corners = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];

        for (let i = 0; i < 4; i++) {
            const [ax, ay] = corners[i];
            const [bx, by] = corners[(i + 1) % 4];

            // Outward normal of a clockwise edge, with y pointing down.
            const nx = by - ay;
            const ny = ax - bx;
            if (nx * (lx - ax) + ny * (ly - ay) >= 0) continue;  // lit face

            const dax = ax - lx;
            const day = ay - ly;
            const dbx = bx - lx;
            const dby = by - ly;
            const la = Math.hypot(dax, day) || 1;
            const lb = Math.hypot(dbx, dby) || 1;

            s.beginPath();
            s.moveTo(ax, ay);
            s.lineTo(bx, by);
            s.lineTo(bx + (dbx / lb) * far, by + (dby / lb) * far);
            s.lineTo(ax + (dax / la) * far, ay + (day / la) * far);
            s.closePath();
            s.fill();
        }
    }

    /* Is any part of this wall inside the lit circle? Walls beyond it
     * only ever shadow floor that is already dark. */
    function withinReach(wall, lx, ly, reach) {
        const x0 = screenX(wall.x);
        const y0 = screenY(wall.y);
        const nearestX = Math.max(x0, Math.min(lx, x0 + wall.w));
        const nearestY = Math.max(y0, Math.min(ly, y0 + wall.h));

        return Math.hypot(lx - nearestX, ly - nearestY) <= reach;
    }

    /*
     * The seeker's torch, in the modes that give them one.
     *
     * A wedge rubbed out of the darkness, not a light laid over it — so
     * it stops at walls along with everything else. The angle is only
     * ever the direction the player last moved, which is what makes a
     * torch something you can be walked around behind.
     */
    function carveTorch(s, round, you, cx, cy) {
        const reach = round.rules.coneReach;
        const half = (round.rules.coneDegrees * Math.PI / 180) / 2;

        const gradient = s.createRadialGradient(cx, cy, 0, cx, cy, reach);
        gradient.addColorStop(0, "rgba(0, 0, 0, 1)");
        gradient.addColorStop(0.7, "rgba(0, 0, 0, 0.92)");
        gradient.addColorStop(1, "rgba(0, 0, 0, 0)");

        s.beginPath();
        s.moveTo(cx, cy);
        s.arc(cx, cy, reach, you.facing - half, you.facing + half);
        s.closePath();

        s.fillStyle = gradient;
        s.fill();
    }

    function drawDarkness(map, round, you) {
        const cx = screenX(you.x + you.size / 2);
        const cy = screenY(you.y + you.size / 2);

        // The mode's reach, not the config's: the server stops sending
        // people at this distance, so drawing a wider circle of light
        // would just be a ring of floor nobody is ever in.
        const reach = round.rules.visionRadius;
        const torch = round.rules.coneDegrees !== null
            && you.role === "tagger"
            && round.phase === "hunting";
        const lit = torch ? Math.max(reach, round.rules.coneReach) : reach;

        shadowSize();
        const s = shadow.ctx;

        s.globalCompositeOperation = "source-over";
        s.fillStyle = SHADOW_INK;
        s.clearRect(0, 0, viewWidth, viewHeight);
        s.fillRect(0, 0, viewWidth, viewHeight);

        // Rub out what is in sight. Soft at the edge, so the lit circle
        // fades rather than ending in a hard rim.
        s.globalCompositeOperation = "destination-out";

        const glow = s.createRadialGradient(cx, cy, reach * 0.45, cx, cy, reach);
        glow.addColorStop(0, "rgba(0, 0, 0, 1)");
        glow.addColorStop(1, "rgba(0, 0, 0, 0)");
        s.fillStyle = glow;
        s.fillRect(0, 0, viewWidth, viewHeight);

        if (torch) carveTorch(s, round, you, cx, cy);

        // And put it back wherever a wall is in the way.
        s.globalCompositeOperation = "source-over";
        s.fillStyle = SHADOW_INK;
        for (const wall of map.sightBlockers) {
            if (!onScreen(wall)) continue;
            if (!withinReach(wall, cx, cy, lit)) continue;
            castShadow(s, wall, cx, cy, lit * 2.2);
        }

        ctx.save();
        ctx.globalAlpha = DARKNESS_ALPHA;
        ctx.drawImage(shadow.canvas, 0, 0, viewWidth, viewHeight);
        ctx.restore();
    }

    /* Eyes shut. The seeker gets a near-black screen while counting; the
     * count itself is in the HUD, on top of the canvas. */
    function drawBlindfold() {
        ctx.fillStyle = COLORS.blindfold;
        ctx.fillRect(0, 0, viewWidth, viewHeight);
    }

    /*
     * A ripple at the edge of the screen for each shout still ringing,
     * pointing the way the noise came from.
     *
     * Drawn on the rim rather than at a point in the world because the
     * server does not tell us where the shouter is — only a bearing
     * rounded to a few degrees and roughly how far. Painting a marker on
     * the floor would be claiming to know something we were deliberately
     * not told; a direction on the edge of your vision is what hearing
     * somebody actually gives you.
     */
    function drawShouts(now) {
        // Inside the HUD's furniture rather than under it: the strip of
        // keycaps along the bottom sits over the canvas, and a ripple
        // drawn behind it is a ripple nobody sees.
        const rim = Math.min(viewWidth, viewHeight) * 0.34;
        const centreX = viewWidth / 2;
        const centreY = viewHeight / 2;

        for (const shout of activeShouts(now)) {
            const x = centreX + Math.cos(shout.bearing) * rim;
            const y = centreY + Math.sin(shout.bearing) * rim;

            // Close shouts land bigger and hang on the screen the same
            // length of time, so distance reads before the words do.
            const weight = shout.nearness === "close" ? 1
                : shout.nearness === "nearby" ? 0.72 : 0.5;

            ctx.save();
            ctx.globalAlpha = shout.life * 0.9;
            ctx.translate(x, y);
            ctx.rotate(shout.bearing);

            ctx.strokeStyle = COLORS.shout;
            ctx.lineWidth = 3.5;

            // Three arcs bulging the way the noise came from, spreading
            // as the shout fades. A sound, drawn.
            for (let i = 0; i < 3; i++) {
                const spread = (16 + i * 13) * weight + (1 - shout.life) * 14;
                ctx.globalAlpha = shout.life * (0.85 - i * 0.22);
                ctx.beginPath();
                ctx.arc(0, 0, spread, -0.72, 0.72);
                ctx.stroke();
            }
            ctx.restore();
        }
    }

    /*
     * A chevron at the edge of the screen pointing home, with how far it
     * is. Hiders have to get back to a base they usually cannot see, and
     * hunting for it in the dark is tedious rather than tense.
     */
    function drawHomeCompass(map, round, you) {
        if (round.phase !== "hunting" || you.role !== "hider") return;
        // Nothing to run home to in a mode where the base is just a rug.
        if (!round.rules.homeIsSafety) return;

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
        // Only in the modes that have one. A glowing square on the floor
        // that does nothing is worse than no square at all: people run
        // to it, and nothing happens when they get there.
        if (round.rules.hasBase) {
            drawBase(map, now, baseIsWall(localPlayer.role));
        }
        drawFurniture(map.solidFurniture, COLORS.solid);

        drawRoomLabels(map);
        drawWalls(map);

        drawOwnHidingSpot(map, round, localPlayer);
        drawNoHideRing(map, round, localPlayer);
        drawSearchRing(round, localPlayer);

        for (const remote of Object.values(remotePlayers)) {
            drawRescueRing(remote, playerNamed(remote.name), round,
                           localPlayer.size, now);
            // The server sends positions only, so remotes are drawn at the
            // same size as us.
            drawPlayer(remote, localPlayer.size);
        }

        // Your own, so a frozen player can see the circle somebody has to
        // reach rather than only being told to sit tight.
        drawRescueRing(localPlayer, playerNamed(localPlayer.name), round,
                       localPlayer.size, now);

        // Drawn last so we are never hidden underneath someone else.
        drawPlayer(localPlayer, localPlayer.size, { isYou: true });

        // The count is the one time the seeker is meant to see nothing at
        // all, so it replaces the darkness rather than joining it.
        if (round.phase === "counting" && localPlayer.role === "tagger") {
            drawBlindfold();
        } else if (round.phase === "counting" || round.phase === "hunting") {
            // The torch is carved out of this rather than laid over it,
            // so a beam stops at a wall like everything else does.
            drawDarkness(map, round, localPlayer);
        }

        drawHomeCompass(map, round, localPlayer);

        // Over the darkness: you hear a shout through a wall, which is
        // the entire reason for having one.
        drawShouts(now);
    }

    return { draw };
}
