import { FishTank, Ramanan } from "./sprite.js";

const REPO = "abilbiju/RAMANAN-The-Windows-Notch-Agent";
const API = `https://api.github.com/repos/${REPO}`;

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/* ---------------- sprites & fish ---------------- */

$$(".brand-sprite").forEach((c) => new Ramanan(c, { scale: 2 }));
$$(".tray-sprite").forEach((c) => new Ramanan(c, { scale: 2 }));
const cardSprite = new Ramanan($(".card-sprite"), { scale: 2, dancing: true });
cardSprite.level = 0.3;
new Ramanan($(".idle-sprite"), { scale: 2 });
const musicSprite = new Ramanan($(".music-sprite"), { scale: 2, dancing: true });
musicSprite.level = 0.7;
const meetSprite = new Ramanan($(".meet-sprite"), { scale: 12, wide: true });
const finalSprite = new Ramanan($(".final-sprite"), { scale: 6, dancing: true });
finalSprite.level = 0.4;

new FishTank($(".sea"), { count: 10, scale: 3, alpha: 0.55, speed: 0.6 });
new FishTank($(".wall-fish"), { count: 6, scale: 3, alpha: 0.85 });
new FishTank($(".nv-fish"), { count: 3, scale: 2, bubbles: true });
new FishTank($(".aq-fish"), { count: 7, scale: 5 });

const dance = $("#dance");
dance.addEventListener("click", () => {
  const on = !meetSprite.dancing;
  meetSprite.level = 0.8;
  meetSprite.setDancing(on);
  dance.textContent = on ? "Okay, that's enough 🛑" : "Make him dance 🕺";
});

/* ---------------- scale the demo stage to fit ---------------- */

const wrap = $(".stage-wrap");
new ResizeObserver(() => wrap.style.setProperty("--s", Math.min(1, wrap.clientWidth / 960))).observe(wrap);

/* ---------------- interactive notch ---------------- */

const notch = $(".notch");
const hud = {
  icon: $(".hud-icon"), title: $(".hud-title"), sub: $(".hud-sub"),
  bar: $(".hud-bar"), fill: $(".hud-bar i"), value: $(".hud-value"),
};
const svg = (d) => `<svg viewBox="0 0 24 24">${d}</svg>`;

const STATES = {
  idle: { view: "idle", ms: 3400 },
  music: { view: "music", ms: 3600 },
  expanded: { view: "expanded", ms: 5600 },
  volume: {
    view: "hud", ms: 2600,
    icon: svg('<path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M19 5a10 10 0 0 1 0 14"/>'),
    title: "Volume", sub: "Speakers (Realtek Audio)", bar: 0.42, to: 0.64, value: "64",
  },
  charging: {
    view: "hud", ms: 3000, icon: '<span class="batt-ic fill"><i></i></span>',
    title: "Charging", sub: "", bar: 0.82, color: "var(--green)", value: "82%", valueColor: "var(--green)",
  },
  camera: {
    view: "hud", ms: 2800, color: "var(--green)",
    icon: `<span style="color:var(--green)">${svg('<path d="m22 8-6 4 6 4V8z"/><rect x="2" y="6" width="14" height="12" rx="2"/>')}</span>`,
    title: "Camera in use", sub: "Microsoft Teams", bar: null, value: "●", valueColor: "var(--green)",
  },
  download: {
    view: "hud", ms: 3200,
    icon: `<span style="color:var(--blue)">${svg('<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>')}</span>`,
    title: "ubuntu-24.04-desktop-amd64.iso", sub: "734.0 MB · 9.4 MB/s", bar: "indet", color: "var(--blue)", value: "",
  },
  caps: {
    view: "hud", ms: 2200, icon: '<span class="caps" style="color:var(--green)">⇪</span>',
    title: "Caps Lock", sub: "", bar: null, value: "On", valueColor: "var(--green)",
  },
};
const SEQUENCE = ["idle", "volume", "music", "expanded", "charging", "camera", "download", "caps"];

let current = "idle";
let seqIndex = 0;
let timer = 0;
let pausedUntil = 0;
let hovering = false;

function show(name) {
  const st = STATES[name];
  current = name;
  notch.dataset.view = st.view;
  if (name === "camera") notch.classList.add("cam");
  if (name === "download") notch.classList.remove("cam");
  if (st.view === "hud") {
    hud.icon.innerHTML = st.icon;
    hud.title.textContent = st.title;
    hud.sub.textContent = st.sub;
    hud.sub.hidden = !st.sub;
    hud.bar.hidden = st.bar === null;
    hud.bar.classList.toggle("indet", st.bar === "indet");
    hud.fill.style.background = st.color || "#f5f5f7";
    if (typeof st.bar === "number") {
      hud.fill.style.width = `${st.bar * 100}%`;
      if (st.to) setTimeout(() => current === name && (hud.fill.style.width = `${st.to * 100}%`), 450);
    } else {
      hud.fill.style.width = "";
    }
    hud.value.textContent = st.value;
    hud.value.style.color = st.valueColor || "";
  }
  $$(".chips button").forEach((b) => b.classList.toggle("on", b.dataset.show === name));
}

function loop() {
  clearTimeout(timer);
  if (!hovering && performance.now() >= pausedUntil) {
    seqIndex = (seqIndex + 1) % SEQUENCE.length;
    show(SEQUENCE[seqIndex]);
  }
  timer = setTimeout(loop, STATES[current].ms);
}

$$(".chips button").forEach((b) =>
  b.addEventListener("click", () => {
    show(b.dataset.show);
    seqIndex = Math.max(0, SEQUENCE.indexOf(b.dataset.show));
    pausedUntil = performance.now() + 9000;
    clearTimeout(timer);
    timer = setTimeout(loop, 9000);
  })
);

const expand = () => { hovering = true; show("expanded"); };
const collapse = () => {
  hovering = false;
  clearTimeout(timer);
  timer = setTimeout(() => { if (!hovering) { show("idle"); seqIndex = 0; timer = setTimeout(loop, 2500); } }, 500);
};
notch.addEventListener("mouseenter", expand);
notch.addEventListener("mouseleave", collapse);
notch.addEventListener("focus", expand);
notch.addEventListener("blur", collapse);
notch.addEventListener("click", () => (current === "expanded" ? collapse() : expand()));

// ?state=expanded (or music, volume, …) pins the demo to one state, handy for sharing.
const pinned = new URLSearchParams(location.search).get("state");
if (pinned && STATES[pinned]) {
  show(pinned);
  pausedUntil = Infinity;
} else {
  show("idle");
}
timer = setTimeout(loop, STATES[current].ms);

/* lyrics + progress in the expanded player and the feature card */
const LYRICS = ["Mothalaalee…", "changa chaka chakaa ♪", "changa chaka chakaa ♪♪", "…mothalaalee!"];
let line = 0;
let progress = 36;
setInterval(() => {
  line = (line + 1) % LYRICS.length;
  $$(".ex-lyric, .mp-lyric").forEach((el) => (el.textContent = LYRICS[line]));
  progress = progress >= 96 ? 8 : progress + 1.5;
  $(".ex-prog span i").style.width = `${progress}%`;
  const secs = Math.round((progress / 100) * 212);
  $(".ex-prog .t0").textContent = `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
}, 1600);

/* ---------------- page chrome ---------------- */

const nav = $(".nav");
const onScroll = () => nav.classList.toggle("scrolled", scrollY > 10);
addEventListener("scroll", onScroll, { passive: true });
onScroll();

const io = new IntersectionObserver(
  (entries) => entries.forEach((e) => e.isIntersecting && (e.target.classList.add("in"), io.unobserve(e.target))),
  { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
);
$$(".reveal").forEach((el) => io.observe(el));

$$(".copy").forEach((btn) =>
  btn.addEventListener("click", async () => {
    const text = $(btn.dataset.copy).innerText;
    try {
      await navigator.clipboard.writeText(text);
      btn.textContent = "Copied!";
    } catch {
      btn.textContent = "Select & copy";
    }
    setTimeout(() => (btn.textContent = "Copy"), 1800);
  })
);

if (!/Windows/i.test(navigator.userAgent)) {
  const note = $(".os-note");
  note.hidden = false;
  note.textContent = "Ramanan runs on Windows 10 & 11, so grab it on your Windows PC.";
}

/* ---------------- live GitHub numbers ---------------- */

const fmt = (n) => (n >= 1000 ? `${(n / 1000).toFixed(1).replace(/\.0$/, "")}k` : String(n));
const setStat = (key, value) => $$(`[data-stat="${key}"]`).forEach((el) => (el.textContent = value));

async function cached(url) {
  const key = `gh:${url}`;
  try {
    const hit = JSON.parse(sessionStorage.getItem(key) || "null");
    if (hit && Date.now() - hit.t < 10 * 60 * 1000) return hit.v;
  } catch { /* storage unavailable */ }
  const res = await fetch(url, { headers: { Accept: "application/vnd.github+json" } });
  if (!res.ok) throw new Error(res.status);
  const v = await res.json();
  try { sessionStorage.setItem(key, JSON.stringify({ t: Date.now(), v })); } catch { /* ignore */ }
  return v;
}

(async () => {
  try {
    const repo = await cached(API);
    setStat("stars", fmt(repo.stargazers_count));
    setStat("forks", fmt(repo.forks_count));
  } catch { setStat("stars", "★"); setStat("forks", "–"); }

  try {
    const rel = await cached(`${API}/releases/latest`);
    setStat("version", rel.tag_name);
    const date = new Date(rel.published_at);
    setStat("released", `Released ${date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`);
    const downloads = rel.assets.reduce((sum, a) => sum + a.download_count, 0);
    setStat("downloads", fmt(downloads));
    const exe = rel.assets.find((a) => /\.exe$/i.test(a.name));
    if (exe) {
      $$('[data-link="download"]').forEach((a) => (a.href = exe.browser_download_url));
      setStat("size", `${(exe.size / 1048576).toFixed(1)} MB`);
    }
  } catch { setStat("downloads", "–"); }

  try {
    const lic = await cached(`${API}/license`);
    $$('[data-link="license"]').forEach((a) => (a.href = lic.html_url));
  } catch { /* keep the default link */ }
})();
