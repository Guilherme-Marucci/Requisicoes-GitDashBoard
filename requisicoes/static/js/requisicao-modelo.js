/* Modelo do rascunho local. Não traduz campos nem situações para o contrato do ERP. */
((root) => {
  function decimal(value, label, positive = false) {
    const text = String(value ?? "").trim().replace(",", ".");
    if (!text && !positive) return null;
    if (!/^\d+(\.\d+)?$/.test(text) || !Number.isFinite(Number(text)) || (positive && Number(text) <= 0)) {
      throw new Error(`${label}: informe um número ${positive ? "maior que zero" : "igual ou maior que zero"}.`);
    }
    // O transporte conserva decimais como texto; moeda, escala e arredondamento dependem do contrato.
    return text;
  }

  class Draft {
    constructor() {
      this.id = root.crypto.randomUUID();
      this.items = [];
      this.locations = [];
      this.nextSequence = 1;
    }

    putItem(input, id = null) {
      if (!input.produto?.codigo) throw new Error("Selecione um produto na consulta.");
      const index = id ? this.items.findIndex((item) => item.idLocal === id) : -1;
      if (id && index < 0) throw new Error("O item não foi encontrado. Inicie uma nova inclusão.");
      // Trocar o produto invalidaria a referência das localizações já distribuídas.
      if (id && this.locations.some((row) => row.itemIdLocal === id) && this.items[index].produto.codigo !== input.produto.codigo) {
        throw new Error("Remova as localizações deste item antes de trocar o produto.");
      }
      const item = {
        idLocal: id || root.crypto.randomUUID(),
        sequencia: id ? this.items[index].sequencia : this.nextSequence,
        produto: structuredClone(input.produto),
        quantidade: decimal(input.quantidade, "Quantidade", true),
        unidade: input.produto.unidade || null,
        veiculo: input.veiculo ? structuredClone(input.veiculo) : null,
        critico: Boolean(input.critico),
        valorInformado: decimal(input.valorInformado, "Valor informado"),
        mediaConsumo: decimal(input.mediaConsumo, "Média de consumo"),
        aplicacao: input.aplicacao?.trim() || null,
        observacao: input.observacao?.trim() || null,
        situacaoERP: null, cotado: null, pedido: null,
      };
      if (id) this.items[index] = item;
      else { this.items.push(item); this.nextSequence += 1; }
      return item;
    }

    removeItem(id) {
      this.items = this.items.filter((item) => item.idLocal !== id);
      this.locations = this.locations.filter((row) => row.itemIdLocal !== id);
    }

    addLocation(itemId, reference, quantity) {
      if (!this.items.some((item) => item.idLocal === itemId)) throw new Error("Selecione um item incluído na requisição.");
      if (!reference?.codigo) throw new Error("Selecione uma localização na consulta.");
      const row = { idLocal: root.crypto.randomUUID(), itemIdLocal: itemId,
        localizacao: structuredClone(reference), quantidade: decimal(quantity, "Quantidade", true) };
      this.locations.push(row);
      return row;
    }

    removeLocation(id) { this.locations = this.locations.filter((row) => row.idLocal !== id); }

    snapshot(general, classification, attachments) {
      // Baixas/cotações nulas significam estrutura não definida; não são registros vazios homologados.
      return structuredClone({ versaoModelo: 1, demonstrativo: true, idLocal: this.id,
        estadoPortal: "rascunho", codigoERP: null, situacaoERP: null,
        geral: general, classificacao: classification, itens: this.items,
        localizacoes: this.locations, anexos: attachments, baixas: null, cotacoes: null,
        auditoriaERP: { incluidoEm: null, incluidoPor: null, atualizadoEm: null, atualizadoPor: null,
          aprovadoEm: null, aprovadoPor: null, liberadoEm: null, liberadoPor: null } });
    }
  }
  const api = { Draft, decimal };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.RequisitionModel = api;
})(globalThis);
