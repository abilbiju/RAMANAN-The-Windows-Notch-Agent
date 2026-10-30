// Pixel-art Ramanan and fish: the same sprites the app draws (notch/ui/mascot.py).

export const PALETTE = {
  H: "#17100d", // hair / eyebrows
  S: "#8a5532", // skin
  s: "#6a3d22", // skin shadow
  B: "#1d1511", // beard & moustache
  W: "#f4f0e6", // eyes & teeth
  E: "#0b0b0b", // pupils
  M: "#5c1c16", // mouth
  Y: "#f3c51b", // yellow shirt
  y: "#c9970b", // shirt shadow
  C: "#e9e3d2", // chain
};

const SPRITE = [
  "....HHHHHHHH....",
  "...HHHHHHHHHH...",
  "..HHHHHHHHHHHH..",
  "..HSSSSSHSSSSH..",
  "..SHHHSSSSHHHS..",
  ".sSWEWSSSSWEWSs.",
  ".sSSSSSssSSSSSs.",
  "..SSBBBBBBBBSS..",
  "..BBBWWWWWWBBB..",
  "..BBBBMMMMBBBB..",
  "...BBBBBBBBBB...",
  "....BBBBBBBB....",
  "......SSSS......",
  "...YYYCSSCYYY...",
  ".YYYYYYCCYYYYYY.",
  "YYYYYyyCyyYYYYYY",
  "YYyySSSSSSSyYYYY",
  "YYYYyysssssssyYY",
  "YYYYYyYYYYyYYYYY",
];
const ARMLESS = { 16: ".YYYYYyyyYYYYYY.", 17: ".YYYYYYYYYYYYYY.", 18: ".YYYYyYYYYyYYYY." };
const FOREHEAD_RAISED = "..HSHHSSHSHHSH..";
const BROWS_RAISED = "..SSSSSSSSSSSS..";
const FACES = {
  grin: {},
  blink: { 5: ".sSSSSSSSSSSSSs.", 6: ".sSHHHSssSHHHSs." },
  brows: { 3: FOREHEAD_RAISED, 4: BROWS_RAISED },
};

export const SPRITE_W = 16;
export const SPRITE_H = SPRITE.length;
const MARGIN = 4; // dancing sprites get extra columns so the arms can swing out
const WIDE_W = SPRITE_W + 2 * MARGIN;

// Same poses and moves as the app: (elbow, hand) for the left arm, mirrored for the right.
const SHOULDER = [4, 14];
const POSES = {
  down: [[3, 16], [3, 17]],
  hip: [[1, 16], [4, 17]],
  up: [[2, 10], [3, 5]],
  pump: [[3, 9], [3, 3]],
  out: [[1, 13], [0, 11]],
  point: [[2, 11], [0, 6]],
  low: [[2, 16], [0, 17]],
  flex: [[1, 15], [2, 10]],
  chest: [[2, 16], [7, 15]],
};
const MOVES = {
  headbob: [["cross", "cross", 0, -1, -2], ["cross", "cross", 0, 0, 2]],
  sway: [["chest", "hip", -2, 0, -4], ["hip", "chest", 2, 0, 4]],
  bhangra: [["up", "pump", -1, -2, -4], ["pump", "up", 1, 0, 4]],
  disco: [["point", "hip", 0, -1, -5], ["low", "hip", 0, 0, 2], ["point", "hip", 0, -1, -5], ["low", "hip", 0, 0, 2],
          ["hip", "point", 0, -1, 5], ["hip", "low", 0, 0, -2], ["hip", "point", 0, -1, 5], ["hip", "low", 0, 0, -2]],
  wave: [["out", "out", 0, -1, 0], ["up", "down", 0, 0, -4], ["out", "out", 0, -1, 0], ["down", "up", 0, 0, 4]],
  flex: [["flex", "flex", 0, -2, 0], ["chest", "chest", 0, 0, 0]],
};
const CALM_MOVES = ["headbob", "sway"];
const BIG_MOVES = ["bhangra", "disco", "wave", "flex"];
const BEATS_PER_SECOND = 1.9;
const BEATS_PER_MOVE = 8;

export const FISH = [".TTTT.T", "TeYYYTT", ".TTTT.T"];
export const FISH_COLORS = { T: "#6fa8b5", Y: "#e3c04d", e: "#1b2b30" };

function drawArm(grid, pose, mirror) {
  const [elbow, hand] = POSES[pose];
  const flip = ([x, y]) => (mirror ? [WIDE_W - 2 - x, y] : [x, y]);
  const line = (a, b, ch) => {
    const steps = Math.max(Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]), 1);
    for (let i = 0; i <= steps; i++) {
      const x = Math.round(a[0] + ((b[0] - a[0]) * i) / steps);
      const y = Math.round(a[1] + ((b[1] - a[1]) * i) / steps);
      for (const [px, py] of [[x, y], [x + 1, y], [x, y + 1], [x + 1, y + 1]]) {
        if (px >= 0 && px < WIDE_W && py >= 0 && py < SPRITE_H) grid[py][px] = ch;
      }
    }
  };
  line(flip(SHOULDER), flip(elbow), "Y");
  line(flip(elbow), flip(hand), "S");
}

/** Rows of palette keys. `wide` adds side margins; arm poses other than "cross" need it. */
export function frame({ face = "grin", left = "cross", right = "cross", wide = false } = {}) {
  const rows = SPRITE.slice();
  for (const [i, row] of Object.entries(FACES[face])) rows[i] = row;
  const crossed = left === "cross" && right === "cross";
  if (!crossed) for (const [i, row] of Object.entries(ARMLESS)) rows[i] = row;
  if (!wide) return rows;
  const pad = ".".repeat(MARGIN);
  const grid = rows.map((r) => [...(pad + r + pad)]);
  if (!crossed) {
    drawArm(grid, left === "cross" ? "down" : left, false);
    drawArm(grid, right === "cross" ? "down" : right, true);
  }
  return grid.map((r) => r.join(""));
}

export function drawPixels(ctx, rows, colors, scale, ox = 0, oy = 0, flip = false) {
  const w = rows[0].length;
  for (let y = 0; y < rows.length; y++) {
    for (let x = 0; x < w; x++) {
      const c = colors[rows[y][x]];
      if (!c) continue;
      ctx.fillStyle = c;
      const px = flip ? w - 1 - x : x;
      ctx.fillRect(ox + px * scale, oy + y * scale, scale, scale);
    }
  }
}

const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

/** A living Ramanan on a <canvas>: blinks, raises his brows, dances with real moves.
 *  Sprites that dance (or `wide: true`) use a wider canvas so the arms fit. */
export class Ramanan {
  constructor(canvas, { scale = 4, dancing = false, wide = dancing } = {}) {
    this.canvas = canvas;
    this.scale = scale;
    this.dancing = dancing;
    this.wide = wide;
    this.level = 0.5;
    canvas.width = (wide ? WIDE_W : SPRITE_W) * scale;
    canvas.height = SPRITE_H * scale;
    canvas.style.transformOrigin = "50% 100%";
    this.ctx = canvas.getContext("2d");
    const now = performance.now();
    this.nextBlink = now + 1500;
    this.nextBrows = now + 4000;
    this.move = "headbob";
    this.moveUntil = 0;
    this.last = "";
    this.tick = this.tick.bind(this);
    requestAnimationFrame(this.tick);
  }

  setDancing(on) {
    this.dancing = on;
    this.moveUntil = 0;
    if (!on) this.canvas.style.transform = "";
  }

  step(beat) {
    if (beat >= this.moveUntil) {
      const pool = this.level > 0.18 ? BIG_MOVES : CALM_MOVES;
      const options = pool.filter((m) => m !== this.move);
      this.move = options[Math.floor(Math.random() * options.length)];
      this.moveUntil = beat + BEATS_PER_MOVE;
    }
    const steps = MOVES[this.move];
    return steps[beat % steps.length];
  }

  tick(now) {
    if (now > this.nextBlink + 140) this.nextBlink = now + 2500 + Math.random() * 3000;
    if (now > this.nextBrows + 600) this.nextBrows = now + 6000 + Math.random() * 6000;
    let face = this.nextBlink <= now ? "blink" : this.nextBrows <= now ? "brows" : "grin";
    let left = "cross";
    let right = "cross";

    if (this.dancing && !reducedMotion.matches) {
      const pos = (now / 1000) * BEATS_PER_SECOND;
      const beat = Math.floor(pos);
      const frac = pos - beat;
      let dx = 0, dy = 0, tilt = 0;
      if (this.wide) [left, right, dx, dy, tilt] = this.step(beat);
      else tilt = Math.sin((pos * Math.PI) / 2) * 5;
      const bob = (dy - Math.abs(Math.sin(frac * Math.PI)) * (1 + this.level * 2.5)) * (this.scale / 2);
      if (face === "grin" && frac < 0.3 && beat % 2) face = "brows";
      this.canvas.style.transform =
        `translate(${(dx * this.scale).toFixed(1)}px, ${bob.toFixed(1)}px) rotate(${tilt.toFixed(1)}deg)`;
    }

    const key = `${face}${left}${right}`;
    if (key !== this.last) {
      this.last = key;
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      drawPixels(this.ctx, frame({ face, left, right, wide: this.wide }), PALETTE, this.scale);
    }
    requestAnimationFrame(this.tick);
  }
}

/** Fish (and bubbles) swimming across a canvas, right to left. */
export class FishTank {
  constructor(canvas, { count = 3, scale = 2, bubbles = true, alpha = 1, speed = 1 } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.scale = scale;
    this.alpha = alpha;
    this.speed = speed;
    this.bubblesOn = bubbles;
    this.count = count;
    this.fish = [];
    this.bubbles = [];
    this.resize();
    new ResizeObserver(() => this.resize()).observe(canvas);
    for (let i = 0; i < count; i++) this.fish.push(this.spawn(Math.random()));
    this.prev = performance.now();
    this.tick = this.tick.bind(this);
    requestAnimationFrame(this.tick);
  }

  resize() {
    const r = this.canvas.getBoundingClientRect();
    this.w = Math.max(1, Math.round(r.width));
    this.h = Math.max(1, Math.round(r.height));
    this.canvas.width = this.w;
    this.canvas.height = this.h;
    this.ctx.imageSmoothingEnabled = false;
  }

  spawn(x) {
    const s = this.scale * (0.8 + Math.random() * 0.6);
    return {
      x: x ?? 1.05,
      y: 0.08 + Math.random() * 0.84,
      v: (0.02 + Math.random() * 0.04) * this.speed,
      s: Math.max(1, Math.round(s)),
      wob: Math.random() * 6,
    };
  }

  tick(now) {
    const dt = Math.min(0.05, (now - this.prev) / 1000);
    this.prev = now;
    const { ctx, w, h } = this;
    ctx.clearRect(0, 0, w, h);
    ctx.globalAlpha = this.alpha;
    const still = reducedMotion.matches;

    for (const f of this.fish) {
      if (!still) f.x -= f.v * dt;
      if (f.x < -0.1) Object.assign(f, this.spawn(1.05));
      const y = f.y * h + Math.sin(now / 700 + f.wob) * 2;
      drawPixels(ctx, FISH, FISH_COLORS, f.s, Math.round(f.x * w), Math.round(y));
      if (this.bubblesOn && !still && Math.random() < 0.004) {
        this.bubbles.push({ x: f.x * w, y, s: Math.max(1, f.s - 1) });
      }
    }
    ctx.fillStyle = "rgba(111,168,181,0.55)";
    for (const b of this.bubbles) {
      b.y -= 14 * dt * (this.scale / 2);
      ctx.fillRect(Math.round(b.x), Math.round(b.y), b.s * 2, b.s * 2);
    }
    this.bubbles = this.bubbles.filter((b) => b.y > -4);
    ctx.globalAlpha = 1;
    requestAnimationFrame(this.tick);
  }
}
