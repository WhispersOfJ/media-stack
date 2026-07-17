/* Atmosphere layer: rising embers on a fixed canvas, behind everything.
   Self-contained, no dependency on app.js. Respects reduced-motion by
   simply never starting the animation loop (the canvas itself is also
   display:none'd via CSS in that case). */

(function () {
  const canvas = document.getElementById("fx-canvas");
  if (!canvas) return;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const ctx = canvas.getContext("2d");
  let w, h, dpr;
  let embers = [];

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = window.innerWidth;
    h = window.innerHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function spawn() {
    const hue = 8 + Math.random() * 30; // red through amber
    return {
      x: Math.random() * w,
      y: h + Math.random() * 40,
      r: 0.6 + Math.random() * 1.8,
      vy: 0.25 + Math.random() * 0.55,
      vx: (Math.random() - 0.5) * 0.35,
      drift: Math.random() * Math.PI * 2,
      driftSpeed: 0.004 + Math.random() * 0.008,
      life: 0,
      maxLife: 400 + Math.random() * 500,
      hue,
      baseAlpha: 0.25 + Math.random() * 0.45,
    };
  }

  const TARGET_COUNT = 70;

  function init() {
    resize();
    embers = Array.from({ length: TARGET_COUNT }, () => {
      const e = spawn();
      e.y = Math.random() * h;
      e.life = Math.random() * e.maxLife;
      return e;
    });
  }

  function step() {
    ctx.clearRect(0, 0, w, h);
    for (const e of embers) {
      e.life += 1;
      e.drift += e.driftSpeed;
      e.y -= e.vy;
      e.x += e.vx + Math.sin(e.drift) * 0.3;

      const lifeFrac = e.life / e.maxLife;
      const fade = lifeFrac < 0.15 ? lifeFrac / 0.15 : lifeFrac > 0.8 ? (1 - lifeFrac) / 0.2 : 1;
      const alpha = Math.max(0, e.baseAlpha * fade);

      const grad = ctx.createRadialGradient(e.x, e.y, 0, e.x, e.y, e.r * 5);
      grad.addColorStop(0, `hsla(${e.hue}, 100%, 60%, ${alpha})`);
      grad.addColorStop(1, `hsla(${e.hue}, 100%, 50%, 0)`);
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(e.x, e.y, e.r * 5, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = `hsla(${e.hue}, 100%, 75%, ${alpha})`;
      ctx.beginPath();
      ctx.arc(e.x, e.y, e.r, 0, Math.PI * 2);
      ctx.fill();

      if (e.y < -20 || e.life > e.maxLife) Object.assign(e, spawn());
    }
    requestAnimationFrame(step);
  }

  window.addEventListener("resize", resize);
  init();
  requestAnimationFrame(step);
})();
