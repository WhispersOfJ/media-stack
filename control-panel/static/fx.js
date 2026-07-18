/* Atmosphere layer: a single static grain texture painted once onto a
   fixed canvas, behind everything — the faint noise you'd see on a
   broadcast monitor's phosphor, not a continuous animation. No rAF loop:
   drawn once and left alone, so there's no ongoing CPU/GPU cost and
   nothing to silence under prefers-reduced-motion beyond hiding the
   canvas outright (handled in CSS). */

(function () {
  const canvas = document.getElementById("fx-canvas");
  if (!canvas) return;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const ctx = canvas.getContext("2d");

  function paint() {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    const w = window.innerWidth;
    const h = window.innerHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";

    const imageData = ctx.createImageData(canvas.width, canvas.height);
    const data = imageData.data;
    for (let i = 0; i < data.length; i += 4) {
      const v = Math.random() * 255;
      data[i] = v;
      data[i + 1] = v;
      data[i + 2] = v;
      data[i + 3] = Math.random() * 14; // very faint
    }
    ctx.putImageData(imageData, 0, 0);
  }

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(paint, 200);
  });
  paint();
})();
