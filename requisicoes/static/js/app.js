/* Apresentação do retrato servido pelo Flask. Catálogos visuais locais traduzem apenas classificações confirmadas. */
const statusCatalog = requisicoesStatus;

const sectors = [
  {
    key: "compras",
    label: "Compras",
    subtitle: "Aquisições e compras",
    icon: "shopping-cart",
  },
  {
    key: "credito_cobranca",
    label: "Crédito e Cobrança",
    subtitle: "Análise de crédito e cobrança",
    icon: "credit-card",
  },
  {
    key: "financeiro",
    label: "Financeiro",
    subtitle: "Contas e tesouraria",
    icon: "wallet",
  },
  {
    key: "administrativo_matriz",
    label: "Administrativo Matriz",
    subtitle: "Apoio administrativo e matriz",
    icon: "building",
  },
  {
    key: "sac",
    label: "SAC",
    subtitle: "Atendimento ao cliente",
    icon: "headset",
  },
  {
    key: "juridico",
    label: "Jurídico",
    subtitle: "Contratos e conformidade",
    icon: "scale",
  },
  {
    key: "ti",
    label: "T.I",
    subtitle: "Tecnologia da informação",
    icon: "monitor",
  },
  {
    key: "rh",
    label: "RH",
    subtitle: "Recursos humanos e pessoal",
    icon: "users",
  },
  {
    key: "armazem",
    label: "Armazém",
    subtitle: "Estoque e armazenagem",
    icon: "warehouse",
  },
  {
    key: "projetos",
    label: "Projetos",
    subtitle: "Planejamento e projetos",
    icon: "folder-kanban",
  },
  {
    key: "recebimento",
    label: "Recebimento",
    subtitle: "Entrada e conferência de materiais",
    icon: "package-check",
  },
  {
    key: "limpeza",
    label: "Limpeza",
    subtitle: "Conservação e higienização",
    icon: "sparkles",
  },
  {
    key: "reintegracao",
    label: "Reintegração",
    subtitle: "Logística reversa e retorno",
    icon: "rotate-ccw",
  },
  {
    key: "manutencao",
    label: "Manutenção",
    subtitle: "Peças, frotas e serviços",
    icon: "wrench",
  },
  {
    key: "transporte",
    label: "Transporte",
    subtitle: "Operação e frotas de transporte",
    icon: "truck",
  },
  {
    key: "expedicao",
    label: "Expedição",
    subtitle: "Saída e despacho",
    icon: "send",
  },
  {
    key: "fiscal",
    label: "Fiscal",
    subtitle: "Tributário e notas fiscais",
    icon: "receipt",
  },
  {
    key: "unclassified",
    label: "Setor não informado",
    subtitle: "Sem classificação nesta coleta",
    icon: "folder",
  },
  // Chaves de compatibilidade para dados e testes legados
  {
    key: "operations",
    label: "Operações",
    subtitle: "Operações gerais",
    icon: "boxes",
  },
  {
    key: "maintenance",
    label: "Manutenção",
    subtitle: "Manutenção geral",
    icon: "wrench",
  },
  {
    key: "facilities",
    label: "Facilities",
    subtitle: "Infraestrutura e apoio",
    icon: "building-2",
  },
  {
    key: "technology",
    label: "Tecnologia",
    subtitle: "Equipamentos e suporte",
    icon: "monitor",
  },
  {
    key: "supply",
    label: "Suprimentos",
    subtitle: "Abastecimento e consumo",
    icon: "package",
  },
];

let requests = [];

const PAGE_SIZE = 20;

const state = {
  query: "",
  sector: "",
  status: "",
  branch: "",
  dateStart: "",
  dateEnd: "",
  attention: false,
  view: "kanban",
  limit: PAGE_SIZE,
  openSectors: new Set(sectors.map((sector) => sector.key)),
  openCards: new Set(),
};

const sectorList = document.querySelector("#sector-list");
const emptyState = document.querySelector("#empty-state");
const searchInput = document.querySelector("#search-input");
const sectorFilter = document.querySelector("#sector-filter");
const statusFilter = document.querySelector("#status-filter");
const branchFilter = document.querySelector("#branch-filter");
const dateStartFilter = document.querySelector("#date-start-filter");
const dateEndFilter = document.querySelector("#date-end-filter");
const attentionFilter = document.querySelector("#attention-filter");
const loadMoreWrap = document.querySelector("#load-more-wrap");
const loadMoreBtn = document.querySelector("#load-more-btn");
const loadMoreInfo = document.querySelector("#load-more-info");

function escapeHtml(value) {
  // Valores de integração futura também deverão entrar na interface como texto, nunca como HTML executável.
  return String(value).replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character],
  );
}

function searchable(value) {
  return String(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR");
}

function statusLabel(key) {
  return (
    statusCatalog.find((status) => status.key === key)?.label ??
    "Não classificado"
  );
}

function formatDateTime(value) {
  if (!value || value === "Não informada" || value === "—") return "Não informada";
  // Suporta ISO com ou sem fuso (ex: 2026-08-12T15:07:00 ou 2026-08-12T15:07:00-03:00)
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2}))?/);
  if (match) {
    const [, y, m, d, hh, mm] = match;
    return hh !== undefined && mm !== undefined ? `${d}/${m}/${y}, ${hh}:${mm}` : `${d}/${m}/${y}`;
  }
  const parsed = Date.parse(value);
  if (Number.isFinite(parsed)) {
    const dt = new Date(parsed);
    const d = String(dt.getDate()).padStart(2, "0");
    const m = String(dt.getMonth() + 1).padStart(2, "0");
    const y = dt.getFullYear();
    const hh = String(dt.getHours()).padStart(2, "0");
    const mm = String(dt.getMinutes()).padStart(2, "0");
    return `${d}/${m}/${y}, ${hh}:${mm}`;
  }
  return String(value);
}

function dateLabel(value) {
  return formatDateTime(value);
}

function historyHtml(request) {
  const events = requisicoesFluxo.history(request);
  if (!events.length) return "";
  return `<section class="request-audit" aria-label="Histórico da requisição ${escapeHtml(request.code)}">
    <h4>Histórico da requisição</h4>
    <ol class="request-history">${events
      .map(
        (event) => `<li>
      <time datetime="${escapeHtml(event.at)}">${escapeHtml(dateLabel(event.at))}</time>
      <strong>${escapeHtml(event.action)}</strong>
      <span>${escapeHtml(event.actor || "Responsável não informado")}</span>
      <small>${escapeHtml(requisicoesFluxo.stageLabel(event.stage))}</small>
    </li>`,
      )
      .join("")}</ol>
  </section>`;
}

function cardHtml(request) {
  const {
    id,
    code,
    status,
    branch,
    title,
    description,
    reference,
    deadline,
    item,
  } = request;
  const sector =
    sectors.find((value) => value.key === request.sector)?.label ||
    request.sectorName ||
    "Setor não informado";
  const flow = request.workflow || {};
  const attention = requisicoesFluxo.needsAttention(request);
  const hasDeadline = Boolean(
    deadline && deadline !== "Não informado" && deadline !== "—",
  );
  const fields = [
    [
      "Etapa atual",
      requisicoesFluxo.stageLabel(requisicoesFluxo.stageKey(request)),
    ],
    [
      "Solicitante / setor",
      request.requesterName
        ? `${request.requesterName} (Cód. ${request.requester})`
        : request.requester || sector,
    ],
    ["Filial", branch],
    ["Item solicitado", item],
    ["Abertura", formatDateTime(request.createdAt || request.inclusionDate)],
    ["Referência", formatDateTime(reference)],
    ["Situação", statusLabel(status)],
  ];
  if (hasDeadline) {
    fields.splice(6, 0, ["Prazo", deadline]);
  }
  if (flow.estimatedValue != null)
    fields.push([
      "Valor previsto",
      new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
      }).format(Number(flow.estimatedValue)),
    ]);
  return `
    <details class="request-card" data-card-id="${escapeHtml(id)}" data-status="${escapeHtml(status)}" ${state.openCards.has(id) ? "open" : ""}>
      <summary aria-label="Requisição ${escapeHtml(code)}: ${escapeHtml(title)}, situação ${escapeHtml(statusLabel(status))}">
        <span><span class="request-card__id">REQ. ${escapeHtml(code)}</span><strong class="request-card__title">${escapeHtml(title)}</strong><span class="request-card__branch">${escapeHtml(sector)} · Filial ${escapeHtml(branch)}</span>${hasDeadline ? `<span class="request-card__deadline">Prazo: ${escapeHtml(deadline)}</span>` : ""}</span>
        <span class="request-card__right"><span class="status-pill">${escapeHtml(statusLabel(status))}</span><span class="request-card__chevron" aria-hidden="true"><i data-lucide="chevron-down" aria-hidden="true"></i></span></span>
      </summary>
      <div class="request-card__detail">
        ${attention ? `<p class="request-attention"><i data-lucide="circle-alert" aria-hidden="true"></i> ${escapeHtml(flow.attention || "Requisição com situação Pendente.")}</p>` : ""}
        <p>${escapeHtml(description)}</p>
        <dl>${fields.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}</dl>
        ${historyHtml(request)}
      </div>
    </details>`;
}

function extractDate(request) {
  const raw = request.reference || request.createdAt;
  if (!raw || raw === "Não informada") return null;
  const match = String(raw).match(/^\d{4}-\d{2}-\d{2}/);
  return match ? match[0] : null;
}

function sectorHtml(sector, matchingRequests) {
  const visible = matchingRequests.slice(0, state.limit);
  const total = matchingRequests.length;
  const countLabel =
    visible.length < total
      ? `Exibindo ${visible.length} de ${total}`
      : `${total} ${total === 1 ? "requisição" : "requisições"}`;
  return `
    <details class="sector" data-sector-id="${escapeHtml(sector.key)}" ${state.openSectors.has(sector.key) ? "open" : ""}>
      <summary aria-label="Setor ${escapeHtml(sector.label)}, ${total} requisições">
        <span class="sector__icon" aria-hidden="true"><i data-lucide="${escapeHtml(sector.icon)}" aria-hidden="true"></i></span>
        <span class="sector__heading"><strong>${escapeHtml(sector.label)}</strong><small>${escapeHtml(sector.subtitle)}</small></span>
        <span class="sector__count">${countLabel}</span>
        <span class="sector__chevron" aria-hidden="true"><i data-lucide="chevron-down" aria-hidden="true"></i></span>
      </summary>
      <div class="sector__body"><div class="card-grid" data-card-stack>${visible.map(cardHtml).join("")}</div></div>
    </details>`;
}

function matches(request) {
  if (state.sector && request.sector !== state.sector) return false;
  if (state.status && request.status !== state.status) return false;
  if (state.branch && request.branch !== state.branch) return false;
  if (state.attention && !requisicoesFluxo.needsAttention(request))
    return false;
  if (state.dateStart || state.dateEnd) {
    const reqDate = extractDate(request);
    if (!reqDate) return false;
    if (state.dateStart && reqDate < state.dateStart) return false;
    if (state.dateEnd && reqDate > state.dateEnd) return false;
  }
  // O código permanece textual: não perder zeros iniciais nem buscar em descrições.
  return searchable(request.code).includes(searchable(state.query));
}

function render() {
  // Os indicadores contam apenas os registros filtrados. Situações sem mapeamento não são consideradas tratadas.
  const matching = requests.filter(matches);
  const groups = sectors
    .map((sector) => ({
      sector,
      items: matching.filter((request) => request.sector === sector.key),
    }))
    .filter(({ items }) => items.length);
  const columns = requisicoesFluxo.group(matching);
  const hasMore =
    state.view === "kanban"
      ? columns.some((column) => column.items.length > state.limit)
      : groups.some(({ items }) => items.length > state.limit);

  sectorList.className =
    state.view === "kanban"
      ? "kanban-board"
      : state.view === "rankings"
        ? "rankings-view"
        : "sector-list";
  document.querySelector("#kanban-navigation").hidden = state.view !== "kanban";
  const actionsWrap = document.querySelector(".results-bar__actions");
  if (actionsWrap) actionsWrap.hidden = state.view === "rankings";
  sectorList.setAttribute(
    "aria-label",
    state.view === "kanban"
      ? "Requisições por etapa; role horizontalmente para ver todas"
      : state.view === "rankings"
        ? "Gráficos de ranking das requisições"
        : "Requisições por setor",
  );
  if (state.view === "rankings") {
    sectorList.innerHTML = requisicoesRankings.renderGrid(matching);
    if (typeof lucide !== "undefined") {
      lucide.createIcons({ root: sectorList });
    }
  } else if (state.view === "kanban") {
    sectorList.innerHTML = columns
      .map((column) => {
        const visible = column.items.slice(0, state.limit);
        const moreCount = column.items.length - visible.length;
        return `<section class="kanban-column" aria-label="${escapeHtml(column.label)}">
      <header class="kanban-column__heading"><h3>${escapeHtml(column.label)}</h3><span aria-label="${column.items.length} requisições">${column.items.length}</span></header>
      <div class="kanban-column__cards">${visible.map(cardHtml).join("") || '<p class="kanban-column__empty">Nenhuma requisição nesta etapa.</p>'}</div>
      ${moreCount > 0 ? `<div class="kanban-column__more" title="${moreCount} requisições adicionais nesta etapa">Exibindo ${visible.length} de ${column.items.length}</div>` : ""}
    </section>`;
      })
      .join("");
  } else {
    sectorList.innerHTML = groups.map(({ sector, items }) => sectorHtml(sector, items)).join("");
  }

  if (loadMoreWrap) {
    loadMoreWrap.hidden = state.view === "rankings" || !hasMore || matching.length === 0;
    if (loadMoreInfo) {
      loadMoreInfo.textContent = `Exibindo até ${state.limit} requisições por ${state.view === "kanban" ? "etapa" : "setor"}. Total de ${matching.length} ${matching.length === 1 ? "requisição encontrada" : "requisições encontradas"}.`;
    }
  }

  emptyState.hidden = matching.length !== 0;
  emptyState.querySelector("p").textContent = requests.length
    ? "Ajuste a busca ou limpe os filtros para voltar à visão completa."
    : "A última coleta foi concluída sem requisições.";
  document.querySelector("#empty-reset").hidden = requests.length === 0;
  document.querySelector("#metric-total").textContent = String(matching.length);
  document.querySelector("#metric-sectors").textContent = String(
    groups.filter((group) => group.sector.key !== "unclassified").length,
  );
  // Situações não mapeadas são registradas no console em vez de bloquear os indicadores na tela.
  const pending = matching.filter(
    (request) => request.status === "pending",
  ).length;
  document.querySelector("#metric-pending").textContent = String(pending);
  document.querySelector("#pending-description").textContent =
    "Requisições com situação Pendente";
  document.querySelector("#results-count").textContent =
    `${matching.length} ${matching.length === 1 ? "requisição encontrada" : "requisições encontradas"}${hasMore ? ` (exibindo até ${state.limit} por ${state.view === "kanban" ? "etapa" : "setor"})` : ""}`;
}

function resetFilters() {
  state.query = "";
  state.sector = "";
  state.status = "";
  state.branch = "";
  state.dateStart = "";
  state.dateEnd = "";
  state.attention = false;
  state.limit = PAGE_SIZE;
  searchInput.value = "";
  sectorFilter.value = "";
  statusFilter.value = "";
  branchFilter.value = "";
  if (dateStartFilter) dateStartFilter.value = "";
  if (dateEndFilter) dateEndFilter.value = "";
  attentionFilter.checked = false;
  render();
  searchInput.focus();
}

function init() {
  for (const [id, direction] of [
    ["previous-stage", -1],
    ["next-stage", 1],
  ]) {
    document.getElementById(id).addEventListener("click", () => {
      const column = sectorList.querySelector(".kanban-column");
      const gap = parseFloat(getComputedStyle(sectorList).columnGap) || 0;
      const distance = column
        ? column.getBoundingClientRect().width + gap
        : sectorList.clientWidth;
      sectorList.scrollBy({ left: direction * distance, behavior: "instant" });
    });
  }
  // Na interface principal (filtro e legenda), exibir apenas as situações oficiais do fluxo ERP.
  const uiStatuses = statusCatalog.filter(
    (status) => status.key !== "unmapped" && status.key !== "released",
  );
  statusFilter.insertAdjacentHTML(
    "beforeend",
    uiStatuses
      .map(
        (status) =>
          `<option value="${escapeHtml(status.key)}">${escapeHtml(status.label)}</option>`,
      )
      .join(""),
  );
  document.querySelector("#status-legend").innerHTML = uiStatuses
    .map(
      (status) =>
        `<span class="legend__item" data-status-key="${escapeHtml(status.key)}"><span class="legend__swatch" aria-hidden="true"></span>${escapeHtml(status.label)}</span>`,
    )
    .join("");

  searchInput.addEventListener("input", () => {
    state.query = searchInput.value.trim();
    state.limit = PAGE_SIZE;
    render();
  });
  sectorFilter.addEventListener("change", () => {
    state.sector = sectorFilter.value;
    state.limit = PAGE_SIZE;
    render();
  });
  statusFilter.addEventListener("change", () => {
    state.status = statusFilter.value;
    state.limit = PAGE_SIZE;
    render();
  });
  branchFilter.addEventListener("change", () => {
    state.branch = branchFilter.value;
    state.limit = PAGE_SIZE;
    render();
  });
  dateStartFilter?.addEventListener("change", () => {
    state.dateStart = dateStartFilter.value;
    state.limit = PAGE_SIZE;
    render();
  });
  dateEndFilter?.addEventListener("change", () => {
    state.dateEnd = dateEndFilter.value;
    state.limit = PAGE_SIZE;
    render();
  });
  attentionFilter.addEventListener("change", () => {
    state.attention = attentionFilter.checked;
    state.limit = PAGE_SIZE;
    render();
  });
  loadMoreBtn?.addEventListener("click", () => {
    state.limit += PAGE_SIZE;
    render();
  });
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      document
        .querySelectorAll("[data-view]")
        .forEach((option) =>
          option.setAttribute("aria-pressed", String(option === button)),
        );
      render();
    });
  });
  document
    .querySelector("#clear-filters")
    .addEventListener("click", resetFilters);
  document
    .querySelector("#empty-reset")
    .addEventListener("click", resetFilters);

  // O estado de expansão é guardado para que buscar e filtrar não feche os detalhes já abertos.
  sectorList.addEventListener(
    "toggle",
    (event) => {
      if (!event.isTrusted || !(event.target instanceof HTMLDetailsElement))
        return;
      const sectorId = event.target.dataset.sectorId;
      const cardId = event.target.dataset.cardId;
      const targetSet = sectorId ? state.openSectors : state.openCards;
      const identifier = sectorId || cardId;
      if (identifier)
        event.target.open
          ? targetSet.add(identifier)
          : targetSet.delete(identifier);
    },
    true,
  );

  document.querySelector("#expand-all").addEventListener("click", () => {
    state.openSectors = new Set(sectors.map((sector) => sector.key));
    state.openCards = new Set(requests.map((request) => request.id));
    render();
  });
  document.querySelector("#collapse-all").addEventListener("click", () => {
    state.openSectors.clear();
    state.openCards.clear();
    render();
  });

  loadRequests();
}

let lastMeta = null;
let loadFailed = false;
const dataMessage = document.querySelector("#data-message");
const dataState = document.querySelector("#data-state");
const reloadButton = document.querySelector("#reload-data");

function setDataState(kind, message) {
  dataState.dataset.state = kind;
  dataMessage.textContent = message;
}

function presentFreshness() {
  if (!lastMeta || loadFailed) return;
  const age = Date.now() - Date.parse(lastMeta.generatedAt);
  const stale =
    lastMeta.stale || age > lastMeta.maxAgeSeconds * 1000 || age < -60000;
  const date = new Date(lastMeta.generatedAt).toLocaleString("pt-BR");
  const warning = !lastMeta.lastAttemptOk
    ? "A última coleta falhou; exibindo a última versão válida. "
    : stale
      ? "A coleta está desatualizada. "
      : "";
  setDataState(
    warning ? "warning" : "ready",
    `${warning}Dados do ERP · coletados em ${date}.`,
  );
}

function logDiagnostics(rows, meta) {
  const unmapped = rows.filter((r) => r.status === "unmapped");
  const unclassifiedSectors = rows.filter((r) => r.sector === "unclassified");
  console.info(
    `[Requisições] Coleta carregada (${rows.length} registros · gerada em ${meta.generatedAt}).`,
  );
  if (unmapped.length > 0) {
    console.warn(
      `[Requisições] ${unmapped.length} requisição(ões) com situação "Não mapeada":`,
      unmapped.map((r) => ({ codigo: r.code, setor: r.sectorName || r.sector })),
    );
  }
  if (unclassifiedSectors.length > 0) {
    console.info(
      `[Requisições] ${unclassifiedSectors.length} requisição(ões) sem setor classificado no catálogo:`,
      unclassifiedSectors.map((r) => ({ codigo: r.code, setorOriginal: r.sectorName })),
    );
  }
}

function validatePayload(payload) {
  const meta = payload?.meta;
  if (
    !meta ||
    meta.schemaVersion !== 3 ||
    meta.source !== "erp" ||
    !Number.isFinite(Date.parse(meta.generatedAt)) ||
    typeof meta.lastAttemptOk !== "boolean" ||
    typeof meta.stale !== "boolean" ||
    !Number.isFinite(meta.maxAgeSeconds) ||
    meta.maxAgeSeconds <= 0 ||
    !Array.isArray(payload.requests)
  )
    throw new Error("Resposta incompatível.");
  const ids = new Set();
  const optionalStrings = [
    "requester",
    "requesterName",
    "firstProduct",
    "sectorName",
    "sectorCode",
    "inclusionDate",
  ];
  payload.requests.forEach((row) => {
    const fields = [
      "id",
      "code",
      "branch",
      "title",
      "description",
      "reference",
      "deadline",
      "item",
    ];
    if (
      !row ||
      fields.some((key) => typeof row[key] !== "string" || !row[key].trim()) ||
      optionalStrings.some(
        (key) => row[key] != null && typeof row[key] !== "string",
      ) ||
      !sectors.some((sector) => sector.key === row.sector) ||
      !statusCatalog.some((status) => status.key === row.status) ||
      ids.has(row.id)
    ) {
      throw new Error("Registro incompatível.");
    }
    ids.add(row.id);
    requisicoesFluxo.validate(row);
  });
  return payload;
}

async function loadRequests() {
  // Recarregar lê o arquivo publicado via API; não solicita sincronização nem consulta ao ERP.
  reloadButton.disabled = true;
  document.querySelector("#setores").setAttribute("aria-busy", "true");
  document
    .querySelectorAll(
      ".toolbar input, .toolbar select, .toolbar button, .results-bar button, .view-toolbar input, .view-toolbar button",
    )
    .forEach((control) => {
      control.disabled = !lastMeta;
    });
  setDataState(
    "loading",
    lastMeta
      ? "Atualizando a leitura da última coleta…"
      : "Carregando a última coleta…",
  );
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const endpointUrl = new URL(
      document.body.dataset.requestsUrl,
      location.href,
    );
    if (endpointUrl.origin !== location.origin) {
      throw new Error("Origem da API não autorizada.");
    }
    const response = await fetch(endpointUrl, {
      signal: controller.signal,
      cache: "no-store",
    });
    if (response.status === 401) {
      window.location.assign("/login?next=" + encodeURIComponent(location.pathname));
      return;
    }
    if (!response.ok) throw new Error("Coleta indisponível.");
    const payload = validatePayload(await response.json());
    requests = payload.requests;
    logDiagnostics(requests, payload.meta);
    // Só oferecer setores presentes na coleta, sem listar departamentos de exemplo.
    const availableSectors = sectors.filter((sector) =>
      requests.some((row) => row.sector === sector.key),
    );
    if (!availableSectors.some((sector) => sector.key === state.sector))
      state.sector = "";
    sectorFilter.innerHTML =
      '<option value="">Todos os setores</option>' +
      availableSectors
        .map(
          (sector) =>
            '<option value="' +
            escapeHtml(sector.key) +
            '">' +
            escapeHtml(sector.label) +
            "</option>",
        )
        .join("");
    sectorFilter.value = state.sector;
    const branches = [...new Set(requests.map((row) => row.branch))].sort(
      (a, b) => a.localeCompare(b, "pt-BR", { numeric: true }),
    );
    if (!branches.includes(state.branch)) state.branch = "";
    branchFilter.innerHTML =
      '<option value="">Todas as filiais</option>' +
      branches
        .map(
          (branch) =>
            `<option value="${escapeHtml(branch)}">${escapeHtml(branch)}</option>`,
        )
        .join("");
    branchFilter.value = state.branch;
    lastMeta = payload.meta;
    loadFailed = false;
    render();
    presentFreshness();
  } catch {
    loadFailed = true;
    setDataState(
      lastMeta ? "warning" : "error",
      lastMeta
        ? `Não foi possível atualizar a leitura. Mantidos os dados recebidos de ${new Date(lastMeta.generatedAt).toLocaleString("pt-BR")}.`
        : "Dados indisponíveis. Aguardando uma coleta válida ou a recuperação da conexão. Tente recarregar.",
    );
    if (!lastMeta) {
      sectorList.replaceChildren();
      emptyState.hidden = true;
      document.querySelector("#results-count").textContent =
        "Não foi possível carregar as requisições.";
      ["metric-total", "metric-sectors", "metric-pending"].forEach((id) => {
        document.getElementById(id).textContent = "—";
      });
    }
  } finally {
    clearTimeout(timeout);
    reloadButton.disabled = false;
    document.querySelector("#setores").setAttribute("aria-busy", "false");
    document
      .querySelectorAll(
        ".toolbar input, .toolbar select, .toolbar button, .results-bar button, .view-toolbar input, .view-toolbar button",
      )
      .forEach((control) => {
        control.disabled = !lastMeta;
      });
  }
}

reloadButton.addEventListener("click", loadRequests);
// O aviso também envelhece em uma aba deixada aberta, sem nova chamada de rede.
setInterval(presentFreshness, 30000);
init();
