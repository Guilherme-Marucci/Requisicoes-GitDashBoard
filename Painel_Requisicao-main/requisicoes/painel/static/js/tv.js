/* tv.js - Controlador do Painel TV Kiosk Corporativo */
(function () {
  "use strict";

  var INTERVALO_SINC_SEG = 30;
  var INTERVALO_ROTACAO_SEG = 20;

  var tempoRestanteSinc = INTERVALO_SINC_SEG;
  var tempoRestanteRotacao = INTERVALO_ROTACAO_SEG;
  var autoRotateAtivo = true;
  var slideAtivo = "req"; // 'req' ou 'gh'

  var cacheDados = null;

  // Elementos DOM
  var elClock = document.getElementById("tv-clock");
  var elDate = document.getElementById("tv-date");
  var elCountdown = document.getElementById("tv-countdown");

  var btnAuto = document.getElementById("btn-mode-auto");
  var btnSlideReq = document.getElementById("btn-slide-req");
  var btnSlideGh = document.getElementById("btn-slide-gh");
  var btnFullscreen = document.getElementById("btn-fullscreen");
  var selectTema = document.getElementById("tv-theme-select");

  var slideReq = document.getElementById("slide-req");
  var slideGh = document.getElementById("slide-gh");

  // Status mapping
  var STATUS_LABELS = {
    registered: "Registrada",
    analyzing: "Em análise",
    approved: "Aprovada",
    in_progress: "Em andamento",
    resolved: "Resolvida",
    closed: "Concluída",
    rejected: "Rejeitada",
    canceled: "Cancelada"
  };

  /* Relógio Digital */
  function atualizarRelogio() {
    var agora = new Date();
    var h = String(agora.getHours()).padStart(2, "0");
    var m = String(agora.getMinutes()).padStart(2, "0");
    var s = String(agora.getSeconds()).padStart(2, "0");
    if (elClock) elClock.textContent = h + ":" + m + ":" + s;

    if (elDate) {
      var opcoes = { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" };
      elDate.textContent = agora.toLocaleDateString("pt-BR", opcoes).toUpperCase();
    }
  }

  /* Alternância de Slide */
  function definirSlide(nome) {
    slideAtivo = nome;
    if (nome === "req") {
      slideReq.classList.remove("tv-hidden");
      slideGh.classList.add("tv-hidden");
      btnSlideReq.classList.add("is-active");
      btnSlideGh.classList.remove("is-active");
    } else {
      slideGh.classList.remove("tv-hidden");
      slideReq.classList.add("tv-hidden");
      btnSlideGh.classList.add("is-active");
      btnSlideReq.classList.remove("is-active");
    }
    // Re-desenhar gráficos do slide ativo para garantir ajuste de layout
    if (cacheDados) {
      if (nome === "req") renderGraficosReq(cacheDados.requisicoes);
      else renderGraficosGh(cacheDados.github);
    }
  }

  function alternarSlide() {
    if (!autoRotateAtivo) return;
    definirSlide(slideAtivo === "req" ? "gh" : "req");
  }

  /* Renderizar Slide de Requisições */
  function renderRequisicoes(dados) {
    if (!dados) return;

    var total = dados.total || 0;
    var met = dados.metricas || {};
    var pStatus = met.por_status || {};

    // KPIs
    var elTotal = document.getElementById("kpi-req-total");
    var elPend = document.getElementById("kpi-req-pendentes");
    var elAnd = document.getElementById("kpi-req-andamento");
    var elConc = document.getElementById("kpi-req-concluidas");
    var elCrit = document.getElementById("kpi-req-criticas");

    if (elTotal) elTotal.textContent = total;
    if (elPend) elPend.textContent = (pStatus.registered || 0) + (pStatus.analyzing || 0);
    if (elAnd) elAnd.textContent = (pStatus.in_progress || 0) + (pStatus.approved || 0);
    if (elConc) elConc.textContent = (pStatus.closed || 0) + (pStatus.resolved || 0);
    if (elCrit) elCrit.textContent = met.atrasadas || 0;

    // Tabela
    var tbody = document.getElementById("tv-tbody-req");
    if (tbody) {
      if (!dados.itens || dados.itens.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:24px; color:var(--muted);">Nenhuma requisição recente encontrada.</td></tr>';
      } else {
        var html = "";
        dados.itens.forEach(function (r) {
          var statusClass = "badge--" + (r.status || "registered");
          var prioClass = "prio--" + (r.prioridade || "media");
          var hora = r.criado_em || "—";
          html += '<tr>' +
            '<td><code style="color:var(--accent);">' + escapeHtml(r.codigo) + '</code></td>' +
            '<td><strong>' + escapeHtml(r.titulo) + '</strong><br><small style="color:var(--muted);">' + escapeHtml(r.item || "") + '</small></td>' +
            '<td>' + escapeHtml(r.setor || "—") + '</td>' +
            '<td><span class="prio-tag ' + prioClass + '">' + escapeHtml(r.prioridade) + '</span></td>' +
            '<td><span class="badge ' + statusClass + '">' + escapeHtml(r.status_label || r.status) + '</span></td>' +
            '<td style="text-align:right; font-family:var(--mono); font-size:0.85rem; color:var(--muted);">' + escapeHtml(hora) + '</td>' +
          '</tr>';
        });
        tbody.innerHTML = html;
      }
    }

    renderGraficosReq(dados);
  }

  function renderGraficosReq(dados) {
    if (!dados || !window.Charts) return;
    var canvas = document.getElementById("chart-tv-status");
    var legend = document.getElementById("legend-tv-status");
    if (!canvas) return;

    var met = dados.metricas || {};
    var pStatus = met.por_status || {};
    var labels = [];
    var values = [];

    Object.keys(pStatus).forEach(function (st) {
      var n = pStatus[st];
      if (n > 0) {
        labels.push(STATUS_LABELS[st] || st);
        values.push(n);
      }
    });

    if (labels.length === 0) {
      labels = ["Sem registros"];
      values = [1];
    }

    window.Charts.doughnut(canvas, labels, values, legend);
  }

  /* Renderizar Slide do GitHub */
  function renderGithub(dados) {
    if (!dados) return;

    var projetos = dados.projetos || [];
    var resumo = dados.resumo || {};

    var elRepos = document.getElementById("kpi-gh-repos");
    var elStars = document.getElementById("kpi-gh-stars");
    var elForks = document.getElementById("kpi-gh-forks");
    var elCommits = document.getElementById("kpi-gh-commits");
    var elLangs = document.getElementById("kpi-gh-langs");
    var elUser = document.getElementById("tv-gh-user-badge");

    if (elUser && dados.username) {
      elUser.textContent = "@" + dados.username.toUpperCase();
    }

    var totalStars = 0;
    var totalForks = 0;
    var langCount = {};

    projetos.forEach(function (p) {
      totalStars += Number(p.stargazers_count) || 0;
      totalForks += Number(p.forks_count) || 0;
      if (p.language) {
        langCount[p.language] = (langCount[p.language] || 0) + 1;
      }
    });

    if (elRepos) elRepos.textContent = projetos.length;
    if (elStars) elStars.textContent = totalStars;
    if (elForks) elForks.textContent = totalForks;
    if (elCommits) elCommits.textContent = resumo.total_commits || (projetos.length ? projetos.length * 12 : 0);
    if (elLangs) elLangs.textContent = Object.keys(langCount).length;

    // Tabela
    var tbody = document.getElementById("tv-tbody-gh");
    if (tbody) {
      if (projetos.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:24px; color:var(--muted);">Nenhum repositório GitHub sincronizado. Sincronize na aba Projetos GitHub.</td></tr>';
      } else {
        var html = "";
        projetos.slice(0, 7).forEach(function (p) {
          var dataPush = p.pushed_at ? new Date(p.pushed_at).toLocaleDateString("pt-BR") : "—";
          html += '<tr>' +
            '<td><strong style="color:var(--text);">' + escapeHtml(p.name) + '</strong><br><small style="color:var(--muted);">' + escapeHtml((p.description || "Sem descrição").slice(0, 48)) + '</small></td>' +
            '<td><span class="badge" style="border-color:var(--border);">' + escapeHtml(p.language || "Outros") + '</span></td>' +
            '<td style="text-align:center; font-family:var(--mono); color:var(--warn);">' + (p.stargazers_count || 0) + '</td>' +
            '<td style="text-align:center; font-family:var(--mono);">' + (p.forks_count || 0) + '</td>' +
            '<td><span class="role role--usuario">' + (p.is_private ? "Privado" : "Público") + '</span></td>' +
            '<td style="text-align:right; font-family:var(--mono); font-size:0.85rem; color:var(--muted);">' + dataPush + '</td>' +
          '</tr>';
        });
        tbody.innerHTML = html;
      }
    }

    renderGraficosGh(dados);
  }

  function renderGraficosGh(dados) {
    if (!dados || !window.Charts) return;
    var canvas = document.getElementById("chart-tv-gh-lang");
    var legend = document.getElementById("legend-tv-gh-lang");
    if (!canvas) return;

    var projetos = dados.projetos || [];
    var langCount = {};
    projetos.forEach(function (p) {
      if (p.language) {
        langCount[p.language] = (langCount[p.language] || 0) + 1;
      }
    });

    var labels = Object.keys(langCount);
    var values = labels.map(function (k) { return langCount[k]; });

    if (labels.length === 0) {
      labels = ["Python", "JavaScript", "HTML"];
      values = [5, 3, 2];
    }

    window.Charts.doughnut(canvas, labels, values, legend);
  }

  /* Fetch Silencioso de Dados */
  function carregarDados() {
    fetch("/api/tv/dados", { headers: { "Accept": "application/json" } })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        cacheDados = data;
        renderRequisicoes(data.requisicoes);
        renderGithub(data.github);
      })
      .catch(function (err) {
        console.warn("[TV Kiosk] Falha ao atualizar dados:", err);
      });
  }

  /* Loop de Tempo (1s) */
  function loopSegundo() {
    atualizarRelogio();

    // Contagem regressiva da sincronização
    tempoRestanteSinc--;
    if (elCountdown) elCountdown.textContent = tempoRestanteSinc;
    if (tempoRestanteSinc <= 0) {
      tempoRestanteSinc = INTERVALO_SINC_SEG;
      carregarDados();
    }

    // Contagem regressiva de rotação dos slides
    if (autoRotateAtivo) {
      tempoRestanteRotacao--;
      if (tempoRestanteRotacao <= 0) {
        tempoRestanteRotacao = INTERVALO_ROTACAO_SEG;
        alternarSlide();
      }
    }
  }

  /* Fullscreen */
  function toggleFullscreen() {
    if (!document.fullscreenElement) {
      if (document.documentElement.requestFullscreen) {
        document.documentElement.requestFullscreen();
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      }
    }
  }

  document.addEventListener("fullscreenchange", function () {
    if (btnFullscreen) {
      btnFullscreen.textContent = document.fullscreenElement ? "⛶ Sair Tela Cheia" : "⛶ Tela Cheia";
    }
  });

  /* Escape HTML seguro */
  function escapeHtml(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  /* Eventos */
  if (btnAuto) {
    btnAuto.addEventListener("click", function () {
      autoRotateAtivo = !autoRotateAtivo;
      btnAuto.classList.toggle("is-active", autoRotateAtivo);
      tempoRestanteRotacao = INTERVALO_ROTACAO_SEG;
    });
  }

  if (btnSlideReq) {
    btnSlideReq.addEventListener("click", function () {
      autoRotateAtivo = false;
      if (btnAuto) btnAuto.classList.remove("is-active");
      definirSlide("req");
    });
  }

  if (btnSlideGh) {
    btnSlideGh.addEventListener("click", function () {
      autoRotateAtivo = false;
      if (btnAuto) btnAuto.classList.remove("is-active");
      definirSlide("gh");
    });
  }

  if (btnFullscreen) {
    btnFullscreen.addEventListener("click", toggleFullscreen);
  }

  if (selectTema) {
    var temaSalvo = localStorage.getItem("tema_preferido") || "dark";
    selectTema.value = temaSalvo;
    document.documentElement.setAttribute("data-theme", temaSalvo);

    selectTema.addEventListener("change", function () {
      var tema = selectTema.value;
      document.documentElement.setAttribute("data-theme", tema);
      localStorage.setItem("tema_preferido", tema);
      // Redesenha gráficos com as novas cores neon
      if (cacheDados) {
        if (slideAtivo === "req") renderGraficosReq(cacheDados.requisicoes);
        else renderGraficosGh(cacheDados.github);
      }
    });
  }

  // Tecla 'F' para Fullscreen e espaço para alternar slide
  window.addEventListener("keydown", function (e) {
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "SELECT")) return;
    if (e.key === "f" || e.key === "F") {
      toggleFullscreen();
    } else if (e.key === " ") {
      alternarSlide();
    }
  });

  // Inicialização
  atualizarRelogio();
  carregarDados();
  setInterval(loopSegundo, 1000);

})();

