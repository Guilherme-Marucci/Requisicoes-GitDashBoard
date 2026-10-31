/* Catálogo visual compartilhado das situações do ERP. */
const requisicoesStatus = Object.freeze([
  { key: "pending", label: "Pendente" },
  { key: "registered", label: "Cadastrado" },
  { key: "partial", label: "Parcial" },
  { key: "quotation", label: "Em cotação" },
  { key: "approved", label: "Aprovado" },
  { key: "rejected", label: "Reprovado" },
  { key: "closed", label: "Baixado" },
  { key: "canceled", label: "Cancelado" },
  { key: "released", label: "Liberado" },
  { key: "unmapped", label: "Não mapeada" },
].map(Object.freeze));
if (typeof module !== "undefined") module.exports = requisicoesStatus;
