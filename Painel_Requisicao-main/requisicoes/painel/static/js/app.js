/* Comportamentos globais: menu móvel, barras, confirmações e seletor de temas (CSP: sem scripts inline). */
(function () {
  "use strict";
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

  // Larguras das barras vêm de data-pct (CSSOM é permitido pela CSP; atributo style inline não).
  document.querySelectorAll(".bar__fill[data-pct]").forEach(function (el) {
    requestAnimationFrame(function () { el.style.width = Math.min(100, Number(el.dataset.pct) || 0) + "%"; });
  });

  // Menu móvel
  var btn = document.getElementById("menu-btn"), sidebar = document.getElementById("sidebar");
  if (btn && sidebar) {
    btn.addEventListener("click", function () {
      var open = sidebar.classList.toggle("is-open");
      btn.setAttribute("aria-expanded", String(open));
    });
  }

  // Confirmação de ações destrutivas
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) { if (!window.confirm(form.dataset.confirm)) e.preventDefault(); });
  });

  // Seletor de temas: aplica na hora, salva no perfil (MySQL) e em localStorage como reserva.
  var picker = document.getElementById("theme-picker");
  if (picker) {
    var feedback = document.getElementById("theme-feedback");
    picker.addEventListener("click", function (e) {
      var chip = e.target.closest("[data-theme-choice]");
      if (!chip) return;
      var tema = chip.dataset.themeChoice;
      document.documentElement.setAttribute("data-theme", tema);
      picker.querySelectorAll("[data-theme-choice]").forEach(function (c) {
        var ativo = c === chip;
        c.classList.toggle("is-active", ativo);
        c.setAttribute("aria-checked", String(ativo));
      });
      try { localStorage.setItem("painel-tema", tema); } catch (err) { /* opcional */ }
      window.dispatchEvent(new CustomEvent("painel:tema"));
      fetch("/api/preferencias/tema", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ tema: tema })
      }).then(function (r) {
        feedback.textContent = r.ok ? "Tema \"" + tema + "\" salvo no seu perfil." : "Tema aplicado, mas não foi possível salvar no perfil.";
      }).catch(function () { feedback.textContent = "Tema aplicado, mas não foi possível salvar no perfil."; });
    });
  }
})();

