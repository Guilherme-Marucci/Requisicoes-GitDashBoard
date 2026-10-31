/* Editor demonstrativo: consultas reutilizáveis, tabelas e exportação sem persistência remota. */
(() => {
  const $ = (id) => document.getElementById(id);
  const draft = new RequisitionModel.Draft();
  const selected = {};
  const attachments = [];
  let editingItem = null;
  let lookupKey = null;
  let dirty = false;
  let pendingItem = false;
  let pendingLocation = false;
  const generalRefs = [
    "filial",
    "funcionario",
    "fornecedor",
    "setor",
    "aprovador",
    "liberador",
    "filialOS",
  ];
  const classificationRefs = [
    "unidadeNegocio",
    "centroGasto",
    "centroCusto",
    "classeSintetica",
    "classeAnalitica",
  ];
  const generalFields = [
    "dataReferencia",
    "dataLimiteEntrega",
    "ordemServico",
    "observacao",
  ];

  // O mapa define a apresentação das consultas, não tabelas nem permissões do ERP.
  // Campos da referência sem valor conhecido continuam nulos; nenhuma identidade real é inventada.
  const situation = (options) => ({
    Situação: { "Valor atual": null, "Opções da referência": options },
  });
  const codeDescription = (code, description, details = {}, unit = null) => ({
    codigo: code,
    descricao: description,
    ...(unit ? { unidade: unit } : {}),
    detalhes: details,
  });
  const basic = (label, code, description) => ({
    label,
    records: [codeDescription(code, description)],
  });
  const userDetails = {
    Login: "usuario.exemplo",
    Nome: "Usuário demonstrativo",
    Status: { "Valor atual": null, "Opções da referência": "Ativo, Inativo" },
    "Cód. de integração": null,
    CPF: null,
  };
  const catalogs = {
    codigo: {
      label: "Código · consulta de referência",
      readonly: true,
      note: "Exemplo da captura. O código da nova requisição permanece não atribuído.",
      records: [
        codeDescription(
          "19867",
          "Aquisição de filme stretch para uso operacional",
          {
            "Situação na captura": "Pendente",
            "Data de referência": "01/10/2026",
          },
        ),
      ],
    },
    filial: {
      label: "Filial",
      records: [
        codeDescription("5", "Filial demonstrativa", {
          "Razão social": "Empresa demonstrativa",
          CNPJ: null,
          "XML MDFe para e-mail": null,
        }),
      ],
    },
    funcionario: {
      label: "Funcionário",
      records: [
        codeDescription("FUNC-DEMO", "Funcionário demonstrativo", {
          Nome: "Funcionário demonstrativo",
          "Setor oficina": null,
          ...situation("Ativo, Inativo"),
          Filial: "5 — Filial demonstrativa",
          "Cliente/fornecedor": null,
        }),
      ],
    },
    fornecedor: {
      label: "Fornecedor",
      records: [
        codeDescription("FORN-DEMO", "Fornecedor demonstrativo", {
          CPF: null,
          Fantasia: "Fornecedor demonstrativo",
          Município: null,
          ...situation("Ativo, Inativo, Bloqueado"),
          Filial: null,
          Estado: null,
          "Razão social": "Fornecedor demonstrativo",
          Classificação: null,
          "Motorista subordinado": null,
          Telefone: null,
          "Nº GFIP": null,
          "Grupo cliente": { Código: null, Descrição: null },
          CEP: null,
          CNPJ: null,
          "Tipo empresa": null,
          Região: null,
          "Telefone 2": null,
          "CUIT/RUIT": null,
          "Cód. terminal": null,
          "Cód. EAN": null,
          Tipo: {
            Código: null,
            Descrição: null,
            Classificação: {
              "Valor atual": null,
              "Opções da referência":
                "Motorista, Veículo, Parceiro, Tabela Frete, OS Manutenção, Cursos/Exames, Fatura",
            },
          },
          Matrícula: null,
        }),
      ],
    },
    setor: {
      ...basic("Setor", "5", "Transporte"),
      note: "Exemplo da captura. A utilização deste campo está pendente de confirmação no mapa fornecido.",
    },
    aprovador: {
      label: "Aprovador indicado",
      note: "A seleção apenas indica um exemplo. Regras de acesso e aprovação dependem da integração.",
      records: [
        codeDescription("APROV-DEMO", "Aprovador demonstrativo", userDetails),
      ],
    },
    liberador: {
      label: "Liberador indicado",
      note: "A seleção apenas indica um exemplo. Regras de acesso e liberação dependem da integração.",
      records: [
        codeDescription("LIB-DEMO", "Liberador demonstrativo", userDetails),
      ],
    },
    unidadeNegocio: {
      label: "Unidade de negócio",
      records: [
        codeDescription("3", "Manaus (AM)", situation("Ativo, Inativo")),
      ],
    },
    centroGasto: basic("Centro de gasto", "2", "Armazenagem"),
    centroCusto: basic("Centro de custo", "2", "Operacionais"),
    classeSintetica: basic(
      "Classificação sintética",
      "226",
      "Custo operacional do armazém",
    ),
    classeAnalitica: basic(
      "Classificação analítica",
      "228",
      "Materiais auxiliares na operação",
    ),
    produto: {
      label: "Produto",
      records: [
        codeDescription(
          "19597",
          "Filme stretch 25 micra 500mm bobina de 4kg",
          {},
          "UN",
        ),
        codeDescription("PROD-DEMO-02", "Fita adesiva — exemplo", {}, "UN"),
      ],
    },
    veiculo: basic("Veículo", "VEIC-DEMO", "Veículo demonstrativo"),
    localizacao: basic("Localização", "LOC-DEMO", "Localização demonstrativa"),
  };
  catalogs.filialOS = { ...catalogs.filial, label: "Filial da O.S." };

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function icon(name) {
    const node = element("i");
    node.dataset.lucide = name;
    return node;
  }
  function action(label, iconName, handler) {
    const button = element("button", undefined, "icon-button");
    button.type = "button";
    button.setAttribute("aria-label", label);
    button.title = label;
    button.append(icon(iconName));
    button.addEventListener("click", handler);
    return button;
  }
  function feedback(message) {
    $("editor-feedback").textContent = message;
  }
  function alertForm(id, message) {
    $(id).hidden = !message;
    $(id).textContent = message;
  }
  function setReference(key, record) {
    // O rascunho transporta uma referência mínima, não CPF/CNPJ ou a árvore inteira de consulta.
    selected[key] = record
      ? {
          codigo: record.codigo,
          descricao: record.descricao,
          ...(record.unidade ? { unidade: record.unidade } : {}),
        }
      : null;
    $(key).value = record ? `${record.codigo} · ${record.descricao}` : "";
    $(key).title = $(key).value;
    $(key).removeAttribute("aria-invalid");
    if (key === "produto") $("unidade").value = record?.unidade || "";
  }
  function markChange(key) {
    dirty = true;
    if (["produto", "veiculo"].includes(key)) pendingItem = true;
    if (key === "localizacao") pendingLocation = true;
  }
  function tree(data) {
    const list = element("dl", undefined, "reference-tree");
    Object.entries(data).forEach(([label, value]) => {
      const group = element("div");
      if (value && typeof value === "object") {
        group.className = "reference-branch";
        const details = element("details");
        details.append(element("summary", label), tree(value));
        group.append(details);
      } else
        group.append(
          element("dt", label),
          element("dd", value ?? "Não informado"),
        );
      list.append(group);
    });
    return list;
  }
  function renderLookup() {
    const catalog = catalogs[lookupKey];
    const normalize = (value) =>
      value
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase();
    const query = normalize($("lookup-search").value.trim());
    const matches = catalog.records.filter((record) =>
      normalize(`${record.codigo} ${record.descricao}`).includes(query),
    );
    $("lookup-results").replaceChildren();
    if (!matches.length)
      $("lookup-results").append(
        element(
          "p",
          "Nenhum exemplo encontrado. Tente outro código ou descrição.",
          "field-note",
        ),
      );
    matches.forEach((record) => {
      const card = element("article", undefined, "lookup-record");
      const header = element("header");
      const title = element("div");
      title.append(
        element("strong", record.descricao),
        element("small", `Código: ${record.codigo} · exemplo`),
      );
      header.append(title);
      if (!catalog.readonly) {
        const choose = element("button", "Selecionar", "clear-button");
        choose.type = "button";
        choose.setAttribute("aria-label", `Selecionar ${record.descricao}`);
        choose.addEventListener("click", () => {
          setReference(lookupKey, record);
          markChange(lookupKey);
          $("lookup-dialog").close();
        });
        header.append(choose);
      }
      const details = element("details");
      details.append(
        element("summary", "Detalhes do cadastro"),
        tree({
          Código: record.codigo,
          Descrição: record.descricao,
          ...record.detalhes,
        }),
      );
      card.append(header, details);
      $("lookup-results").append(card);
    });
  }
  function openLookup(key) {
    lookupKey = key;
    $("lookup-title").textContent = `Consultar ${catalogs[key].label}`;
    $("lookup-note").textContent =
      catalogs[key].note ||
      "Catálogo demonstrativo. Consulte os detalhes e selecione um exemplo.";
    $("lookup-search").value = "";
    renderLookup();
    $("lookup-dialog").showModal();
    $("lookup-search").focus();
  }
  document
    .querySelectorAll("[data-lookup]")
    .forEach((button) =>
      button.addEventListener("click", () => openLookup(button.dataset.lookup)),
    );
  document.querySelectorAll("[data-reference]").forEach((input) => {
    input.addEventListener("click", () => openLookup(input.dataset.reference));
    input.addEventListener("keydown", (event) => {
      if (["Enter", " "].includes(event.key)) {
        event.preventDefault();
        openLookup(input.dataset.reference);
      }
    });
  });
  document.querySelectorAll("[data-clear]").forEach((button) =>
    button.addEventListener("click", () => {
      setReference(button.dataset.clear, null);
      markChange(button.dataset.clear);
    }),
  );
  $("lookup-search").addEventListener("input", renderLookup);
  document
    .querySelectorAll("[data-close]")
    .forEach((button) =>
      button.addEventListener("click", () => $(button.dataset.close).close()),
    );

  function switchTab(key, focus = true) {
    document.querySelectorAll("[data-tab]").forEach((tab) => {
      const active = tab.dataset.tab === key;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      $(tab.getAttribute("aria-controls")).hidden = !active;
      if (active && focus) tab.focus();
    });
  }
  const tabs = [...document.querySelectorAll("[data-tab]")];
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
    tab.addEventListener("keydown", (event) => {
      const next = {
        ArrowRight: (index + 1) % tabs.length,
        ArrowLeft: (index + tabs.length - 1) % tabs.length,
        Home: 0,
        End: tabs.length - 1,
      }[event.key];
      if (next !== undefined) {
        event.preventDefault();
        switchTab(tabs[next].dataset.tab);
      }
    });
  });
  document
    .querySelectorAll("[data-next]")
    .forEach((button) =>
      button.addEventListener("click", () => switchTab(button.dataset.next)),
    );
  document.querySelectorAll("form").forEach((form) =>
    form.addEventListener("input", (event) => {
      dirty = true;
      if (form.id === "item-form") pendingItem = true;
      if (form.id === "location-form") pendingLocation = true;
      event.target.removeAttribute("aria-invalid");
    }),
  );
  $("general-form").addEventListener("submit", (event) =>
    event.preventDefault(),
  );

  function emptyRow(body, columns, message) {
    body.replaceChildren();
    const row = element("tr");
    const cell = element("td", message, "table-empty");
    cell.colSpan = columns;
    row.append(cell);
    body.append(row);
  }
  function productCell(reference) {
    const cell = element("td");
    cell.append(
      element("strong", reference.descricao),
      element("small", reference.codigo),
    );
    return cell;
  }
  function resetItem() {
    $("item-form").reset();
    setReference("produto", null);
    setReference("veiculo", null);
    editingItem = null;
    pendingItem = false;
    $("add-item").replaceChildren(
      icon("plus"),
      document.createTextNode(" Incluir item"),
    );
    $("cancel-item").textContent = "Limpar campos";
    alertForm("item-alert", "");
  }
  function editItem(item) {
    if (
      pendingItem &&
      !window.confirm("Descartar os campos do item em edição?")
    )
      return;
    resetItem();
    editingItem = item.idLocal;
    setReference("produto", item.produto);
    setReference("veiculo", item.veiculo);
    ["quantidade", "valorInformado", "mediaConsumo", "aplicacao"].forEach(
      (key) => {
        $(key).value = item[key] ?? "";
      },
    );
    $("observacaoItem").value = item.observacao || "";
    $("critico").checked = item.critico;
    $("add-item").replaceChildren(
      icon("check"),
      document.createTextNode(" Atualizar item"),
    );
    $("cancel-item").textContent = "Cancelar edição";
    $("produto").focus();
  }
  function renderItems() {
    $("item-count").textContent =
      `${draft.items.length} ${draft.items.length === 1 ? "item" : "itens"}`;
    $("items-caption").textContent = `(${draft.items.length})`;
    const body = $("items-body");
    body.replaceChildren();
    draft.items.forEach((item) => {
      const row = element("tr");
      row.append(
        element("td", item.sequencia),
        productCell(item.produto),
        element("td", item.quantidade),
        element("td", item.unidade),
        element("td", "Não informado"),
        element("td", "Não informado"),
        element("td", item.observacao || "—"),
      );
      const controls = element("div", undefined, "row-actions");
      controls.append(
        action(`Editar item ${item.sequencia}`, "pencil", () => editItem(item)),
        action(`Remover item ${item.sequencia}`, "trash-2", () => {
          const count = draft.locations.filter(
            (location) => location.itemIdLocal === item.idLocal,
          ).length;
          if (
            count &&
            !window.confirm(`Remover o item e suas ${count} localização(ões)?`)
          )
            return;
          draft.removeItem(item.idLocal);
          dirty = true;
          if (editingItem === item.idLocal) resetItem();
          renderItems();
          renderLocations();
          feedback(`Item ${item.sequencia} removido do rascunho.`);
        }),
      );
      const actions = element("td");
      actions.append(controls);
      row.append(actions);
      body.append(row);
    });
    if (!draft.items.length)
      emptyRow(
        body,
        8,
        "Nenhum item incluído. Selecione um produto e informe a quantidade acima.",
      );
    const previous = $("location-item").value;
    const placeholder = element(
      "option",
      draft.items.length ? "Selecione um item" : "Inclua um item primeiro",
    );
    placeholder.value = "";
    $("location-item").replaceChildren(placeholder);
    draft.items.forEach((item) => {
      const option = element(
        "option",
        `${item.sequencia} · ${item.produto.descricao}`,
      );
      option.value = item.idLocal;
      $("location-item").append(option);
    });
    $("location-item").value = draft.items.some(
      (item) => item.idLocal === previous,
    )
      ? previous
      : "";
  }
  $("item-form").addEventListener("submit", (event) => {
    event.preventDefault();
    try {
      if (!$("item-form").reportValidity()) return;
      const item = draft.putItem(
        {
          produto: selected.produto,
          quantidade: $("quantidade").value,
          veiculo: selected.veiculo,
          critico: $("critico").checked,
          valorInformado: $("valorInformado").value,
          mediaConsumo: $("mediaConsumo").value,
          aplicacao: $("aplicacao").value,
          observacao: $("observacaoItem").value,
        },
        editingItem,
      );
      resetItem();
      renderItems();
      renderLocations();
      dirty = true;
      feedback(`Item ${item.sequencia} atualizado no rascunho.`);
    } catch (error) {
      alertForm("item-alert", error.message);
    }
  });
  $("cancel-item").addEventListener("click", resetItem);

  function renderLocations() {
    const body = $("locations-body");
    body.replaceChildren();
    draft.locations.forEach((location) => {
      const item = draft.items.find(
        (candidate) => candidate.idLocal === location.itemIdLocal,
      );
      const row = element("tr");
      row.append(
        element("td", `${item.sequencia} · ${item.produto.descricao}`),
        productCell(location.localizacao),
        element("td", location.quantidade),
      );
      const actions = element("td");
      actions.append(
        action("Remover localização", "trash-2", () => {
          draft.removeLocation(location.idLocal);
          dirty = true;
          renderLocations();
        }),
      );
      row.append(actions);
      body.append(row);
    });
    if (!draft.locations.length)
      emptyRow(body, 4, "Nenhuma localização vinculada aos itens.");
  }
  $("location-form").addEventListener("submit", (event) => {
    event.preventDefault();
    try {
      if (!$("location-form").reportValidity()) return;
      draft.addLocation(
        $("location-item").value,
        selected.localizacao,
        $("quantidadeLocalizacao").value,
      );
      $("location-form").reset();
      setReference("localizacao", null);
      pendingLocation = false;
      dirty = true;
      alertForm("location-alert", "");
      renderLocations();
      feedback("Localização incluída no rascunho.");
    } catch (error) {
      alertForm("location-alert", error.message);
    }
  });
  $("cancel-location").addEventListener("click", () => {
    $("location-form").reset();
    setReference("localizacao", null);
    pendingLocation = false;
    alertForm("location-alert", "");
  });

  let previewUrl = null;
  function previewAttachment(file) {
    previewUrl = URL.createObjectURL(file);
    $("attachment-title").textContent = file.name;
    const pdf = /\.pdf$/i.test(file.name);
    const preview = element(pdf ? "iframe" : "img");
    if (pdf) {
      preview.setAttribute("sandbox", "");
      preview.title = `Prévia de ${file.name}`;
    } else preview.alt = file.name;
    preview.src = previewUrl;
    $("attachment-preview").replaceChildren(preview);
    if (pdf)
      $("attachment-preview").append(
        element(
          "p",
          "Se o navegador não exibir o PDF, baixe o arquivo original pelo link abaixo.",
          "field-note",
        ),
      );
    $("attachment-download").href = previewUrl;
    $("attachment-download").download = file.name;
    $("attachment-dialog").showModal();
  }
  $("attachment-dialog").addEventListener("close", () => {
    $("attachment-preview").replaceChildren();
    $("attachment-download").removeAttribute("href");
    URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  });

  function renderAttachments() {
    const body = $("attachments-body");
    body.replaceChildren();
    attachments.forEach((attachment) => {
      const row = element("tr");
      row.append(
        element("td", attachment.file.name),
        element(
          "td",
          `${(attachment.file.size / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} KB`,
        ),
      );
      const actions = element("td");
      const controls = element("div", undefined, "row-actions");
      controls.append(
        action(`Visualizar ${attachment.file.name}`, "eye", () =>
          previewAttachment(attachment.file),
        ),
        action(`Remover ${attachment.file.name}`, "trash-2", () => {
          attachments.splice(attachments.indexOf(attachment), 1);
          dirty = true;
          renderAttachments();
        }),
      );
      actions.append(controls);
      row.append(actions);
      body.append(row);
    });
    if (!attachments.length) emptyRow(body, 3, "Nenhum arquivo selecionado.");
  }
  $("attachment-files").addEventListener("change", (event) => {
    const errors = [];
    [...event.target.files].forEach((file) => {
      if (
        !/\.(pdf|png|jpe?g)$/i.test(file.name) ||
        file.size > 10 * 1024 * 1024
      ) {
        errors.push(`${file.name}: selecione PDF, PNG ou JPEG de até 10 MB.`);
        return;
      }
      if (
        attachments.some(
          (attachment) =>
            attachment.file.name === file.name &&
            attachment.file.size === file.size &&
            attachment.file.lastModified === file.lastModified,
        )
      )
        return;
      attachments.push({ id: crypto.randomUUID(), file });
      dirty = true;
    });
    alertForm("attachment-alert", errors.join(" "));
    event.target.value = "";
    renderAttachments();
  });

  function snapshot() {
    const general = Object.fromEntries(
      generalRefs.map((key) => [key, selected[key] || null]),
    );
    generalFields.forEach((key) => {
      general[key] = $(key).value.trim() || null;
    });
    general.tipo = $("tipo").value;
    general.tipoRequisicao = null;
    const classification = Object.fromEntries(
      classificationRefs.map((key) => [key, selected[key] || null]),
    );
    return draft.snapshot(
      general,
      classification,
      attachments.map(({ id, file }) => ({
        idLocal: id,
        nome: file.name,
        tamanhoBytes: file.size,
        tipoInformado: file.type || null,
        enviado: false,
      })),
    );
  }
  function review() {
    const errors = [];
    ["filial", "tarefa", "funcionario"].forEach((key) => {
      if (!selected[key])
        errors.push(`Selecione ${catalogs[key].label.toLowerCase()} em Geral.`);
    });
    if (!$("dataReferencia").value)
      errors.push("Informe a data de referência em Geral.");
    if (!$("observacao").value.trim())
      errors.push("Descreva a necessidade no campo Observação em Geral.");
    if (!draft.items.length)
      errors.push("Inclua ao menos um item na aba Itens.");
    if (pendingItem)
      errors.push(
        "Há campos de um item ainda não incluídos/atualizados na tabela.",
      );
    if (pendingLocation)
      errors.push("Há uma localização ainda não incluída na tabela.");
    $("review-message").textContent = errors.length
      ? "Confira os pontos abaixo para completar este modelo:"
      : "Rascunho conferido para revisão. Você pode baixar o modelo; nenhum registro foi enviado ao ERP.";
    const list = element("ul");
    (errors.length
      ? errors
      : [
          `${draft.items.length} item(ns) incluído(s).`,
          `${draft.locations.length} localização(ões) vinculada(s).`,
          `${attachments.length} anexo(s) selecionado(s); somente os metadados entram no JSON.`,
        ]
    ).forEach((text) => list.append(element("li", text)));
    $("review-content").replaceChildren(list);
    const model = element("details");
    model.append(
      element("summary", "Visualizar modelo JSON"),
      element("pre", JSON.stringify(snapshot(), null, 2), "model-preview"),
    );
    $("review-content").append(model);
    $("review-dialog").showModal();
  }
  function download() {
    // Impede exportar silenciosamente uma versão anterior de um item/localização em edição.
    if (pendingItem || pendingLocation) {
      if ($("review-dialog").open) $("review-dialog").close();
      review();
      return;
    }
    const blob = new Blob([JSON.stringify(snapshot(), null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = element("a");
    link.href = url;
    link.download = "requisicao-rascunho.json";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    feedback(
      "Modelo JSON gerado. Os arquivos anexados não fazem parte do download; mantenha os originais.",
    );
  }
  $("review-draft").addEventListener("click", review);
  $("download-draft").addEventListener("click", download);
  $("review-download").addEventListener("click", download);
  window.addEventListener("beforeunload", (event) => {
    if (dirty) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  const today = new Date();
  $("dataReferencia").value =
    `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  renderItems();
  renderLocations();
  renderAttachments();
})();
