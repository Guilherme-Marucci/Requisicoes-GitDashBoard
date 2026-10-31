/* Aba Projetos GitHub: sincronização, métricas, gráficos e log. Todo texto dinâmico entra via textContent. */
(function () {
  "use strict";
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  var form = document.getElementById("gh-form"), input = document.getElementById("gh-input");
  var submit = document.getElementById("gh-submit"), status = document.getElementById("gh-status");
  var dash = document.getElementById("gh-dashboard"), logsTodos = document.getElementById("logs-todos");
  var ultimo = null;

  function el(tag, text, cls) { var e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
  function msg(texto, tipo) { status.hidden = !texto; status.textContent = texto || ""; status.className = "flash flash--" + (tipo || "info"); }
  function fmt(d) { if (!d) return "—"; var x = new Date(d); return isNaN(x) ? "—" : x.toLocaleString("pt-BR"); }
  function api(url, opts) {
    opts = opts || {}; opts.credentials = "same-origin"; opts.headers = Object.assign({ "X-CSRF-Token": csrf }, opts.headers || {});
    return fetch(url, opts).then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; }); });
  }

  function metric(label, value) { var d = el("div", undefined, "metric"); d.append(el("span", label), el("strong", String(value))); return d; }

  function render(resumo, projetos) {
    if (!resumo) { dash.hidden = true; return; }
    ultimo = { resumo: resumo, projetos: projetos };
    dash.hidden = false;
    var t = resumo.totais, m = document.getElementById("gh-metrics");
    m.replaceChildren(metric("Repositórios", t.repos), metric("Estrelas", t.estrelas), metric("Forks", t.forks),
      metric("Issues abertas", t.issues), metric("Commits (30 dias)", t.commits));
    Charts.line(document.getElementById("chart-atividade"), resumo.atividade.map(function (a) { return a.data; }), resumo.atividade.map(function (a) { return a.commits; }));
    Charts.doughnut(document.getElementById("chart-linguagens"), resumo.linguagens.map(function (l) { return l.nome; }),
      resumo.linguagens.map(function (l) { return l.repos; }), document.getElementById("legend-linguagens"));
    Charts.bar(document.getElementById("chart-estrelas"), resumo.top_repos.map(function (r) { return r.nome; }), resumo.top_repos.map(function (r) { return r.estrelas; }));
    Charts.bar(document.getElementById("chart-forks"), resumo.top_repos.map(function (r) { return r.nome; }), resumo.top_repos.map(function (r) { return r.forks; }), "#ff2bd6");
    var tbody = document.querySelector("#gh-table tbody"); tbody.replaceChildren();
    (projetos || []).forEach(function (p) {
      var tr = document.createElement("tr"), a = el("a", p.nome, "repo-link");
      a.href = /^https:\/\/github\.com\//.test(p.url) ? p.url : "#"; a.target = "_blank"; a.rel = "noopener noreferrer";
      var c0 = el("td"); c0.appendChild(a);
      if (p.descricao) c0.appendChild(el("small", p.descricao, "muted block"));
      tr.append(c0, el("td", p.linguagem || "—"), el("td", p.estrelas), el("td", p.forks), el("td", p.issues_abertas), el("td", p.commits_recentes), el("td", fmt(p.ultimo_push)));
      tbody.appendChild(tr);
    });
  }

  function carregarLogs() {
    var escopo = logsTodos && logsTodos.checked ? "?escopo=todos" : "";
    api("/api/github/logs" + escopo).then(function (r) {
      var tbody = document.querySelector("#log-table tbody"); tbody.replaceChildren();
      if (!r.ok) return;
      if (!r.body.logs.length) { var tr0 = document.createElement("tr"), td0 = el("td", "Nenhuma sincronização registrada.", "empty"); td0.colSpan = 10; tr0.appendChild(td0); tbody.appendChild(tr0); return; }
      r.body.logs.forEach(function (l) {
        var tr = document.createElement("tr");
        tr.append(el("td", fmt(l.criado_em)), el("td", l.github_username), el("td", l.resultado, "res--" + l.resultado),
          el("td", l.total_repos), el("td", l.total_estrelas), el("td", l.total_forks), el("td", l.total_commits),
          el("td", l.rate_limit_restante === null ? "—" : l.rate_limit_restante), el("td", l.mensagem || "—"));
        if (logsTodos) tr.appendChild(el("td", l.usuario_nome || "—"));
        tbody.appendChild(tr);
      });
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var entrada = input.value.trim();
    if (!entrada) { msg("Informe o link ou o username do GitHub.", "erro"); return; }
    submit.disabled = true; msg("Sincronizando com a API do GitHub…", "info");
    api("/api/github/sincronizar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ entrada: entrada }) })
      .then(function (r) {
        if (r.ok) {
          var restante = r.body.rate_limit_restante;
          msg("Sincronizado: " + r.body.resumo.totais.repos + " repositórios de @" + r.body.username +
              (restante !== null && restante !== undefined ? " · limite restante da API: " + restante : "") + ". Log registrado.", "ok");
          render(r.body.resumo, r.body.projetos);
        } else {
          msg((r.body.erro && r.body.erro.mensagem) || "Falha ao sincronizar.", "erro");
        }
        carregarLogs();
      }).catch(function () { msg("Falha de rede ao contatar o painel.", "erro"); })
      .then(function () { submit.disabled = false; });
  });

  if (logsTodos) logsTodos.addEventListener("change", carregarLogs);
  window.addEventListener("painel:tema", function () { if (ultimo) render(ultimo.resumo, ultimo.projetos); });
  window.addEventListener("resize", function () { if (ultimo) render(ultimo.resumo, ultimo.projetos); });

  // Estado persistido (sem chamar o GitHub)
  if (input.value.trim()) {
    api("/api/github/projetos?username=" + encodeURIComponent(input.value.trim())).then(function (r) {
      if (r.ok && r.body.resumo) { render(r.body.resumo, r.body.projetos); msg("Exibindo a última sincronização (" + fmt(r.body.atualizado_em) + ").", "info"); }
    });
  }
  carregarLogs();
})();

