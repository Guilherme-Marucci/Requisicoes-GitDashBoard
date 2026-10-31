/* Dashboard de Acompanhamento de Pedidos (ESTIPE / ESTPED) — Vanilla JS, leitura exclusiva da API Flask. */
(() => {
  const currencyFmt = new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
  const numberFmt = new Intl.NumberFormat("pt-BR", {
    maximumFractionDigits: 4,
  });
  const intFmt = new Intl.NumberFormat("pt-BR");

  const STATUS_LABELS = {
    pending: "Pendente",
    registered: "Cadastrado",
    partial: "Parcial",
    approved: "Aprovado",
    in_transit: "Em trânsito",
    closed: "Baixado",
    finalized: "Finalizado",
    rejected: "Reprovado",
    canceled: "Cancelado",
    unmapped: "Não mapeado",
  };

  const STATUS_COLORS = {
    pending: "var(--ss-tv-pending)",
    registered: "var(--ss-tv-registered)",
    partial: "var(--ss-tv-partial)",
    approved: "var(--ss-tv-approved)",
    in_transit: "var(--ss-tv-quotation)",
    closed: "var(--ss-tv-closed)",
    finalized: "var(--ss-tv-closed)",
    rejected: "var(--ss-tv-rejected)",
    canceled: "var(--ss-tv-canceled)",
    unmapped: "var(--muted)",
  };

  const state = {
    q: "",
    filial: "",
    status: "",
    data_inicio: "",
    data_fim: "",
    ordenar: "datinc_desc",
    page: 1,
    per_page: 50,
  };

  const $ = (id) => document.getElementById(id);

  function escapeHtml(value) {
    return String(value ?? "").replace(
      /[&<>"']/g,
      (ch) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[ch],
    );
  }

  function formatDateTime(value) {
    if (!value || value === "—" || value === "Não informada") return "—";
    const match = String(value).match(
      /^(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2}))?/,
    );
    if (match) {
      const [, y, m, d, hh, mm] = match;
      return hh !== undefined && mm !== undefined
        ? `${d}/${m}/${y}, ${hh}:${mm}`
        : `${d}/${m}/${y}`;
    }
    return String(value);
  }

  function formatDecimal(value, digits = null) {
    const num = Number(value);
    if (!Number.isFinite(num)) return escapeHtml(value ?? "0");
    if (digits !== null) {
      return num.toLocaleString("pt-BR", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
    }
    return numberFmt.format(num);
  }

  function setDataState(kind, message) {
    const box = $("orders-data-state");
    const msg = $("orders-data-message");
    if (box) box.dataset.state = kind;
    if (msg) msg.textContent = message;
  }

  function buildQueryParams(includePagination = true) {
    const params = new URLSearchParams();
    if (state.filial) params.set("filial", state.filial);
    if (state.status) params.set("status", state.status);
    if (state.data_inicio) params.set("data_inicio", state.data_inicio);
    if (state.data_fim) params.set("data_fim", state.data_fim);
    if (state.q) params.set("q", state.q);
    if (includePagination) {
      params.set("ordenar", state.ordenar);
      params.set("page", String(state.page));
      params.set("per_page", String(state.per_page));
    }
    return params;
  }

  function renderMetrics(metrics) {
    $("kpi-total-purchased").textContent = currencyFmt.format(
      Number(metrics.totalPurchased) || 0,
    );
    $("kpi-total-sub").textContent =
      `${intFmt.format(metrics.activeOrdersCount || 0)} pedidos ativos · ${intFmt.format(metrics.activeItemsCount || 0)} itens`;

    $("kpi-pending-orders").textContent = intFmt.format(
      metrics.pendingOrdersCount || 0,
    );
    const ff = metrics.fulfillment || {};
    $("kpi-pending-sub").textContent =
      `${intFmt.format(metrics.pendingItemsCount || 0)} itens em aberto (${ff.pendingDeliveryPct ?? 0}% pendentes)`;

    $("kpi-avg-ticket").textContent = currencyFmt.format(
      Number(metrics.averageTicketPerOrder) || 0,
    );
    $("kpi-avg-sub").textContent =
      `Média por pedido sobre ${intFmt.format(metrics.activeOrdersCount || 0)} NUMPEDs`;

    const mc = metrics.monthlyComparison || {};
    const cur = mc.currentMonth || { label: "Mês atual", total: 0, ordersCount: 0 };
    const prev = mc.previousMonth || { label: "Mês anterior", total: 0, ordersCount: 0 };
    const deltaEl = $("kpi-month-delta");
    deltaEl.classList.remove("is-positive", "is-negative");

    if (mc.deltaPct === null || mc.deltaPct === undefined) {
      deltaEl.textContent = currencyFmt.format(Number(cur.total) || 0);
    } else {
      const sign = mc.deltaPct > 0 ? "+" : "";
      deltaEl.textContent = `${sign}${String(mc.deltaPct).replace(".", ",")}%`;
      if (mc.deltaPct > 0) deltaEl.classList.add("is-positive");
      else if (mc.deltaPct < 0) deltaEl.classList.add("is-negative");
    }
    $("kpi-month-sub").textContent =
      `${cur.label}: ${currencyFmt.format(cur.total || 0)} vs ${prev.label}: ${currencyFmt.format(prev.total || 0)}`;

    // Card 1: Comparativo financeiro mensal
    $("chart-monthly-badge").textContent = `${cur.label} vs ${prev.label}`;
    $("monthly-highlight").innerHTML = `
      <div class="monthly-box">
        <span>${escapeHtml(prev.label)} (anterior)</span>
        <strong>${escapeHtml(currencyFmt.format(prev.total || 0))}</strong>
        <small>${intFmt.format(prev.ordersCount || 0)} pedidos · ${intFmt.format(prev.itemsCount || 0)} itens</small>
      </div>
      <div class="monthly-box">
        <span>${escapeHtml(cur.label)} (atual)</span>
        <strong>${escapeHtml(currencyFmt.format(cur.total || 0))}</strong>
        <small>${intFmt.format(cur.ordersCount || 0)} pedidos · ${intFmt.format(cur.itemsCount || 0)} itens</small>
      </div>`;

    const series = Array.isArray(mc.series) ? mc.series : [];
    const maxMonthVal = Math.max(1, ...series.map((s) => Number(s.total) || 0));
    $("monthly-chart").innerHTML = series
      .map((entry) => {
        const pct = Math.min(
          100,
          Math.max(0, Math.round(((Number(entry.total) || 0) / maxMonthVal) * 100)),
        );
        return `
          <div class="chart-row">
            <div class="chart-row__head">
              <span class="chart-row__label">${escapeHtml(entry.label)}</span>
              <span class="chart-row__meta">
                <strong>${escapeHtml(currencyFmt.format(entry.total || 0))}</strong>
                · ${intFmt.format(entry.ordersCount || 0)} ped.
              </span>
            </div>
            <div class="chart-track" aria-hidden="true">
              <div class="chart-fill" style="width: ${pct}%;"></div>
            </div>
          </div>`;
      })
      .join("");

    // Card 2: Taxa de atendimento e distribuição SITUAC
    const donePct = Number(ff.fulfilledPct) || 0;
    const openPct = Number(ff.pendingDeliveryPct) || 0;
    $("chart-fulfillment-badge").textContent = `${String(donePct).replace(".", ",")}% atendido`;
    $("fulfillment-box").innerHTML = `
      <div class="fulfillment-box__labels">
        <span class="fulfillment-ok">Atendido / Baixado: ${String(donePct).replace(".", ",")}% (${intFmt.format(ff.fulfilledItems || 0)})</span>
        <span class="fulfillment-pending">Pendente entrega: ${String(openPct).replace(".", ",")}% (${intFmt.format(ff.pendingDeliveryItems || 0)})</span>
      </div>
      <div class="fulfillment-bar" aria-hidden="true">
        <div class="fulfillment-bar__done" style="width: ${Math.min(100, Math.max(0, donePct))}%;"></div>
        <div class="fulfillment-bar__open" style="width: ${Math.min(100, Math.max(0, openPct))}%;"></div>
      </div>`;

    const dist = Array.isArray(metrics.statusDistribution)
      ? metrics.statusDistribution
      : [];
    const unmappedDist = dist.find((d) => d.status === "unmapped");
    if (unmappedDist && unmappedDist.itemsCount > 0) {
      console.warn(
        `[Pedidos] ${unmappedDist.itemsCount} item(ns) com SITUAC não mapeada:`,
        unmappedDist.rawCodes,
      );
    }
    const visibleDist = dist.filter((d) => d.status !== "unmapped");
    const maxStatusCount = Math.max(
      1,
      ...visibleDist.map((d) => Number(d.itemsCount) || 0),
    );
    $("status-chart").innerHTML = visibleDist.length
      ? visibleDist
          .map((d) => {
            const pct = Math.min(
              100,
              Math.max(
                0,
                Math.round(((Number(d.itemsCount) || 0) / maxStatusCount) * 100),
              ),
            );
            const color = STATUS_COLORS[d.status] || "var(--accent-strong)";
            const rawBadge =
              Array.isArray(d.rawCodes) && d.rawCodes.length
                ? ` (${d.rawCodes.join("/")})`
                : "";
            return `
              <div class="chart-row">
                <div class="chart-row__head">
                  <span class="chart-row__label">${escapeHtml(d.label + rawBadge)}</span>
                  <span class="chart-row__meta">
                    <strong>${intFmt.format(d.itemsCount || 0)} itens</strong>
                    · ${escapeHtml(currencyFmt.format(d.totalValue || 0))}
                  </span>
                </div>
                <div class="chart-track" aria-hidden="true">
                  <div class="chart-fill" style="width: ${pct}%; background: ${color};"></div>
                </div>
              </div>`;
          })
          .join("")
      : '<p class="cell-sub">Nenhum item no recorte selecionado.</p>';
  }

  function populateBranches(branches) {
    const select = $("orders-branch");
    if (!select || !Array.isArray(branches)) return;
    const current = state.filial;
    select.innerHTML =
      '<option value="">Todas as filiais</option>' +
      branches
        .map(
          (b) =>
            `<option value="${escapeHtml(b)}">Filial ${escapeHtml(b)}</option>`,
        )
        .join("");
    select.value = branches.includes(current) ? current : "";
  }

  function renderTable(listPayload) {
    const items = Array.isArray(listPayload.items) ? listPayload.items : [];
    const pag = listPayload.pagination || {
      page: 1,
      totalPages: 1,
      totalItems: 0,
      totalOrders: 0,
      hasPrev: false,
      hasNext: false,
    };

    const tbody = $("orders-tbody");
    const tableWrap = document.querySelector(".orders-table-wrap");
    const emptyEl = $("orders-empty");
    const pagNav = $("orders-pagination");

    $("orders-results-count").textContent =
      `${intFmt.format(pag.totalItems)} ${pag.totalItems === 1 ? "item encontrado" : "itens encontrados"} em ${intFmt.format(pag.totalOrders)} ${pag.totalOrders === 1 ? "pedido" : "pedidos"}`;

    if (!items.length) {
      tbody.innerHTML = "";
      tableWrap.hidden = true;
      emptyEl.hidden = false;
      pagNav.hidden = true;
      return;
    }

    tableWrap.hidden = false;
    emptyEl.hidden = true;
    pagNav.hidden = pag.totalPages <= 1;
    $("orders-page-info").textContent =
      `Página ${pag.page} de ${pag.totalPages}`;
    $("orders-prev").disabled = !pag.hasPrev;
    $("orders-next").disabled = !pag.hasNext;

    tbody.innerHTML = items
      .map((row) => {
        const statusKey = row.status || "unmapped";
        const statusText = STATUS_LABELS[statusKey] || statusKey;
        const rawSuffix =
          row.rawStatus && row.rawStatus !== "—" ? ` · ${row.rawStatus}` : "";
        const prodRef =
          row.reference && row.reference !== "—" ? ` · Ref. ${row.reference}` : "";
        const cotInfo =
          row.quoteCode && row.quoteCode !== "—"
            ? `Cot. ${row.quoteCode}`
            : "Sem cotação";
        const obsText =
          row.observation && row.observation !== "—" ? row.observation : "—";

        return `
          <tr data-status="${escapeHtml(statusKey)}">
            <td class="cell-id">${escapeHtml(row.idIpe || "—")}</td>
            <td class="cell-code">${escapeHtml(row.requisitionCode || "—")}</td>
            <td class="cell-code">${escapeHtml(row.orderNumber || row.code || "—")}</td>
            <td>
              <span class="cell-main">${escapeHtml(row.productCode || "—")} — ${escapeHtml(row.description || "—")}</span>
              <span class="cell-sub">Unid.: ${escapeHtml(row.unit || "UN")}${escapeHtml(prodRef)}</span>
            </td>
            <td class="num-col">${formatDecimal(row.qtyOrdered)}</td>
            <td class="num-col">${escapeHtml(currencyFmt.format(Number(row.unitPrice) || 0))}</td>
            <td class="num-col"><strong>${escapeHtml(currencyFmt.format(Number(row.totalPrice ?? row.totalValue) || 0))}</strong></td>
            <td class="num-col">${formatDecimal(row.qtyDelivered)}</td>
            <td>
              <span class="order-status-pill" data-status="${escapeHtml(statusKey)}">${escapeHtml(statusText + rawSuffix)}</span>
            </td>
            <td>
              <span class="cell-main">${escapeHtml(row.supplier || "—")}</span>
              <span class="cell-sub">Filial ${escapeHtml(row.branch || "—")} · ${escapeHtml(row.buyer || "—")}</span>
            </td>
            <td>
              <span class="cell-main">${escapeHtml(formatDateTime(row.inclusionDate))}</span>
              <span class="cell-sub">Atu.: ${escapeHtml(formatDateTime(row.updatedAt))}</span>
            </td>
            <td>
              <span class="cell-main">${escapeHtml(cotInfo)}</span>
              <span class="cell-obs" title="${escapeHtml(obsText)}">${escapeHtml(obsText)}</span>
            </td>
          </tr>`;
      })
      .join("");
  }

  async function loadDashboard() {
    const reloadBtn = $("orders-reload");
    const gridSection = $("grade-pedidos");
    if (reloadBtn) reloadBtn.disabled = true;
    if (gridSection) gridSection.setAttribute("aria-busy", "true");

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);

    try {
      const ordersBase = new URL(
        document.body.dataset.ordersUrl,
        location.href,
      );
      const metricsBase = new URL(
        document.body.dataset.metricsUrl,
        location.href,
      );
      if (
        ordersBase.origin !== location.origin ||
        metricsBase.origin !== location.origin
      ) {
        throw new Error("Origem da API não autorizada.");
      }

      ordersBase.search = buildQueryParams(true).toString();
      metricsBase.search = buildQueryParams(false).toString();

      const [ordersRes, metricsRes] = await Promise.all([
        fetch(ordersBase, { cache: "no-store", signal: controller.signal }),
        fetch(metricsBase, { cache: "no-store", signal: controller.signal }),
      ]);

      if (ordersRes.status === 401 || metricsRes.status === 401) {
        window.location.assign("/login?next=" + encodeURIComponent(location.pathname));
        return;
      }

      if (!ordersRes.ok || !metricsRes.ok) {
        throw new Error("Coleta de pedidos indisponível.");
      }

      const [ordersData, metricsData] = await Promise.all([
        ordersRes.json(),
        metricsRes.json(),
      ]);

      populateBranches(ordersData.filters?.availableBranches || []);
      renderMetrics(metricsData.metrics || {});
      renderTable(ordersData);

      const meta = ordersData.meta || {};
      const genDate = meta.generatedAt
        ? new Date(meta.generatedAt).toLocaleString("pt-BR")
        : "—";
      const staleWarn = meta.stale ? "A coleta está desatualizada. " : "";
      setDataState(
        meta.stale ? "warning" : "ready",
        `${staleWarn}Dados do ERP (ESTIPE / ESTPED) · coletados em ${genDate}.`,
      );
    } catch (err) {
      console.warn("[Pedidos] Falha ao carregar dados da coleta:", err);
      setDataState(
        "error",
        "Dados de pedidos indisponíveis. Execute a sincronização do coletor ERP e recarregue.",
      );
      $("orders-results-count").textContent =
        "Não foi possível carregar os itens de pedido.";
    } finally {
      clearTimeout(timeout);
      if (reloadBtn) reloadBtn.disabled = false;
      if (gridSection) gridSection.setAttribute("aria-busy", "false");
    }
  }

  function resetFilters() {
    state.q = "";
    state.filial = "";
    state.status = "";
    state.data_inicio = "";
    state.data_fim = "";
    state.ordenar = "datinc_desc";
    state.page = 1;

    $("orders-search").value = "";
    $("orders-branch").value = "";
    $("orders-status").value = "";
    $("orders-date-start").value = "";
    $("orders-date-end").value = "";
    $("orders-sort").value = "datinc_desc";
    loadDashboard();
  }

  let searchTimer = null;
  function init() {
    $("orders-search")?.addEventListener("input", (e) => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        state.q = e.target.value.trim();
        state.page = 1;
        loadDashboard();
      }, 240);
    });

    $("orders-branch")?.addEventListener("change", (e) => {
      state.filial = e.target.value;
      state.page = 1;
      loadDashboard();
    });

    $("orders-status")?.addEventListener("change", (e) => {
      state.status = e.target.value;
      state.page = 1;
      loadDashboard();
    });

    $("orders-date-start")?.addEventListener("change", (e) => {
      state.data_inicio = e.target.value;
      state.page = 1;
      loadDashboard();
    });

    $("orders-date-end")?.addEventListener("change", (e) => {
      state.data_fim = e.target.value;
      state.page = 1;
      loadDashboard();
    });

    $("orders-sort")?.addEventListener("change", (e) => {
      state.ordenar = e.target.value;
      state.page = 1;
      loadDashboard();
    });

    $("orders-per-page")?.addEventListener("change", (e) => {
      state.per_page = Number(e.target.value) || 50;
      state.page = 1;
      loadDashboard();
    });

    $("orders-prev")?.addEventListener("click", () => {
      if (state.page > 1) {
        state.page -= 1;
        loadDashboard();
      }
    });

    $("orders-next")?.addEventListener("click", () => {
      state.page += 1;
      loadDashboard();
    });

    $("orders-clear")?.addEventListener("click", resetFilters);
    $("orders-empty-reset")?.addEventListener("click", resetFilters);
    $("orders-reload")?.addEventListener("click", loadDashboard);

    loadDashboard();
  }

  init();
})();
