"""Lógica de agrupamento e contabilização dos gráficos de ranking (Top Requerentes, Setores, Itens)."""

from collections import Counter


# Consulta direta de Funcionários / Requerentes (OSEFUN)
SQL_FUNCIONARIOS = """
-- Funcionários / Requerentes cadastrados e ativos
SELECT 
    OSEFUN.CODFUN,
    OSEFUN.CODSET,
    OSEFUN.CODFIL,
    OSEFUN.NOMFUN
FROM OSEFUN WITH(NOLOCK)
    INNER JOIN RODFIL WITH(NOLOCK) ON OSEFUN.CODFIL = RODFIL.CODFIL
WHERE OSEFUN.CODPAD IN (1)
    AND OSEFUN.INAFUN = 'N'
ORDER BY OSEFUN.NOMFUN ASC;
""".strip()

# Consultas SQL homologadas para apuração direta no banco de dados ERP
SQL_TOP_REQUERENTES = """
-- Top Requerentes por código de funcionário (CODFUN) e nome (NOMFUN)
SELECT TOP 10
    REQ.CODFUN AS codigo,
    ISNULL(FUN.NOMFUN, CONCAT('Requerente ', REQ.CODFUN)) AS nome,
    COUNT(*) AS total
FROM ESTREQ AS REQ WITH(NOLOCK)
LEFT JOIN OSEFUN AS FUN WITH(NOLOCK)
    ON REQ.CODFUN = FUN.CODFUN
    AND FUN.CODPAD IN (1)
    AND FUN.INAFUN = 'N'
WHERE REQ.DATATU >= DATEADD(month, -3, CAST(GETDATE() AS DATE))
  AND REQ.CODFUN IS NOT NULL
GROUP BY REQ.CODFUN, FUN.NOMFUN
ORDER BY total DESC;
""".strip()

SQL_TOP_SETORES = """
-- Top Setores por código do setor (CODSET)
SELECT TOP 10
    REQ.CODSET AS codigo,
    ISNULL(SETOR.DESCRI, CONCAT('Setor ', REQ.CODSET)) AS nome,
    COUNT(*) AS total
FROM ESTREQ AS REQ WITH(NOLOCK)
LEFT JOIN OSESET AS SETOR WITH(NOLOCK)
    ON REQ.CODSET = SETOR.CODSET
    AND SETOR.CODPAD IN (1)
    AND ISNULL(SETOR.INATIV, 'N') <> 'S'
WHERE REQ.DATATU >= DATEADD(month, -3, CAST(GETDATE() AS DATE))
  AND REQ.CODSET IS NOT NULL
GROUP BY REQ.CODSET, SETOR.DESCRI
ORDER BY total DESC;
""".strip()

SQL_TOP_ITENS = """
-- Top Itens por código do produto (CODPROD)
SELECT TOP 10
    IRQ.CODPROD AS codigo,
    ISNULL(PROD.DESCRI, CONCAT('Item ', IRQ.CODPROD)) AS nome,
    COUNT(*) AS total
FROM ESTIRQ AS IRQ WITH(NOLOCK)
INNER JOIN ESTREQ AS REQ WITH(NOLOCK)
    ON REQ.CODREQ = IRQ.CODREQ
LEFT JOIN ESTPRO AS PROD WITH(NOLOCK)
    ON IRQ.CODPROD = PROD.CODPROD
WHERE REQ.DATATU >= DATEADD(month, -3, CAST(GETDATE() AS DATE))
  AND IRQ.CODPROD IS NOT NULL
GROUP BY IRQ.CODPROD, PROD.DESCRI
ORDER BY total DESC;
""".strip()


def calcular_rankings(requests: list[dict], limit: int = 10) -> dict:
    """Contabiliza as ocorrências e prepara os dados para os três gráficos de ranking.
    
    Agrupamentos:
      1. Top Requerentes (por código do requerente: CODFUN e nome: NOMFUN)
      2. Top Setores (por código do setor: CODSET e nome: DESCRI_SETOR)
      3. Top Itens (por código do primeiro produto: PRI_CODPRO)
    """
    total = len(requests)
    if total == 0:
        return {
            "topRequerentes": [],
            "topSetores": [],
            "topItens": [],
            "total": 0,
        }

    # 1. Agrupamento por código de Requerente
    requester_counts = Counter()
    requester_names = {}
    for r in requests:
        cod = str(r.get("requester") or "—").strip()
        name = str(r.get("requesterName") or "").strip()
        if cod and cod != "—":
            requester_counts[cod] += 1
            if cod not in requester_names or (name and name != f"Requerente {cod}"):
                if name:
                    requester_names[cod] = name

    top_requerentes = [
        {
            "code": code,
            "name": requester_names.get(code, f"Requerente {code}"),
            "label": requester_names.get(code, f"Requerente {code}"),
            "count": count,
            "percentage": round((count / total) * 100, 1),
        }
        for code, count in requester_counts.most_common(limit)
    ]

    # 2. Agrupamento por código de Setor
    sector_counts = Counter()
    sector_names = {}
    for r in requests:
        cod = str(r.get("sectorCode") or "—").strip()
        if not cod or cod == "—":
            # Fallback para o nome do setor caso sectorCode não esteja presente
            cod = str(r.get("sectorName") or r.get("sector") or "—").strip()
        name = str(r.get("sectorName") or f"Setor {cod}").strip()
        if cod and cod != "—":
            sector_counts[cod] += 1
            if cod not in sector_names or (name and name != f"Setor {cod}"):
                sector_names[cod] = name

    top_setores = [
        {
            "code": code,
            "name": sector_names.get(code, f"Setor {code}"),
            "label": sector_names.get(code, f"Setor {code}"),
            "count": count,
            "percentage": round((count / total) * 100, 1),
        }
        for code, count in sector_counts.most_common(limit)
    ]

    # 3. Agrupamento por código de Item
    item_counts = Counter()
    item_labels = {}
    for r in requests:
        cod = str(r.get("firstProduct") or "—").strip()
        label = str(r.get("item") or f"Item {cod}").strip()
        if cod and cod != "—":
            item_counts[cod] += 1
            if cod not in item_labels or (label and label != f"Item {cod}"):
                item_labels[cod] = label

    top_itens = [
        {
            "code": code,
            "name": item_labels.get(code, f"Item {code}"),
            "label": f"Item {code}",
            "count": count,
            "percentage": round((count / total) * 100, 1),
        }
        for code, count in item_counts.most_common(limit)
    ]

    return {
        "topRequerentes": top_requerentes,
        "topSetores": top_setores,
        "topItens": top_itens,
        "total": total,
    }
