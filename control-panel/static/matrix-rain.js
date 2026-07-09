/* Matrix-style falling code, rendered on a full-viewport canvas behind
   everything (#matrix-rain, z-index: -1 in style.css). Self-contained and
   independent of app.js on purpose - a bug here should never be able to
   break the actual dashboard functionality. */

(function () {
  const canvas = document.getElementById("matrix-rain");
  if (!canvas || !canvas.getContext) return;

  const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduceMotion) return; // CSS already hides the canvas; skip the render loop entirely too.

  const ctx = canvas.getContext("2d");
  const GLYPHS = "アカサタナハマヤラワ0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ:・.=*+-<>¦｜";
  const FONT_SIZE = 15;

  let columns = 0;
  let drops = [];
  let width = 0;
  let height = 0;
  let dpr = Math.min(window.devicePixelRatio || 1, 2);

  function resize() {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const newColumns = Math.ceil(width / FONT_SIZE);
    const prev = drops;
    drops = new Array(newColumns).fill(0).map((_, i) => (prev[i] !== undefined ? prev[i] : Math.floor((Math.random() * height) / FONT_SIZE)));
    columns = newColumns;
  }

  function frame() {
    // Translucent black wipe instead of a full clear - this is what
    // produces the fading-trail effect behind each falling glyph.
    ctx.fillStyle = "rgba(2, 6, 3, 0.08)";
    ctx.fillRect(0, 0, width, height);

    ctx.font = `${FONT_SIZE}px monospace`;
    ctx.textBaseline = "top";

    for (let i = 0; i < columns; i++) {
      const glyph = GLYPHS[(Math.random() * GLYPHS.length) | 0];
      const x = i * FONT_SIZE;
      const y = drops[i] * FONT_SIZE;

      // Leading glyph brighter/near-white-green, trail a dimmer phosphor
      // green - the same two-tone look the real effect uses.
      ctx.fillStyle = "#c9ffd6";
      ctx.fillText(glyph, x, y);
      ctx.fillStyle = "rgba(0, 255, 65, 0.75)";
      ctx.fillText(GLYPHS[(Math.random() * GLYPHS.length) | 0], x, y - FONT_SIZE);

      if (y > height && Math.random() > 0.975) {
        drops[i] = 0;
      } else {
        drops[i]++;
      }
    }
  }

  let rafId = null;
  let lastTick = 0;
  const FRAME_INTERVAL = 50; // ms - readable typing speed, not a strobe

  function loop(ts) {
    rafId = requestAnimationFrame(loop);
    if (ts - lastTick < FRAME_INTERVAL) return;
    lastTick = ts;
    frame();
  }

  function start() {
    if (rafId === null) rafId = requestAnimationFrame(loop);
  }

  function stop() {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  }

  // Pause entirely when the tab isn't visible - this dashboard is meant to
  // be left open, so an invisible tab burning CPU on a canvas nobody sees
  // is pure waste.
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
    else start();
  });

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(resize, 150);
  });

  resize();
  start();
})();
