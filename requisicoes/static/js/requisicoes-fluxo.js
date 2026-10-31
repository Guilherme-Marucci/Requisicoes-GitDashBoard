/* Regras de apresentação do fluxo oficial por situação do ERP (da esquerda para direita). */
const requisicoesFluxo = (() => {
  const stages = Object.freeze(
    [
      { key: "pending", label: "Pendente" },
      { key: "registered", label: "Cadastrado" },
      { key: "partial", label: "Parcial" },
      { key: "quotation", label: "Em cotação" },
      { key: "approved", label: "Aprovado" },
      { key: "rejected", label: "Reprovado" },
      { key: "closed", label: "Baixado" },
      { key: "canceled", label: "Cancelado" },
    ].map(Object.freeze),
  );

  const validStageKeys = new Set([
    ...stages.map((s) => s.key),
    "request",
    "approval",
    "execution",
    "invoice",
    "payment",
    "unclassified",
  ]);

  const stageKey = (row) => {
    if (row.workflow?.stage) {
      const s = row.workflow.stage;
      if (stages.some((st) => st.key === s)) return s;
      if (s === "request") return "registered";
      if (s === "approval") return "approved";
      if (s === "execution") return "partial";
    }
    if (row.status && stages.some((st) => st.key === row.status)) {
      return row.status;
    }
    return "unclassified";
  };

  const stageLabel = (key) =>
    stages.find((stage) => stage.key === key)?.label ||
    (typeof requisicoesStatus !== "undefined"
      ? requisicoesStatus.find((st) => st.key === key)?.label
      : null) ||
    "Etapa não informada";

  const needsAttention = (row) =>
    row.status === "pending" || Boolean(row.workflow?.attention);
  const dateValid = (value) =>
    typeof value === "string" &&
    /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value));
  const textValid = (value) =>
    typeof value === "string" && Boolean(value.trim());

  function validate(row) {
    if (row.createdAt != null && !dateValid(row.createdAt))
      throw new Error("Data de cadastro inválida.");
    if (row.requester != null && typeof row.requester !== "string")
      throw new Error("Solicitante inválido.");
    const flow = row.workflow;
    if (flow == null) return;
    if (
      typeof flow !== "object" ||
      Array.isArray(flow) ||
      Object.keys(flow).some(
        (key) =>
          !["stage", "attention", "estimatedValue", "history"].includes(key),
      )
    )
      throw new Error("Fluxo inválido.");
    if (flow.stage != null && !validStageKeys.has(flow.stage))
      throw new Error("Etapa inválida.");
    if (flow.attention != null && !textValid(flow.attention))
      throw new Error("Pendência inválida.");
    if (
      flow.estimatedValue != null &&
      (typeof flow.estimatedValue !== "string" ||
        !/^\d{1,12}\.\d{2}$/.test(flow.estimatedValue))
    )
      throw new Error("Valor previsto inválido.");
    if (flow.history != null) {
      if (!Array.isArray(flow.history)) throw new Error("Histórico inválido.");
      for (const event of flow.history) {
        if (
          !event ||
          typeof event !== "object" ||
          Array.isArray(event) ||
          Object.keys(event).sort().join(",") !== "action,actor,at,stage" ||
          !dateValid(event.at) ||
          !textValid(event.action) ||
          (event.actor !== null && !textValid(event.actor)) ||
          !validStageKeys.has(event.stage)
        )
          throw new Error("Evento inválido.");
      }
    }
  }

  let lastUnclassifiedSignature = "";

  function group(rows) {
    const list = stages.map((stage) => ({
      ...stage,
      items: rows.filter((row) => stageKey(row) === stage.key),
    }));

    const unclassified = rows.filter(
      (row) => stageKey(row) === "unclassified",
    );
    const signature = unclassified.map((r) => r.code).join(",");
    if (unclassified.length > 0 && signature !== lastUnclassifiedSignature) {
      lastUnclassifiedSignature = signature;
      // Informativos de registros "Não mapeada" ficam restritos ao console para manter a interface limpa.
      console.warn(
        `[Requisições · Fluxo] ${unclassified.length} requisição(ões) com situação "Não mapeada":`,
        unclassified.map((r) => r.code),
      );
    } else if (unclassified.length === 0) {
      lastUnclassifiedSignature = "";
    }

    // Exibir no fluxo da esquerda para direita:
    // 1 - Pendente, 2 - Cadastrado, 3 - Parcial, 4 - Em cotação, 5 - Aprovado, 6 - Reprovado, 7 - Baixado, 8 - Cancelado
    // 'partial' e 'quotation' só são exibidos se tiverem >= 1 item ativo
    return list.filter((column) => {
      if (column.key === "partial" || column.key === "quotation") {
        return column.items.length >= 1;
      }
      return true;
    });
  }

  // Ordena uma cópia dos eventos recebidos. Não inventa passagens por etapas anteriores.
  const history = (row) =>
    [...(row.workflow?.history || [])].sort(
      (a, b) => Date.parse(a.at) - Date.parse(b.at),
    );

  return Object.freeze({
    stages,
    stageKey,
    stageLabel,
    needsAttention,
    validate,
    group,
    history,
  });
})();

if (typeof module !== "undefined") module.exports = requisicoesFluxo;
