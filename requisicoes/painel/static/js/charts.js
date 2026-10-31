/* Gráficos em canvas (sem dependências): barras, linha e rosca. Cores vêm das variáveis CSS do tema ativo. */
(function (global) {
  "use strict";

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function palette() {
    var a = css("--accent"), b = css("--accent-2");
    return [a, b, "#39ff88", "#ffd23f", "#ff7a3d", "#3d8bff", "#b565ff", "#8b8fb0"];
  }
  function setup(canvas) {
    var dpr = window.devicePixelRatio || 1, w = canvas.clientWidth, h = Number(canvas.getAttribute("height")) || 220;
    canvas.width = w * dpr; canvas.height = h * dpr;
    var ctx = canvas.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    ctx.font = "11px " + (css("--mono") || "monospace");
    return { ctx: ctx, w: w, h: h };
  }
  function empty(s, msg) {
    s.ctx.fillStyle = css("--muted"); s.ctx.textAlign = "center";
    s.ctx.fillText(msg || "Sem dados", s.w / 2, s.h / 2);
  }
  function niceMax(v) { if (v <= 5) return 5; var p = Math.pow(10, Math.floor(Math.log10(v))); return Math.ceil(v / p) * p; }

  function axes(s, max, pad) {
    var ctx = s.ctx, steps = 4;
    ctx.strokeStyle = css("--border"); ctx.fillStyle = css("--muted"); ctx.textAlign = "right"; ctx.lineWidth = 1;
    for (var i = 0; i <= steps; i++) {
      var y = pad.t + (s.h - pad.t - pad.b) * (1 - i / steps);
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(s.w - pad.r, y); ctx.stroke();
      ctx.fillText(String(Math.round(max * i / steps)), pad.l - 6, y + 3);
    }
  }

  function bar(canvas, labels, values, color) {
    var s = setup(canvas), ctx = s.ctx;
    if (!values.length || !values.some(function (v) { return v > 0; })) return empty(s);
    var pad = { l: 36, r: 8, t: 10, b: 44 }, max = niceMax(Math.max.apply(null, values)), n = values.length;
    axes(s, max, pad);
    var bw = (s.w - pad.l - pad.r) / n, col = color || css("--accent");
    values.forEach(function (v, i) {
      var bh = (s.h - pad.t - pad.b) * v / max, x = pad.l + i * bw + bw * 0.18, y = s.h - pad.b - bh;
      ctx.shadowColor = col; ctx.shadowBlur = 10; ctx.fillStyle = col;
      ctx.fillRect(x, y, bw * 0.64, bh); ctx.shadowBlur = 0;
      ctx.save(); ctx.translate(x + bw * 0.32, s.h - pad.b + 8); ctx.rotate(Math.PI / 6);
      ctx.fillStyle = css("--muted"); ctx.textAlign = "left";
      ctx.fillText(String(labels[i]).slice(0, 14), 0, 4); ctx.restore();
    });
  }

  function line(canvas, labels, values) {
    var s = setup(canvas), ctx = s.ctx;
    if (!values.length || !values.some(function (v) { return v > 0; })) return empty(s, "Sem commits públicos no período");
    var pad = { l: 36, r: 12, t: 10, b: 26 }, max = niceMax(Math.max.apply(null, values)), n = values.length;
    axes(s, max, pad);
    var step = (s.w - pad.l - pad.r) / Math.max(1, n - 1), col = css("--accent");
    function pt(i) { return [pad.l + i * step, s.h - pad.b - (s.h - pad.t - pad.b) * values[i] / max]; }
    var grad = ctx.createLinearGradient(0, pad.t, 0, s.h - pad.b);
    grad.addColorStop(0, col + "55"); grad.addColorStop(1, col + "00");
    ctx.beginPath(); ctx.moveTo(pad.l, s.h - pad.b);
    values.forEach(function (_, i) { var p = pt(i); ctx.lineTo(p[0], p[1]); });
    ctx.lineTo(pad.l + (n - 1) * step, s.h - pad.b); ctx.closePath(); ctx.fillStyle = grad; ctx.fill();
    ctx.beginPath(); values.forEach(function (_, i) { var p = pt(i); i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); });
    ctx.shadowColor = col; ctx.shadowBlur = 10; ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.stroke(); ctx.shadowBlur = 0;
    ctx.fillStyle = css("--muted"); ctx.textAlign = "center";
    [0, Math.floor(n / 2), n - 1].forEach(function (i) { ctx.fillText(String(labels[i]).slice(5), pad.l + i * step, s.h - 8); });
  }

  function doughnut(canvas, labels, values, legend) {
    var s = setup(canvas), ctx = s.ctx, total = values.reduce(function (a, b) { return a + b; }, 0);
    if (!total) return empty(s);
    var cx = s.w / 2, cy = s.h / 2, r = Math.min(cx, cy) - 10, colors = palette(), ang = -Math.PI / 2;
    values.forEach(function (v, i) {
      var a2 = ang + (v / total) * Math.PI * 2;
      ctx.beginPath(); ctx.arc(cx, cy, r, ang, a2); ctx.arc(cx, cy, r * 0.62, a2, ang, true); ctx.closePath();
      ctx.shadowColor = colors[i % colors.length]; ctx.shadowBlur = 8; ctx.fillStyle = colors[i % colors.length]; ctx.fill();
      ang = a2;
    });
    ctx.shadowBlur = 0; ctx.fillStyle = css("--text"); ctx.textAlign = "center"; ctx.font = "bold 20px " + (css("--mono") || "monospace");
    ctx.fillText(String(total), cx, cy + 4);
    if (legend) {
      legend.replaceChildren();
      labels.forEach(function (l, i) {
        var li = document.createElement("li"), sw = document.createElement("i");
        sw.style.background = colors[i % colors.length];
        li.append(sw, document.createTextNode(l + " (" + values[i] + ")")); legend.appendChild(li);
      });
    }
  }

  global.Charts = { bar: bar, line: line, doughnut: doughnut };
})(window);

