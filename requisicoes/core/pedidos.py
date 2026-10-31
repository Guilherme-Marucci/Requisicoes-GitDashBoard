"""Regras de filtragem, paginação e agregação financeira de Pedidos (ESTIPE / ESTPED)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import unicodedata

MONTH_NAMES_PT = (
    "",
    "Jan",
    "Fev",
    "Mar",
    "Abr",
    "Mai",
    "Jun",
    "Jul",
    "Ago",
    "Set",
    "Out",
    "Nov",
    "Dez",
)

STATUS_LABELS_PT = {
    "pending": "Pendente",
    "registered": "Cadastrado",
    "partial": "Parcial",
    "approved": "Aprovado",
    "in_transit": "Em trânsito",
    "closed": "Baixado",
    "finalized": "Finalizado",
    "rejected": "Reprovado",
    "canceled": "Cancelado",
    "unmapped": "Não mapeado",
}

INACTIVE_STATUSES = {"canceled", "rejected"}
FULFILLED_STATUSES = {"closed", "finalized"}
PENDING_FLOW_STATUSES = {"pending", "registered", "partial", "approved", "in_transit"}


def _to_decimal(value) -> Decimal:
    if value is None or value == "" or value == "—":
        return Decimal("0")
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _normalize_search(text: str) -> str:
    normalized = unicodedata.normalize("NFD", str(text or ""))
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").lower()


def _extract_iso_timestamp(item: dict) -> str:
    """Retorna a melhor estampa cronológica disponível priorizando DATINC do cabeçalho ESTPED."""
    for field in ("inclusionDate", "orderDate", "updatedAt"):
        raw = str(item.get(field) or "").strip()
        if raw and raw != "—" and len(raw) >= 10 and raw[:4].isdigit():
            return raw
    return ""


def _extract_date_only(item: dict) -> str | None:
    ts = _extract_iso_timestamp(item)
    return ts[:10] if len(ts) >= 10 else None


def _previous_year_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return (year - 1, 12)
    return (year, month - 1)


def _format_month_label(year: int, month: int) -> str:
    name = MONTH_NAMES_PT[month] if 1 <= month <= 12 else f"{month:02d}"
    return f"{name}/{year}"


def available_branches(items: list[dict]) -> list[str]:
    branches = {
        str(row.get("branch") or "").strip()
        for row in items
        if row.get("branch") and str(row.get("branch")).strip() not in {"", "—", "Não informada"}
    }
    return sorted(branches, key=lambda b: (0, int(b)) if b.isdigit() else (1, b))


def filtrar_pedidos(
    items: list[dict],
    *,
    filial: str = "",
    data_inicio: str = "",
    data_fim: str = "",
    status: str = "",
    q: str = "",
    ordenar: str = "datinc_desc",
) -> list[dict]:
    """Filtra e ordena itens de pedido sem mutar a lista original."""
    filial = (filial or "").strip()
    data_inicio = (data_inicio or "").strip()
    data_fim = (data_fim or "").strip()
    status = (status or "").strip()
    query = _normalize_search(q.strip()) if q else ""

    filtered = []
    for row in items:
        if filial and str(row.get("branch") or "").strip() != filial:
            continue
        if status and str(row.get("status") or "").strip() != status:
            continue
        if data_inicio or data_fim:
            row_date = _extract_date_only(row)
            if not row_date:
                continue
            if data_inicio and row_date < data_inicio:
                continue
            if data_fim and row_date > data_fim:
                continue
        if query:
            haystack = _normalize_search(
                " ".join(
                    str(row.get(k) or "")
                    for k in (
                        "idIpe",
                        "requisitionCode",
                        "orderNumber",
                        "code",
                        "productCode",
                        "description",
                        "supplier",
                        "observation",
                        "quoteCode",
                    )
                )
            )
            if query not in haystack:
                continue
        filtered.append(row)

    def sort_key_datinc(r: dict):
        ts = _extract_iso_timestamp(r)
        numped = int(r["orderNumber"]) if str(r.get("orderNumber", "")).isdigit() else 0
        id_ipe = int(r["idIpe"]) if str(r.get("idIpe", "")).isdigit() else 0
        return (ts, numped, id_ipe)

    if ordenar == "datinc_asc":
        filtered.sort(key=sort_key_datinc)
    elif ordenar == "valor_desc":
        filtered.sort(key=lambda r: (_to_decimal(r.get("totalPrice") or r.get("totalValue")), sort_key_datinc(r)), reverse=True)
    elif ordenar == "valor_asc":
        filtered.sort(key=lambda r: (_to_decimal(r.get("totalPrice") or r.get("totalValue")), sort_key_datinc(r)))
    elif ordenar == "numped_desc":
        filtered.sort(
            key=lambda r: (
                int(r["orderNumber"]) if str(r.get("orderNumber", "")).isdigit() else 0,
                int(r["idIpe"]) if str(r.get("idIpe", "")).isdigit() else 0,
            ),
            reverse=True,
        )
    else:
        # Padrão: ordenação cronológica real decrescente por DATINC
        filtered.sort(key=sort_key_datinc, reverse=True)

    return filtered


def paginar_pedidos(items: list[dict], page: int = 1, per_page: int = 50) -> dict:
    """Aplica paginação segura sobre a lista já filtrada e ordenada."""
    page = max(1, int(page or 1))
    per_page = min(200, max(1, int(per_page or 50)))
    total_items = len(items)
    distinct_orders = len({str(r.get("orderNumber") or r.get("code") or "") for r in items if (r.get("orderNumber") or r.get("code"))})
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages

    start = (page - 1) * per_page
    end = start + per_page
    return {
        "pagination": {
            "page": page,
            "perPage": per_page,
            "totalItems": total_items,
            "totalOrders": distinct_orders,
            "totalPages": total_pages,
            "hasNext": page < total_pages,
            "hasPrev": page > 1,
        },
        "items": items[start:end],
    }


def calcular_metricas_pedidos(items: list[dict], *, reference_month: tuple[int, int] | None = None) -> dict:
    """Calcula KPIs financeiros, taxa de atendimento, comparativo mensal e distribuição por status."""
    gross_total = Decimal("0")
    total_purchased = Decimal("0")
    canceled_total = Decimal("0")

    all_orders: set[str] = set()
    active_orders: set[str] = set()
    pending_orders: set[str] = set()
    strictly_pending_orders: set[str] = set()

    active_items_count = 0
    fulfilled_items_count = 0
    pending_delivery_items_count = 0

    qty_ordered_net = Decimal("0")
    qty_delivered_total = Decimal("0")

    monthly_buckets: dict[tuple[int, int], dict] = defaultdict(
        lambda: {"total": Decimal("0"), "orders": set(), "itemsCount": 0}
    )
    status_buckets: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "orders": set(), "totalValue": Decimal("0"), "rawCodes": set()}
    )

    latest_item = None
    latest_sort_tuple = ("", 0, 0)

    for row in items:
        order_no = str(row.get("orderNumber") or row.get("code") or "—").strip()
        status = str(row.get("status") or "unmapped").strip()
        raw_status = str(row.get("rawStatus") or "—").strip()
        item_total = _to_decimal(row.get("totalPrice") if row.get("totalPrice") is not None else row.get("totalValue"))
        qty_ped = _to_decimal(row.get("qtyOrdered"))
        qty_can = _to_decimal(row.get("qtyCanceled"))
        qty_ent = _to_decimal(row.get("qtyDelivered"))

        gross_total += item_total
        if order_no and order_no != "—":
            all_orders.add(order_no)

        # Agrupamento por status (inclui todos os status para transparência da distribuição)
        st_bucket = status_buckets[status]
        st_bucket["count"] += 1
        st_bucket["totalValue"] += item_total
        if order_no and order_no != "—":
            st_bucket["orders"].add(order_no)
        if raw_status and raw_status != "—":
            st_bucket["rawCodes"].add(raw_status)

        # Identifica o último pedido registrado pela data cronológica (DATINC) e maior NUMPED
        ts = _extract_iso_timestamp(row)
        numped_int = int(order_no) if order_no.isdigit() else 0
        id_ipe_int = int(row["idIpe"]) if str(row.get("idIpe", "")).isdigit() else 0
        candidate_tuple = (ts, numped_int, id_ipe_int)
        if latest_item is None or candidate_tuple > latest_sort_tuple:
            latest_sort_tuple = candidate_tuple
            latest_item = row

        if status in INACTIVE_STATUSES:
            canceled_total += item_total
            continue

        # Itens ativos (compras efetivas / em andamento)
        active_items_count += 1
        total_purchased += item_total
        if order_no and order_no != "—":
            active_orders.add(order_no)

        net_qty = max(Decimal("0"), qty_ped - qty_can)
        delivered_capped = min(net_qty, max(Decimal("0"), qty_ent)) if net_qty > 0 else max(Decimal("0"), qty_ent)
        qty_ordered_net += net_qty
        qty_delivered_total += delivered_capped

        is_fulfilled = status in FULFILLED_STATUSES or (net_qty > 0 and qty_ent >= net_qty)
        if is_fulfilled:
            fulfilled_items_count += 1
        else:
            pending_delivery_items_count += 1
            if order_no and order_no != "—":
                pending_orders.add(order_no)
            if status in {"pending", "registered"} and order_no and order_no != "—":
                strictly_pending_orders.add(order_no)

        date_only = _extract_date_only(row)
        if date_only and len(date_only) >= 7:
            try:
                yr = int(date_only[:4])
                mo = int(date_only[5:7])
                mb = monthly_buckets[(yr, mo)]
                mb["total"] += item_total
                mb["itemsCount"] += 1
                if order_no and order_no != "—":
                    mb["orders"].add(order_no)
            except ValueError:
                pass

    active_orders_count = len(active_orders)
    avg_ticket = (total_purchased / Decimal(active_orders_count)) if active_orders_count > 0 else Decimal("0")

    if active_items_count > 0:
        fulfilled_pct = round(float((Decimal(fulfilled_items_count) / Decimal(active_items_count)) * Decimal("100")), 1)
        pending_pct = round(100.0 - fulfilled_pct, 1)
    else:
        fulfilled_pct = 0.0
        pending_pct = 0.0

    qty_pending_total = max(Decimal("0"), qty_ordered_net - qty_delivered_total)

    # Determina o mês de referência (explícito, maior mês nos dados ou data atual)
    if reference_month is not None:
        cur_year, cur_month = reference_month
    elif monthly_buckets:
        cur_year, cur_month = max(monthly_buckets.keys())
    else:
        now = datetime.now()
        cur_year, cur_month = now.year, now.month

    prev_year, prev_month = _previous_year_month(cur_year, cur_month)

    cur_data = monthly_buckets.get((cur_year, cur_month), {"total": Decimal("0"), "orders": set(), "itemsCount": 0})
    prev_data = monthly_buckets.get((prev_year, prev_month), {"total": Decimal("0"), "orders": set(), "itemsCount": 0})

    cur_total = cur_data["total"]
    prev_total = prev_data["total"]
    delta_val = cur_total - prev_total
    delta_pct = (
        round(float((delta_val / prev_total) * Decimal("100")), 1)
        if prev_total > Decimal("0")
        else None
    )

    # Garante ao menos mês anterior e mês atual na série cronológica
    series_keys = sorted(set(monthly_buckets.keys()) | {(prev_year, prev_month), (cur_year, cur_month)})
    monthly_series = [
        {
            "period": f"{yr:04d}-{mo:02d}",
            "label": _format_month_label(yr, mo),
            "total": round(float(monthly_buckets[(yr, mo)]["total"]), 2) if (yr, mo) in monthly_buckets else 0.0,
            "ordersCount": len(monthly_buckets[(yr, mo)]["orders"]) if (yr, mo) in monthly_buckets else 0,
            "itemsCount": monthly_buckets[(yr, mo)]["itemsCount"] if (yr, mo) in monthly_buckets else 0,
        }
        for yr, mo in series_keys
    ]

    total_all_items = len(items)
    status_distribution = [
        {
            "status": st_key,
            "label": STATUS_LABELS_PT.get(st_key, st_key),
            "rawCodes": sorted(bucket["rawCodes"]),
            "itemsCount": bucket["count"],
            "ordersCount": len(bucket["orders"]),
            "totalValue": round(float(bucket["totalValue"]), 2),
            "percentage": round((bucket["count"] / total_all_items) * 100, 1) if total_all_items > 0 else 0.0,
        }
        for st_key, bucket in sorted(
            status_buckets.items(),
            key=lambda kv: (kv[1]["totalValue"], kv[1]["count"]),
            reverse=True,
        )
    ]

    latest_order_summary = None
    if latest_item is not None:
        latest_order_summary = {
            "orderNumber": str(latest_item.get("orderNumber") or latest_item.get("code") or "—"),
            "requisitionCode": str(latest_item.get("requisitionCode") or "—"),
            "supplier": str(latest_item.get("supplier") or "—"),
            "branch": str(latest_item.get("branch") or "—"),
            "inclusionDate": str(latest_item.get("inclusionDate") or latest_item.get("orderDate") or ""),
            "status": str(latest_item.get("orderStatus") or latest_item.get("status") or "unmapped"),
            "totalValue": round(float(_to_decimal(latest_item.get("orderTotalValue") or latest_item.get("totalPrice"))), 2),
        }

    return {
        "totalPurchased": round(float(total_purchased), 2),
        "grossTotal": round(float(gross_total), 2),
        "canceledTotal": round(float(canceled_total), 2),
        "averageTicketPerOrder": round(float(avg_ticket), 2),
        "activeOrdersCount": active_orders_count,
        "totalOrdersCount": len(all_orders),
        "totalItemsCount": total_all_items,
        "activeItemsCount": active_items_count,
        "pendingOrdersCount": len(pending_orders),
        "awaitingApprovalOrdersCount": len(strictly_pending_orders),
        "pendingItemsCount": pending_delivery_items_count,
        "fulfillment": {
            "fulfilledPct": fulfilled_pct,
            "pendingDeliveryPct": pending_pct,
            "fulfilledItems": fulfilled_items_count,
            "pendingDeliveryItems": pending_delivery_items_count,
            "qtyOrderedNet": round(float(qty_ordered_net), 4),
            "qtyDeliveredTotal": round(float(qty_delivered_total), 4),
            "qtyPendingTotal": round(float(qty_pending_total), 4),
        },
        "monthlyComparison": {
            "currentMonth": {
                "period": f"{cur_year:04d}-{cur_month:02d}",
                "label": _format_month_label(cur_year, cur_month),
                "total": round(float(cur_total), 2),
                "ordersCount": len(cur_data["orders"]),
                "itemsCount": cur_data["itemsCount"],
            },
            "previousMonth": {
                "period": f"{prev_year:04d}-{prev_month:02d}",
                "label": _format_month_label(prev_year, prev_month),
                "total": round(float(prev_total), 2),
                "ordersCount": len(prev_data["orders"]),
                "itemsCount": prev_data["itemsCount"],
            },
            "deltaValue": round(float(delta_val), 2),
            "deltaPct": delta_pct,
            "series": monthly_series,
        },
        "statusDistribution": status_distribution,
        "latestOrder": latest_order_summary,
    }
