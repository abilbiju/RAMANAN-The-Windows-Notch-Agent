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
const FOREHEAD_RAISED = "..HSHHSSHSHHSH..";
const BROWS_RAISED = "..SSSSSSSSSSSS..";
const EYES_CLOSED = ".sSHHHSSSSHHHSs.";

export const SPRITE_W = 16;
export const SPRITE_H = SPRITE.length;

export const FISH = [".TTTT.T", "TeYYYTT", ".TTTT.T"];
export const FISH_COLORS = { T: "#6fa8b5", Y: "#e3c04d", e: "#1b2b30" };

export function frame({ blink = false, brows = false } = {}) {
  const rows = SPRITE.slice();
  if (brows) {
    rows[3] = FOREHEAD_RAISED;
    rows[4] = BROWS_RAISED;
  }
  if (blink) rows[5] = EYES_CLOSED;
  return rows;
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

/** A living Ramanan on a <canvas>: blinks, raises his brows, dances. */
export class Ramanan {
  constructor(canvas, { scale = 4, dancing = false } = {}) {
    this.canvas = canvas;
    this.scale = scale;
    this.dancing = dancing;
    this.level = 0.5;
    canvas.width = SPRITE_W * scale;
    canvas.height = SPRITE_H * scale;
    canvas.style.transformOrigin = "50% 100%";
    this.ctx = canvas.getContext("2d");
    const now = performance.now();
    this.nextBlink = now + 1500;
    this.nextBrows = now + 4000;
    this.last = "";
    this.tick = this.tick.bind(this);
    requestAnimationFrame(this.tick);
  }

  setDancing(on) {
    this.dancing = on;
    if (!on) this.canvas.style.transform = "";
  }

  tick(now) {
    if (now > this.nextBlink + 140) this.nextBlink = now + 2500 + Math.random() * 3000;
    if (now > this.nextBrows + 600) this.nextBrows = now + 6000 + Math.random() * 6000;
    let blink = this.nextBlink <= now;
    let brows = this.nextBrows <= now;

    if (this.dancing && !reducedMotion.matches) {
      const beat = (now / 1000) * (2.2 + this.level * 2);
      const bob = -Math.abs(Math.sin(beat * Math.PI)) * (1.5 + this.level * 3) * (this.scale / 2);
      const tilt = Math.sin((beat * Math.PI) / 2) * 5;
      brows = brows || Math.sin(beat * Math.PI) > 0.6;
      this.canvas.style.transform = `translateY(${bob.toFixed(1)}px) rotate(${tilt.toFixed(1)}deg)`;
    }

    const key = `${blink}${brows}`;
    if (key !== this.last) {
      this.last = key;
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      drawPixels(this.ctx, frame({ blink, brows }), PALETTE, this.scale);
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
