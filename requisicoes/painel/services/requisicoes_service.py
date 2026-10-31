"""Validação de payload e regras de negócio de requisições."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

SETORES = {
    "compras": "Compras", "ti": "TI", "manutencao": "Manutenção", "financeiro": "Financeiro",
    "administrativo": "Administrativo", "armazem": "Armazém", "transporte": "Transporte",
    "juridico": "Jurídico", "rh": "RH", "projetos": "Projetos", "outros": "Outros",
}
PRIORIDADES = {"baixa": "Baixa", "media": "Média", "alta": "Alta", "critica": "Crítica"}
STATUS = {
    "registered": "Registrada", "pending": "Pendente", "quotation": "Em cotação", "approved": "Aprovada",
    "partial": "Parcial", "released": "Liberada", "closed": "Concluída", "rejected": "Rejeitada",
    "canceled": "Cancelada",
}
# Transições permitidas a partir de cada status; estados finais só reabrem com super-admin.
TRANSICOES = {
    "registered": {"pending", "quotation", "approved", "rejected", "canceled"},
    "pending": {"quotation", "approved", "rejected", "canceled"},
    "quotation": {"approved", "rejected", "canceled", "pending"},
    "approved": {"partial", "released", "canceled", "closed"},
    "partial": {"released", "closed", "canceled"},
    "released": {"closed", "partial"},
    "rejected": {"pending"},
    "canceled": set(),
    "closed": set(),
}
UNIDADES = {"UN", "CX", "KG", "L", "M", "PC", "PAR", "KIT", "SV"}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ValidacaoErro(Exception):
    def __init__(self, erros: dict[str, str]):
        super().__init__("Dados inválidos.")
        self.erros = erros


def _texto(valor, limite: int) -> str:
    texto = _CONTROL.sub("", str(valor if valor is not None else "")).strip()
    return texto


def validar_requisicao(payload: dict) -> dict:
    """Normaliza e valida o payload; levanta ValidacaoErro com mensagens por campo."""
    if not isinstance(payload, dict):
        raise ValidacaoErro({"_": "Payload inválido."})
    erros: dict[str, str] = {}
    limpo: dict = {}

    def obrigatorio(campo, rotulo, minimo, maximo):
        valor = _texto(payload.get(campo), maximo)
        if len(valor) < minimo:
            erros[campo] = f"{rotulo}: informe ao menos {minimo} caracteres."
        elif len(valor) > maximo:
            erros[campo] = f"{rotulo}: máximo de {maximo} caracteres."
        limpo[campo] = valor

    obrigatorio("titulo", "Título", 5, 140)
    obrigatorio("descricao", "Descrição", 10, 2000)
    obrigatorio("item", "Item", 2, 160)
    obrigatorio("filial", "Filial", 2, 40)

    setor = _texto(payload.get("setor"), 30).lower()
    if setor not in SETORES:
        erros["setor"] = "Setor inválido."
    limpo["setor"] = setor

    prioridade = _texto(payload.get("prioridade") or "media", 10).lower()
    if prioridade not in PRIORIDADES:
        erros["prioridade"] = "Prioridade inválida."
    limpo["prioridade"] = prioridade

    unidade = _texto(payload.get("unidade") or "UN", 10).upper()
    if unidade not in UNIDADES:
        erros["unidade"] = "Unidade inválida."
    limpo["unidade"] = unidade

    try:
        quantidade = Decimal(str(payload.get("quantidade", "")).replace(",", ".").strip())
        if not quantidade.is_finite() or quantidade <= 0 or quantidade > Decimal("999999999"):
            raise InvalidOperation
        limpo["quantidade"] = quantidade.quantize(Decimal("0.001"))
    except (InvalidOperation, ValueError):
        erros["quantidade"] = "Quantidade deve ser um número maior que zero."

    bruto_valor = str(payload.get("valor_estimado") or "").replace(",", ".").strip()
    limpo["valor_estimado"] = None
    if bruto_valor:
        try:
            valor = Decimal(bruto_valor)
            if not valor.is_finite() or valor < 0 or valor > Decimal("999999999999"):
                raise InvalidOperation
            limpo["valor_estimado"] = valor.quantize(Decimal("0.01"))
        except InvalidOperation:
            erros["valor_estimado"] = "Valor estimado inválido."

    bruto_prazo = _texto(payload.get("prazo"), 10)
    limpo["prazo"] = None
    if bruto_prazo:
        try:
            prazo = datetime.strptime(bruto_prazo, "%Y-%m-%d").date()
            if prazo < date.today():
                erros["prazo"] = "O prazo não pode estar no passado."
            limpo["prazo"] = prazo
        except ValueError:
            erros["prazo"] = "Data inválida (use AAAA-MM-DD)."

    referencia = _texto(payload.get("referencia"), 60)
    if len(referencia) > 60:
        erros["referencia"] = "Referência: máximo de 60 caracteres."
    limpo["referencia"] = referencia or None

    if erros:
        raise ValidacaoErro(erros)
    return limpo


def validar_mudanca_status(atual: str, novo: str, comentario: str | None, *, super_admin: bool) -> str | None:
    if novo not in STATUS:
        raise ValidacaoErro({"status": "Status inválido."})
    if novo == atual:
        raise ValidacaoErro({"status": "A requisição já está neste status."})
    if not super_admin and novo not in TRANSICOES.get(atual, set()):
        raise ValidacaoErro({"status": f"Transição não permitida: {STATUS[atual]} → {STATUS[novo]}."})
    comentario = _texto(comentario, 500) if comentario else ""
    if len(comentario) > 500:
        raise ValidacaoErro({"comentario": "Comentário: máximo de 500 caracteres."})
    if novo in {"rejected", "canceled"} and len(comentario) < 5:
        raise ValidacaoErro({"comentario": "Informe o motivo (mínimo 5 caracteres) para rejeitar ou cancelar."})
    return comentario or None


def normalizar_filtros(args) -> dict:
    """Aceita somente valores conhecidos; filtros inválidos são descartados em vez de repassados ao SQL."""
    filtros = {
        "q": _texto(args.get("q"), 80)[:80],
        "status": args.get("status", "") if args.get("status", "") in STATUS else "",
        "setor": args.get("setor", "") if args.get("setor", "") in SETORES else "",
        "prioridade": args.get("prioridade", "") if args.get("prioridade", "") in PRIORIDADES else "",
        "filial": _texto(args.get("filial"), 40)[:40],
        "ordenar": args.get("ordenar", "recentes"),
    }
    for campo in ("data_inicio", "data_fim"):
        bruto = _texto(args.get(campo), 10)
        try:
            datetime.strptime(bruto, "%Y-%m-%d")
            filtros[campo] = bruto
        except ValueError:
            filtros[campo] = ""
    return filtros

