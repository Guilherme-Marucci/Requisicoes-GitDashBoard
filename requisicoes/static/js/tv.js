/* Exibição autônoma do retrato: nenhum comando de coleta é enviado pelo navegador. */
(() => {
  const statuses =
    typeof module !== "undefined"
      ? require("./requisicoes-status.js")
      : requisicoesStatus;
  const SCREEN_MS = 90000,
    PAGE_MS = 15000,
    REFRESH_MS = 60000,
    PAGE_SIZE = 6;
  const screens = [
    {
      id: "tv-summary-screen",
      title: "Situações das requisições",
      kicker: "01 / VISÃO GERAL",
    },
    {
      id: "tv-table-screen",
      title: "Acompanhamento das requisições",
      kicker: "02 / DETALHAMENTO",
    },
    {
      id: "tv-chart-screen",
      title: "Gráfico de situações",
      kicker: "03 / DISTRIBUIÇÃO POR SITUAÇÃO",
    },
  ];
  const firstName = (name) =>
    typeof name === "string" ? name.trim().split(/\s+/u)[0] || "—" : "—";

  function validate(payload) {
    const meta = payload?.meta;
    if (
      meta?.schemaVersion !== 3 ||
      meta.source !== "erp" ||
      !Number.isFinite(Date.parse(meta.generatedAt)) ||
      typeof meta.lastAttemptOk !== "boolean" ||
      typeof meta.stale !== "boolean" ||
      !Number.isFinite(meta.maxAgeSeconds) ||
      meta.maxAgeSeconds <= 0 ||
      !Array.isArray(payload.requests)
    )
      throw new Error("Retrato incompatível");
    const ids = new Set();
    for (const row of payload.requests) {
      if (
        !row ||
        !["id", "code", "branch", "item", "description", "status"].every(
          (key) => typeof row[key] === "string" && row[key].trim(),
        ) ||
        !statuses.some((status) => status.key === row.status) ||
        ids.has(row.id) ||
        [
          "requester",
          "requesterName",
          "firstProduct",
          "sectorName",
          "sectorCode",
          "inclusionDate",
        ].some((key) => row[key] != null && typeof row[key] !== "string") ||
        (row.createdAt != null &&
          (typeof row.createdAt !== "string" ||
            !/(Z|[+-]\d{2}:\d{2})$/.test(row.createdAt) ||
            !Number.isFinite(Date.parse(row.createdAt))))
      ) {
        throw new Error("Registro incompatível");
      }
      ids.add(row.id);
    }
    return payload;
  }

  function counts(rows) {
    return statuses
      .filter((status) => status.key !== "unmapped" && status.key !== "released")
      .map((status) => ({
        ...status,
        count: rows.filter((row) => row.status === status.key).length,
      }));
  }

  function summary(rows) {
    const pending = rows.filter((row) => row.status === "pending").length;
    let latest = null;
    const candidates = rows.filter(
      (row) => Number.isFinite(Date.parse(row.createdAt || row.inclusionDate || row.reference))
    );
    if (candidates.length) {
      // Prioridade: data de cadastro/inclusão mais recente (DATINC / createdAt); desempate pelo maior código numérico
      latest = candidates.reduce((last, row) => {
        const timeRow = Date.parse(row.createdAt || row.inclusionDate || row.reference);
        const timeLast = Date.parse(last.createdAt || last.inclusionDate || last.reference);
        if (timeRow !== timeLast) {
          return timeRow > timeLast ? row : last;
        }
        return (Number(row.code) || 0) > (Number(last.code) || 0) ? row : last;
      });
    } else if (rows.length) {
      // Fallback: maior código numérico
      latest = rows.reduce((last, row) =>
        (Number(row.code) || 0) > (Number(last.code) || 0) ? row : last
      );
    }
    const unmapped = rows.filter((row) => row.status === "unmapped").length;
    return {
      pending,
      unmapped,
      latest,
      latestId: latest?.code ?? null,
      clear: pending === 0 && unmapped === 0,
    };
  }

  function formatLatestReq(latest) {
    if (!latest) return "Nenhuma requisição encontrada";
    const codigo = String(latest.code || "—").trim();
    const setor = (latest.sectorName || (latest.sector !== "unclassified" ? latest.sector : "") || "").trim();
    return setor ? `${codigo} — ${setor}` : codigo;
  }

  function formatLatestDate(latest) {
    if (!latest) return "";
    const rawDate = String(latest.inclusionDate || latest.createdAt || latest.reference || "");
    if (!rawDate) return "";
    const match = rawDate.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (match) {
      const [, y, m, d] = match;
      return `Data de cadastro: ${d}/${m}/${y}`;
    }
    if (Number.isFinite(Date.parse(rawDate))) {
      const formatted = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" }).format(new Date(rawDate));
      return `Data de cadastro: ${formatted}`;
    }
    return "";
  }

  function ordersSummary(orders) {
    const rows = Array.isArray(orders) ? orders : [];
    const pendingOrdersSet = new Set();
    let latest = null;

    for (const row of rows) {
      const orderNo = String(row.orderNumber || row.code || "").trim();
      if (
        orderNo &&
        orderNo !== "—" &&
        (row.status === "pending" || row.orderStatus === "pending")
      ) {
        pendingOrdersSet.add(orderNo);
      }
      if (row.status === "canceled" || row.status === "rejected") continue;

      if (!latest) {
        latest = row;
        continue;
      }
      const tsRow = Date.parse(row.inclusionDate || row.orderDate || row.updatedAt || "");
      const tsLast = Date.parse(latest.inclusionDate || latest.orderDate || latest.updatedAt || "");
      if (Number.isFinite(tsRow) && Number.isFinite(tsLast) && tsRow !== tsLast) {
        if (tsRow > tsLast) latest = row;
      } else if (Number.isFinite(tsRow) && !Number.isFinite(tsLast)) {
        latest = row;
      } else {
        const numRow = Number(orderNo) || 0;
        const numLast = Number(latest.orderNumber || latest.code) || 0;
        if (numRow > numLast) latest = row;
      }
    }

    const pending = pendingOrdersSet.size;
    return {
      pending,
      latest,
      clear: rows.length > 0 && pending === 0,
    };
  }

  function formatLatestOrder(latest) {
    if (!latest) return "Nenhum pedido encontrado";
    const numped = String(latest.orderNumber || latest.code || "—").trim();
    const codreq = String(latest.requisitionCode || "").trim();
    const supplier = String(latest.supplier || "").trim();
    const parts = [numped];
    if (codreq && codreq !== "—") parts.push(`Req. ${codreq}`);
    if (supplier && supplier !== "—" && supplier !== "Fornecedor não informado") {
      parts.push(supplier);
    }
    return parts.join(" — ");
  }

  function formatOrderInclusionDate(latest) {
    if (!latest) return "";
    const rawDate = String(latest.inclusionDate || latest.orderDate || "");
    if (!rawDate || rawDate === "—") return "";
    const match = rawDate.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2}))?/);
    if (match) {
      const [, y, m, d, hh, mm] = match;
      return hh !== undefined && mm !== undefined
        ? `Data de inclusão: ${d}/${m}/${y}, ${hh}:${mm}`
        : `Data de inclusão: ${d}/${m}/${y}`;
    }
    return "";
  }

  function sortTrackingRows(requests) {
    return [...requests].sort((a, b) => {
      const priority = (st) => {
        if (st === "pending") return 1;    // Situação 'P' (Pendente)
        if (st === "registered") return 2; // Situação 'D' (Cadastrada)
        return 3;                          // Demais situações
      };
      const pa = priority(a.status);
      const pb = priority(b.status);
      if (pa !== pb) return pa - pb;
      return (Number(b.code) || 0) - (Number(a.code) || 0);
    });
  }

  // Mantém tempos separados: troca de tela em 90 s e avanço das linhas em 15 s de tabela visível.
  function advanceScreen(state) {
    state.screen = (state.screen + 1) % screens.length;
    state.screenElapsed = 0;
    state.page = 0;
    state.pageElapsed = 0;
    return state;
  }

  function advance(state, elapsed) {
    let remaining = Math.max(0, elapsed);
    while (remaining > 0) {
      const step = Math.min(remaining, SCREEN_MS - state.screenElapsed);
      state.screenElapsed += step;
      if (state.screen === 1) {
        state.pageElapsed += step;
        state.page += Math.floor(state.pageElapsed / PAGE_MS);
        state.pageElapsed %= PAGE_MS;
      }
      remaining -= step;
      if (state.screenElapsed >= SCREEN_MS) {
        advanceScreen(state);
      }
    }
    return state;
  }
  if (typeof module !== "undefined") {
    module.exports = {
      firstName,
      validate,
      counts,
      summary,
      formatLatestReq,
      formatLatestDate,
      ordersSummary,
      formatLatestOrder,
      formatOrderInclusionDate,
      sortTrackingRows,
      advance,
      advanceScreen,
      SCREEN_MS,
      PAGE_MS,
      REFRESH_MS,
      PAGE_SIZE,
    };
    return;
  }

  const $ = (id) => document.getElementById(id);
  const state = { screen: 0, screenElapsed: 0, page: 0, pageElapsed: 0 };
  const progressFill = $("tv-progress-fill");
  const graphOnly = document.body.dataset.tvView === "graph";
  let payload = null,
    ordersPayload = null,
    failed = false,
    busy = false,
    lastTick = performance.now(),
    lastTableKey = "";
  const number = new Intl.NumberFormat("pt-BR");
  const date = new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "medium",
  });
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  function renderChart() {
    const rows = payload.requests,
      totals = counts(rows),
      max = Math.max(1, ...totals.map((status) => status.count));
    $("tv-chart").replaceChildren(
      ...totals.map((status) => {
        const bar = element("div", "tv-bar");
        bar.dataset.status = status.key;
        const track = element("div", "tv-bar-track"),
          fill = element("span", "tv-bar-fill");
        fill.style.width = (100 * status.count) / max + "%";
        track.append(fill);
        track.setAttribute("aria-hidden", "true");
        bar.append(
          element("span", "tv-bar-label", status.label),
          track,
          element("strong", "", number.format(status.count)),
          element(
            "small",
            "",
            (rows.length ? Math.round((100 * status.count) / rows.length) : 0) +
              "%",
          ),
        );
        return bar;
      }),
    );
  }

  function renderSummary() {
    const result = summary(payload.requests);
    $("tv-total").textContent = formatLatestReq(result.latest);
    const dateEl = $("tv-latest-date");
    if (dateEl) {
      dateEl.textContent = formatLatestDate(result.latest);
    }
    $("tv-summary").classList.toggle("is-clear", result.clear);
    $("tv-pending").textContent = number.format(result.pending);
    $("tv-pending-note").textContent = "Requisições pendentes";
    if (result.unmapped > 0) {
      console.warn(
        `[Painel TV] ${result.unmapped} requisição(ões) com situação "Não mapeada" na coleta.`,
      );
    }
    renderOrdersSummary();
  }

  function renderOrdersSummary() {
    const box = $("tv-orders-summary");
    const totalEl = $("tv-orders-total");
    const dateEl = $("tv-orders-latest-date");
    const pendingEl = $("tv-orders-pending");
    const noteEl = $("tv-orders-pending-note");
    if (!box || !totalEl || !pendingEl) return;

    if (!ordersPayload || !Array.isArray(ordersPayload.orders)) {
      totalEl.textContent = "Aguardando coleta…";
      if (dateEl) dateEl.textContent = "";
      pendingEl.textContent = "—";
      if (noteEl) noteEl.textContent = "Pedidos pendentes";
      box.classList.remove("is-clear");
      return;
    }

    const ordResult = ordersSummary(ordersPayload.orders);
    totalEl.textContent = formatLatestOrder(ordResult.latest);
    if (dateEl) {
      dateEl.textContent = formatOrderInclusionDate(ordResult.latest);
    }
    box.classList.toggle("is-clear", ordResult.clear);
    pendingEl.textContent = number.format(ordResult.pending);
    if (noteEl) noteEl.textContent = "Pedidos pendentes";
  }

  function renderTable() {
    if (!payload || graphOnly) return;
    const sorted = sortTrackingRows(payload.requests),
      pages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
    state.page %= pages;
    const key = payload.meta.generatedAt + ":" + state.page;
    if (key !== lastTableKey) {
      lastTableKey = key;
      $("tv-rows").replaceChildren(
        ...sorted
          .slice(state.page * PAGE_SIZE, (state.page + 1) * PAGE_SIZE)
          .map((row) => {
            const tr = element("tr", "");
            const values = [
              row.code,
              row.branch,
              row.firstProduct?.trim() || "—",
              firstName(row.requesterName || row.requester),
              row.description,
            ];
            for (const value of values) {
              const td = element("td", ""),
                text = element("span", "tv-cell-text", value);
              text.title = value;
              td.append(text);
              tr.append(td);
            }
            const td = element("td", ""),
              badge = element(
                "span",
                "tv-badge",
                statuses.find((status) => status.key === row.status).label,
              );
            badge.dataset.status = row.status;
            td.append(badge);
            tr.append(td);
            return tr;
          }),
      );
    }
    $("tv-pagination").textContent =
      state.screen === 1
        ? "Página " +
          (state.page + 1) +
          " / " +
          pages +
          " · " +
          number.format(sorted.length) +
          " requisições"
        : "Todos os registros";
  }

  function renderState() {
    if (graphOnly) {
      $("tv-chart-screen").hidden = !payload;
      $("tv-title").textContent = "Gráfico de situações";
      $("tv-kicker").textContent = "DISTRIBUIÇÃO POR SITUAÇÃO";
      $("tv-pagination").textContent = payload
        ? number.format(payload.requests.length) + " requisições"
        : "";
    } else {
      screens.forEach((screen, index) => {
        const el = $(screen.id);
        if (el) el.hidden = state.screen !== index || !payload;
      });
      $("tv-title").textContent = screens[state.screen].title;
      $("tv-kicker").textContent = screens[state.screen].kicker;
      $("tv-screen-label").textContent =
        "Tela " + (state.screen + 1) + " de " + screens.length;
    }
    $("tv-clock").textContent = date.format(new Date());
    $("tv-empty").hidden = Boolean(
      payload &&
      (payload.requests.length || (!graphOnly && state.screen === 0)),
    );
    if (payload) {
      $("tv-empty").textContent = payload.requests.length
        ? ""
        : "Nenhuma requisição na última coleta.";
      const age = Date.now() - Date.parse(payload.meta.generatedAt);
      const stale =
        payload.meta.stale ||
        age > Math.min(120, payload.meta.maxAgeSeconds) * 1000 ||
        age < -60000;
      const warning = failed || !payload.meta.lastAttemptOk || stale;
      $("tv-data-state").dataset.warning = String(warning);
      const prefix = failed
        ? "Falha ao atualizar · exibindo última leitura"
        : !payload.meta.lastAttemptOk
          ? "Falha na coleta · dados anteriores"
          : stale
            ? "Coleta desatualizada"
            : "Coleta atualizada";
      $("tv-data-state").textContent =
        prefix + " · " + date.format(new Date(payload.meta.generatedAt));
    }
    renderTable();
  }

  async function refresh() {
    if (busy) return;
    busy = true;
    const controller = new AbortController(),
      timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const endpointUrl = new URL(
        document.body.dataset.requestsUrl,
        location.href,
      );
      if (endpointUrl.origin !== location.origin) {
        throw new Error("Origem da API não autorizada");
      }
      const response = await fetch(endpointUrl, {
        cache: "no-store",
        signal: controller.signal,
      });
      if (response.status === 401) {
        window.location.assign("/login?next=" + encodeURIComponent(location.pathname));
        return;
      }
      if (!response.ok) throw new Error("API indisponível");
      payload = validate(await response.json());

      // Coleta complementar de pedidos para a visão geral da TV (independente de falha parcial)
      if (!graphOnly && document.body.dataset.ordersUrl) {
        try {
          const ordersUrl = new URL(
            document.body.dataset.ordersUrl,
            location.href,
          );
          if (ordersUrl.origin === location.origin) {
            const ordRes = await fetch(ordersUrl, {
              cache: "no-store",
              signal: controller.signal,
            });
            if (ordRes.ok) {
              const ordJson = await ordRes.json();
              if (ordJson && Array.isArray(ordJson.orders)) {
                ordersPayload = ordJson;
              }
            }
          }
        } catch (ordErr) {
          console.warn("[Painel TV] Leitura de pedidos indisponível:", ordErr);
        }
      }

      failed = false;
      lastTableKey = "";
      // Todas as telas compartilham a mesma coleta, inclusive o gráfico no ciclo automático.
      renderChart();
      if (!graphOnly) renderSummary();
    } catch {
      failed = true;
      if (!payload) {
        $("tv-empty").textContent =
          "Dados indisponíveis. Aguardando uma coleta válida.";
        $("tv-data-state").textContent =
          "Falha na leitura · nova tentativa em até 1 minuto";
        $("tv-data-state").dataset.warning = "true";
      }
    } finally {
      clearTimeout(timeout);
      busy = false;
      renderState();
    }
  }
  function tick() {
    const now = performance.now();
    if (!graphOnly) advance(state, now - lastTick);
    lastTick = now;
    renderState();
  }
  // Interpola somente a barra entre os ticks, sem redesenhar a tabela a cada quadro.
  // Usa o mesmo relógio do ciclo resumo → tabela → gráfico, sem navegação entre páginas.
  function animateProgress(now) {
    const elapsed = Math.min(
      SCREEN_MS,
      state.screenElapsed + Math.max(0, now - lastTick),
    );
    progressFill.style.transform = "scaleX(" + elapsed / SCREEN_MS + ")";
    requestAnimationFrame(animateProgress);
  }
  $("tv-fullscreen").addEventListener("click", async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch {
      $("tv-fullscreen").title =
        "Tela cheia indisponível. Use F11 no navegador.";
    }
  });
  $("tv-next")?.addEventListener("click", () => {
    if (graphOnly) return;
    advanceScreen(state);
    lastTick = performance.now();
    renderState();
  });
  renderState();
  refresh();
  if (progressFill) requestAnimationFrame(animateProgress);
  setInterval(tick, 1000);
  // Atualiza somente a leitura do JSON; o Bash controla a coleta independentemente das TVs abertas.
  setInterval(refresh, REFRESH_MS);
})();
