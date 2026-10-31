"""Converte os SELECTs nomeados da TV em dados de apresentação seguros."""

from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json

from core.database import consultar


class MappingError(ValueError):
    """Contrato incompleto ou resultado incompatível, sem expor dados da consulta."""


def _text(value):
    """Preserva zeros à esquerda, NULL e precisão; não serializa tipos desconhecidos."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    if isinstance(value, Decimal) and value.is_finite():
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise MappingError("Tipo incompatível em coluna mapeada; revise os tipos do SELECT.")


def _mapear_generico(rows: list[dict], key_cols: tuple[str, ...], field_map: dict[str, str | None]) -> list[dict]:
    """Validador comum: garante registros em dict, chave primária única e campos mapeados."""
    if not key_cols:
        raise MappingError("Chave primária não configurada para este mapeador.")
    if not isinstance(rows, list):
        raise MappingError("O SELECT deve retornar uma lista de registros.")

    result, seen = [], set()
    for original in rows:
        if not isinstance(original, dict) or any(not isinstance(k, str) for k in original):
            raise MappingError("Registro SQL incompatível.")

        row = {k.upper(): v for k, v in original.items()}
        if len(row) != len(original):
            raise MappingError("O SELECT retornou nomes de colunas repetidos.")

        def field(col_name):
            return _text(row.get(col_name.upper())) if col_name else None

        key = tuple(field(col) for col in key_cols)
        if None in key or key in seen:
            raise MappingError(f"Chave {key_cols} ausente ou duplicada no resultado do SELECT.")
        seen.add(key)

        identifier = sha256(json.dumps(key, ensure_ascii=False).encode("utf-8")).hexdigest()
        item = {"id": identifier}
        for attr, col in field_map.items():
            item[attr] = field(col)

        result.append(item)
    return result


# =====================================================================
# 1. TV_SITUAC (Situações de Requisições)
# =====================================================================
STATUS_MAP_SITUAC = {
    "A": "approved",    # Aprovado
    "B": "closed",      # Baixado
    "C": "canceled",    # Cancelado
    "D": "registered",  # Cadastrada
    "L": "partial",     # Parcial
    "P": "pending",     # Pendente
    "R": "rejected",    # Reprovado
}

MAPA_SETORES = {
    "COMPRAS": "compras",
    "CREDITO E COBRANCA": "credito_cobranca",
    "CREDITO E COBRANÇA": "credito_cobranca",
    "FINANCEIRO": "financeiro",
    "ADMINISTRATIVO MATRIZ": "administrativo_matriz",
    "SAC": "sac",
    "JURIDICO": "juridico",
    "JURÍDICO": "juridico",
    "T.I": "ti",
    "TI": "ti",
    "RH": "rh",
    "ARMAZEM": "armazem",
    "ARMAZÉM": "armazem",
    "PROJETOS": "projetos",
    "RECEBIMENTO": "recebimento",
    "LIMPEZA": "limpeza",
    "REINTEGRACAO": "reintegracao",
    "REINTEGRAÇÃO": "reintegracao",
    "MANUTENCAO": "manutencao",
    "MANUTENÇÃO": "manutencao",
    "TRANSPORTE": "transporte",
    "EXPEDICAO": "expedicao",
    "EXPEDIÇÃO": "expedicao",
    "FISCAL": "fiscal",
}


def _canonizar_setor(name: str | None) -> str:
    """Mapeia o nome do setor do ERP (OSESET) para a chave canônica do setor."""
    if not name:
        return "unclassified"
    n = name.upper().strip()
    if n in MAPA_SETORES:
        return MAPA_SETORES[n]
    for chave_nome, slug in MAPA_SETORES.items():
        if chave_nome in n or n in chave_nome:
            return slug
    return "unclassified"


def mapear_tv_situac(rows: list[dict]) -> list[dict]:
    """Mapeia o SELECT de TV_situac.sql (baseado em CODREQ)."""
    field_map = {
        "code": "CODREQ",
        "branch": "CODFIL",
        "reference": "DATATU",
        "inclusionDate": "DATINC",
        "description": "OBSERV",
        "requester": "CODFUN",
        "requesterName": "NOMFUN",
        "firstProduct": "PRI_CODPRO",
        "raw_status": "SITUAC",
        "raw_sector_code": "CODSET",
        "raw_sector_name": "DESCRI_SETOR",
    }
    brutos = _mapear_generico(rows, key_cols=("CODREQ",), field_map=field_map)
    resultado = []
    for item in brutos:
        raw_st = item.pop("raw_status")
        raw_sector_code = item.pop("raw_sector_code", None)
        raw_sector_name = item.pop("raw_sector_name", None)
        first_prod = item.get("firstProduct") or "—"
        code = item["code"] or "—"
        item["code"] = code
        item["status"] = STATUS_MAP_SITUAC.get(raw_st, "unmapped") #NULL contents

        # Setor canônico e descrição do setor
        sector_name = (raw_sector_name or (f"Setor {raw_sector_code}" if raw_sector_code else "Não informado")).strip()
        item["sectorName"] = sector_name
        item["sectorCode"] = raw_sector_code or "—"
        item["sector"] = _canonizar_setor(sector_name)

        item["branch"] = item["branch"] or "Não informada"
        item["title"] = f"Requisição {code}"
        item["description"] = item["description"] or "Não informada"
        ref = item["reference"] or "Não informada"
        item["reference"] = ref
        item["deadline"] = "Não informado"
        item["item"] = f"Item {first_prod}" if first_prod and first_prod != "—" else "Item de requisição"
        item["firstProduct"] = first_prod
        item["requester"] = item["requester"] or "—"

        req_name = item.get("requesterName")
        item["requesterName"] = req_name.strip() if (req_name and isinstance(req_name, str)) else None

        # DATINC representa a data/hora original de inclusão/cadastro
        raw_inc = item.get("inclusionDate")
        if raw_inc and "T" in raw_inc:
            item["createdAt"] = f"{raw_inc}-03:00" if not raw_inc.endswith("Z") and not ("+" in raw_inc[10:] or "-" in raw_inc[10:]) else raw_inc
        elif raw_inc:
            item["createdAt"] = f"{raw_inc}T00:00:00-03:00"
        elif ref and ref != "Não informada" and "T" in ref:
            item["createdAt"] = f"{ref}-03:00" if not ref.endswith("Z") and not ("+" in ref[10:] or "-" in ref[10:]) else ref
        else:
            item["createdAt"] = None

        item["inclusionDate"] = raw_inc
        item["workflow"] = None
        resultado.append(item)
    return resultado


# =====================================================================
# 2. TV_PEDIDOS (Acompanhamento de Pedidos de Compras vinculados a Requisições)
# =====================================================================
STATUS_MAP_PEDIDOS = {
    "A": "approved",    # Aprovado
    "B": "closed",      # Baixado / Atendido
    "C": "canceled",    # Cancelado
    "D": "registered",  # Cadastrado
    "E": "in_transit",  # Em trânsito / Emitido
    "F": "finalized",   # Finalizado / Entregue
    "L": "partial",     # Parcial
    "P": "pending",     # Pendente
    "R": "rejected",    # Reprovado
    "X": "partial",     # Em baixa parcial no cabeçalho do pedido
}


def mapear_tv_pedidos(rows: list[dict]) -> list[dict]:
    """Mapeia o SELECT de TV_pedidos.sql (itens ESTIPE + cabeçalho ESTPED) mantendo compatibilidade legada."""
    if not rows:
        return _mapear_generico(rows, key_cols=("ID_IPE",), field_map={"code": "NUMPED"})

    chaves_disponiveis = {k.upper() for k in rows[0]} if isinstance(rows[0], dict) else set()

    # Contrato principal: granularidade de item de pedido (ESTIPE.ID_IPE + cabeçalho ESTPED)
    if "ID_IPE" in chaves_disponiveis:
        field_map = {
            # 1. Colunas prioritárias
            "idIpe": "ID_IPE",
            "requisitionCode": "CODREQ",
            "orderNumber": "NUMPED",
            "productCode": "CODPROD",
            "qtyOrdered": "QTDPED",
            "unitPrice": "PREUNI",
            "totalPrice": "PRETOT",
            # 2. Demais colunas ESTIPE
            "qtyDelivered": "QTDENT",
            "rawStatus": "SITUAC",
            "updatedAt": "DATATU",
            "updatedBy": "USUATU",
            "description": "DESCRI",
            "qtyCanceled": "QTDCAN",
            "observation": "OBSERV",
            "quoteCode": "CODCOT",
            "icmsSt": "ICMSST",
            # 3. Produto ESTPRO
            "unit": "UNIDAD",
            "reference": "REFERE",
            # 4. Cabeçalho ESTPED + Fornecedor RODCLI
            "branch": "CODFIL",
            "inclusionDate": "DATINC",
            "orderDate": "DATEMI",
            "deliveryDate": "DATENT",
            "orderRawStatus": "SITPED",
            "orderTotalValue": "VALTOT_PED",
            "buyer": "COMPRADOR",
            "supplierCode": "CODCLIFOR",
            "supplierShort": "FORNECEDOR",
            "supplierLegal": "RAZSOC",
        }
        brutos = _mapear_generico(rows, key_cols=("ID_IPE",), field_map=field_map)
        resultado = []
        for item in brutos:
            raw_st = (item.get("rawStatus") or "").strip().upper()
            raw_ped_st = (item.get("orderRawStatus") or "").strip().upper()
            status = STATUS_MAP_PEDIDOS.get(raw_st, "unmapped")
            order_status = STATUS_MAP_PEDIDOS.get(raw_ped_st, status)

            supplier_short = item.pop("supplierShort", None)
            supplier_legal = item.pop("supplierLegal", None)
            supplier_name = supplier_short or supplier_legal or "Fornecedor não informado"

            numped = item.get("orderNumber") or "—"
            pretot = item.get("totalPrice") or "0.00"

            item["code"] = numped
            item["orderNumber"] = numped
            item["requisitionCode"] = item.get("requisitionCode") or "—"
            item["productCode"] = item.get("productCode") or "—"
            item["qtyOrdered"] = item.get("qtyOrdered") or "0"
            item["unitPrice"] = item.get("unitPrice") or "0.00"
            item["totalPrice"] = pretot
            item["totalValue"] = pretot
            item["qtyDelivered"] = item.get("qtyDelivered") or "0"
            item["qtyCanceled"] = item.get("qtyCanceled") or "0"
            item["rawStatus"] = raw_st or "—"
            item["status"] = status
            item["orderRawStatus"] = raw_ped_st or raw_st or "—"
            item["orderStatus"] = order_status
            item["updatedAt"] = item.get("updatedAt") or "—"
            item["updatedBy"] = item.get("updatedBy") or "—"
            item["description"] = item.get("description") or f"Produto {item['productCode']}"
            item["observation"] = item.get("observation") or "—"
            item["quoteCode"] = item.get("quoteCode") or "—"
            item["icmsSt"] = item.get("icmsSt") or "0.00"
            item["unit"] = item.get("unit") or "UN"
            item["reference"] = item.get("reference") or "—"
            item["branch"] = item.get("branch") or "Não informada"
            item["inclusionDate"] = item.get("inclusionDate") or item.get("orderDate") or item["updatedAt"]
            item["orderDate"] = item.get("orderDate") or item["inclusionDate"]
            item["deliveryDate"] = item.get("deliveryDate") or "—"
            item["orderTotalValue"] = item.get("orderTotalValue") or pretot
            item["buyer"] = item.get("buyer") or item["updatedBy"]
            item["supplierCode"] = item.get("supplierCode") or "—"
            item["supplier"] = supplier_name
            resultado.append(item)
        return resultado

    # Compatibilidade preservada para contratos legados por cabeçalho (CODPED ou NUMPED)
    field_map = {
        "code": "CODPED",
        "branch": "CODFIL",
        "requisitionCode": "CODREQ",
        "supplier": "RAZSOC",
        "orderDate": "DATEMI",
        "deliveryDate": "DATENT",
        "buyer": "COMPRADOR",
        "totalValue": "VALTOT",
        "raw_status": "SITPED",
    }
    key_col = "CODPED" if "CODPED" in chaves_disponiveis else "NUMPED"
    if key_col == "NUMPED":
        field_map["code"] = "NUMPED"

    brutos = _mapear_generico(rows, key_cols=(key_col,), field_map=field_map)
    resultado = []
    for item in brutos:
        raw_st = item.pop("raw_status")
        item["status"] = STATUS_MAP_PEDIDOS.get(raw_st, "unmapped")
        item["branch"] = item["branch"] or "Não informada"
        item["requisitionCode"] = item["requisitionCode"] or "—"
        item["supplier"] = item["supplier"] or "Fornecedor não informado"
        item["orderDate"] = item["orderDate"] or "—"
        item["deliveryDate"] = item["deliveryDate"] or "—"
        item["buyer"] = item["buyer"] or "—"
        item["totalValue"] = item["totalValue"] or "0.00"
        resultado.append(item)
    return resultado


# =====================================================================
# 3. TV_NF (Notas Fiscais / Finalizados)
# =====================================================================
STATUS_MAP_NF = {
    "R": "received",    # Recebida
    "C": "inspected",   # Conferida
    "L": "released",    # Liberada / Finalizada
    "F": "finalized",   # Finalizada
    "X": "canceled",    # Cancelada
}

def mapear_tv_nf(rows: list[dict]) -> list[dict]:
    """Mapeia o SELECT de TV_nf.sql (baseado em NUMNF ou combinação com Filial)."""
    field_map = {
        "code": "NUMNF",
        "series": "SERIE",
        "branch": "CODFIL",
        "orderCode": "CODPED",
        "supplier": "RAZSOC",
        "issueDate": "DATEMI",
        "arrivalDate": "DATENT",
        "totalValue": "VALTOT",
        "raw_status": "SITNF",
    }
    # Se houver série, a chave composta é (CODFIL, NUMNF, SERIE); se não, (NUMNF,)
    key_cols = ("NUMNF",)
    if rows:
        chaves_disponiveis = {k.upper() for k in rows[0]}
        if "CODFIL" in chaves_disponiveis and "SERIE" in chaves_disponiveis:
            key_cols = ("CODFIL", "NUMNF", "SERIE")

    brutos = _mapear_generico(rows, key_cols=key_cols, field_map=field_map)
    resultado = []
    for item in brutos:
        raw_st = item.pop("raw_status")
        item["status"] = STATUS_MAP_NF.get(raw_st, "unmapped")
        item["series"] = item["series"] or "1"
        item["branch"] = item["branch"] or "Não informada"
        item["orderCode"] = item["orderCode"] or "—"
        item["supplier"] = item["supplier"] or "Emitente não informado"
        item["issueDate"] = item["issueDate"] or "—"
        item["arrivalDate"] = item["arrivalDate"] or "—"
        item["totalValue"] = item["totalValue"] or "0.00"
        resultado.append(item)
    return resultado


# Catálogo com a parametrização das tabelas da TV e módulos do painel
CONFIG_COLETAS_TV = {
    "requisicoes": {
        "consulta": "requisicoes",
        "mapeador": mapear_tv_situac,
        "arquivo": "requisicoes.json",
        "campo_raiz": "requests",
    },
    "tv_situac": {
        "consulta": "tv_situac",
        "mapeador": mapear_tv_situac,
        "arquivo": "tv_situac.json",
        "campo_raiz": "requests",
    },
    "tv_pedidos": {
        "consulta": "tv_pedidos",
        "mapeador": mapear_tv_pedidos,
        "arquivo": "tv_pedidos.json",
        "campo_raiz": "orders",
    },
}
