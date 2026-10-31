/* Módulo de cálculo e apresentação dos Gráficos de Ranking (Top Requerentes, Top Setores, Top Itens) */
const requisicoesRankings = (() => {
  function calcularTopRequerentes(requests, limit = 10) {
    const total = requests.length;
    if (!total) return [];
    const counts = new Map();
    const names = new Map();
    for (const r of requests) {
      const code = String(r.requester || "—").trim();
      const name = String(r.requesterName || "").trim();
      if (code && code !== "—") {
        counts.set(code, (counts.get(code) || 0) + 1);
        if (!names.has(code) && name) {
          names.set(code, name);
        }
      }
    }
    return Array.from(counts.entries())
      .map(([code, count]) => {
        const name = names.get(code) || `Requerente ${code}`;
        return {
          code,
          name,
          label: name,
          count,
          percentage: ((count / total) * 100).toFixed(1),
        };
      })
      .sort((a, b) => b.count - a.count || (Number(a.code) || 0) - (Number(b.code) || 0))
      .slice(0, limit);
  }

  function calcularTopSetores(requests, limit = 10) {
    const total = requests.length;
    if (!total) return [];
    const counts = new Map();
    const names = new Map();
    for (const r of requests) {
      let code = String(r.sectorCode || "").trim();
      if (!code || code === "—") {
        code = String(r.sectorName || r.sector || "—").trim();
      }
      const name = String(r.sectorName || (code ? `Setor ${code}` : "Não informado")).trim();
      if (code && code !== "—") {
        counts.set(code, (counts.get(code) || 0) + 1);
        if (!names.has(code) || (name && name !== `Setor ${code}`)) {
          names.set(code, name);
        }
      }
    }
    return Array.from(counts.entries())
      .map(([code, count]) => ({
        code,
        name: names.get(code) || `Setor ${code}`,
        label: names.get(code) || `Setor ${code}`,
        count,
        percentage: ((count / total) * 100).toFixed(1),
      }))
      .sort((a, b) => b.count - a.count || (Number(a.code) || 0) - (Number(b.code) || 0))
      .slice(0, limit);
  }

  function calcularTopItens(requests, limit = 10) {
    const total = requests.length;
    if (!total) return [];
    const counts = new Map();
    const labels = new Map();
    for (const r of requests) {
      const code = String(r.firstProduct || "—").trim();
      const label = String(r.item || `Item ${code}`).trim();
      if (code && code !== "—") {
        counts.set(code, (counts.get(code) || 0) + 1);
        if (!labels.has(code) || (label && label !== `Item ${code}`)) {
          labels.set(code, label);
        }
      }
    }
    return Array.from(counts.entries())
      .map(([code, count]) => ({
        code,
        name: labels.get(code) || `Item ${code}`,
        label: `Item ${code}`,
        count,
        percentage: ((count / total) * 100).toFixed(1),
      }))
      .sort((a, b) => b.count - a.count || (Number(a.code) || 0) - (Number(b.code) || 0))
      .slice(0, limit);
  }

  function calcularRankings(requests, limit = 10) {
    return {
      topRequerentes: calcularTopRequerentes(requests, limit),
      topSetores: calcularTopSetores(requests, limit),
      topItens: calcularTopItens(requests, limit),
      total: requests.length,
    };
  }

  function renderCard(items, title, icon, barColor, emptyMessage = "Nenhum dado registrado.") {
    const max = items.length > 0 ? Math.max(1, ...items.map((i) => i.count)) : 1;
    const itemsHtml = items.length
      ? items
          .map((item, idx) => {
            const widthPct = Math.min(
              100,
              Math.max(0, Math.round((Number(item.count) / max) * 100) || 0),
            );
            return `
            <div class="ranking-item">
              <div class="ranking-item__info">
                <span class="ranking-item__label">
                  <span class="ranking-item__rank">#${idx + 1}</span>
                  <strong>${escapeHtml(item.name || item.label)}</strong>
                  <small class="ranking-item__code">Cód. ${escapeHtml(item.code)}</small>
                </span>
                <span class="ranking-item__metrics">
                  <strong>${new Intl.NumberFormat("pt-BR").format(Number(item.count) || 0)}</strong> reqs
                  <span class="ranking-item__pct">(${escapeHtml(item.percentage)}%)</span>
                </span>
              </div>
              <div class="ranking-item__bar" aria-hidden="true">
                <div class="ranking-item__fill" style="width: ${widthPct}%; background: ${escapeHtml(barColor)};"></div>
              </div>
            </div>`;
          })
          .join("")
      : `<p class="ranking-empty">${escapeHtml(emptyMessage)}</p>`;

    return `
      <section class="ranking-card" aria-label="${escapeHtml(title)}">
        <header class="ranking-card__header">
          <div class="ranking-card__title">
            <i data-lucide="${escapeHtml(icon)}" aria-hidden="true"></i>
            <h3>${escapeHtml(title)}</h3>
          </div>
          <span class="ranking-card__badge">${items.length} classificados</span>
        </header>
        <div class="ranking-list">
          ${itemsHtml}
        </div>
      </section>`;
  }

  function renderGrid(requests) {
    const data = calcularRankings(requests, 8);
    const html = `
      <div class="rankings-grid">
        ${renderCard(
          data.topRequerentes,
          "Top Requerentes",
          "users",
          "var(--accent, #6366f1)",
          "Nenhum requerente identificado nesta seleção."
        )}
        ${renderCard(
          data.topSetores,
          "Top Setores",
          "layers",
          "var(--accent-strong, #3b82f6)",
          "Nenhum setor identificado nesta seleção."
        )}
        ${renderCard(
          data.topItens,
          "Top Itens Solicitados",
          "package",
          "#f59e0b",
          "Nenhum item identificado nesta seleção."
        )}
      </div>`;
    return html;
  }

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
        })[ch]
    );
  }

  return Object.freeze({
    calcularTopRequerentes,
    calcularTopSetores,
    calcularTopItens,
    calcularRankings,
    renderCard,
    renderGrid,
  });
})();

if (typeof module !== "undefined") {
  module.exports = requisicoesRankings;
}
