"""Validação e publicação de retratos JSON; nenhuma conexão com o ERP nesta camada."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
import re
from pathlib import Path
import tempfile

from core.config import load_environment

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_NAME = "requisicoes.json"
SCHEMA_VERSION = 3
MAX_SNAPSHOT_BYTES = 25 * 1024 * 1024  # Limite defensivo de 25 MB por arquivo JSON
_SAFE_FILENAME_RE = re.compile(r"^[a-z0-9_]+\.json$")
WORKFLOW_STAGES = {"request", "approval", "quotation", "execution", "invoice", "payment", "closed"}


def _validate_workflow(flow):
    """Valida o contrato de apresentação; não deduz movimentos nem consulta auditoria do ERP."""
    if flow is None:
        return
    if not isinstance(flow, dict) or set(flow) - {"stage", "attention", "estimatedValue", "history"}:
        raise ValueError("Fluxo incompatível.")
    if flow.get("stage") is not None and (not isinstance(flow["stage"], str) or flow["stage"] not in WORKFLOW_STAGES):
        raise ValueError("Etapa inválida.")
    if flow.get("attention") is not None and (not isinstance(flow["attention"], str) or not flow["attention"].strip()):
        raise ValueError("Pendência inválida.")
    if flow.get("estimatedValue") is not None and (not isinstance(flow["estimatedValue"], str) or
                                                  not re.fullmatch(r"\d{1,12}\.\d{2}", flow["estimatedValue"])):
        raise ValueError("Valor previsto inválido.")
    if flow.get("history") is None:
        return
    if not isinstance(flow["history"], list):
        raise ValueError("Histórico inválido.")
    for event in flow["history"]:
        if not isinstance(event, dict) or set(event) != {"at", "action", "actor", "stage"}:
            raise ValueError("Evento incompatível.")
        _date(event["at"])
        if not isinstance(event["action"], str) or not event["action"].strip():
            raise ValueError("Ação inválida.")
        if event["actor"] is not None and (not isinstance(event["actor"], str) or not event["actor"].strip()):
            raise ValueError("Responsável inválido.")
        if not isinstance(event["stage"], str) or event["stage"] not in WORKFLOW_STAGES:
            raise ValueError("Etapa do evento inválida.")


class SnapshotUnavailable(ValueError):
    """O retrato está ausente, corrompido ou incompatível com o contrato do painel."""


def storage_directory() -> Path:
    """CLI e Flask usam a mesma pasta privada, independentemente do diretório de execução."""
    configured = Path(load_environment().get("REQUISICOES_STORAGE_DIR", "storage"))
    directory = (configured if configured.is_absolute() else PROJECT_ROOT / configured).resolve()
    forbidden_roots = {PROJECT_ROOT / "static", PROJECT_ROOT / "templates", PROJECT_ROOT / "components"}
    for forbidden in forbidden_roots:
        if directory == forbidden or forbidden in directory.parents:
            raise ValueError("Os retratos não podem ficar dentro de diretórios públicos ou de templates.")
    return directory


def _safe_snapshot_path(directory: Path, filename: str) -> Path:
    """Confina o acesso ao diretório de storage e rejeita path traversal ou links simbólicos."""
    if not isinstance(filename, str) or not _SAFE_FILENAME_RE.fullmatch(filename):
        raise ValueError("Nome de arquivo de retrato inválido.")
    base = directory.resolve()
    target = base / filename
    if target.is_symlink() or target.resolve().parent != base:
        raise ValueError("Caminho de retrato fora do diretório seguro.")
    return target


def _read_secure_json(path: Path) -> dict:
    """Lê e valida um arquivo JSON respeitando limites de tamanho e tipo raiz."""
    if not path.exists() or not path.is_file() or path.is_symlink():
        raise SnapshotUnavailable("Não há um retrato válido disponível.")
    size = path.stat().st_size
    if size <= 0 or size > MAX_SNAPSHOT_BYTES:
        raise SnapshotUnavailable("Tamanho do retrato fora dos limites permitidos.")
    raw_content = path.read_text(encoding="utf-8")
    snapshot = json.loads(raw_content)
    if not isinstance(snapshot, dict):
        raise ValueError("Retrato inválido.")
    return snapshot


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date(value):
    if not isinstance(value, str):
        raise ValueError("Data inválida no retrato.")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=-3)))
    return parsed


def validate_records(records):
    """Valida o contrato de apresentação; códigos do ERP são mapeados em core/erp.py.

    id identifica o registro; code preserva o código exibido e pesquisado. Classificação
    ausente não equivale a pendente, concluída nem qualquer etapa do processo.
    """
    if not isinstance(records, list):
        raise ValueError("A coleta deve produzir uma lista de requisições.")
    sectors = {
        "operations", "maintenance", "facilities", "technology", "supply",  # compatibilidade de testes legados
        "compras", "credito_cobranca", "financeiro", "administrativo_matriz",
        "sac", "juridico", "ti", "rh", "armazem", "projetos", "recebimento",
        "limpeza", "reintegracao", "manutencao", "transporte", "expedicao", "fiscal",
        "unclassified",
    }
    statuses = {"registered", "pending", "approved", "partial", "rejected", "canceled", "released", "quotation", "closed", "unmapped"}
    fields = {"id", "code", "sector", "status", "branch", "title", "description", "reference", "deadline", "item"}
    optional = {"requester", "requesterName", "firstProduct", "createdAt", "sectorName", "inclusionDate", "sectorCode"}
    seen = set()
    for row in records:
        if not isinstance(row, dict) or not fields <= set(row) or set(row) - fields - optional - {"workflow"}:
            raise ValueError("Campos incompatíveis com a versão do painel.")
        # Campos de apresentação opcionais; sua origem/ordenação no ERP ainda será homologada.
        if any(row.get(key) is not None and not isinstance(row[key], str) for key in optional):
            raise ValueError("Campos opcionais inválidos na coleta.")
        if row.get("createdAt") is not None:
            _date(row["createdAt"])
        _validate_workflow(row.get("workflow"))
        if any(not isinstance(row[key], str) or not row[key].strip() for key in fields):
            raise ValueError("Textos obrigatórios inválidos na coleta.")
        if row["sector"] not in sectors or row["status"] not in statuses:
            raise ValueError("Classificação de apresentação inválida.")
        if row["id"] in seen:
            raise ValueError("ID de apresentação duplicado.")
        seen.add(row["id"])
    return records


def read_snapshot(directory: Path) -> dict:
    """Lê somente o JSON já publicado; não coleta nem repara arquivos durante um GET."""
    try:
        target = _safe_snapshot_path(directory, SNAPSHOT_NAME)
        snapshot = _read_secure_json(target)

        # Suporta metadados tanto na raiz quanto dentro de 'meta'
        meta = snapshot.get("meta") if isinstance(snapshot.get("meta"), dict) else snapshot

        schema_version = meta.get("schemaVersion")
        source = meta.get("source")
        last_attempt_ok = meta.get("lastAttemptOk")
        generated_at = meta.get("generatedAt")
        last_attempt_at = meta.get("lastAttemptAt")
        requests_data = snapshot.get("requests")

        if schema_version != SCHEMA_VERSION:
            raise ValueError("Versão de retrato inválida.")
        if source != "erp" or type(last_attempt_ok) is not bool:
            raise ValueError("Origem ou estado inválido.")
        _date(generated_at)
        _date(last_attempt_at)
        validate_records(requests_data)

        # Normaliza o dicionário com campos na raiz para uso transparente pelo dashboard_payload
        return {
            "schemaVersion": schema_version,
            "source": source,
            "generatedAt": generated_at,
            "lastAttemptAt": last_attempt_at,
            "lastAttemptOk": last_attempt_ok,
            "requests": requests_data,
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SnapshotUnavailable("Não há um retrato válido disponível.") from exc

def _publish(directory: Path, snapshot: dict):
    # O arquivo temporário fica no mesmo volume. Leitores veem a versão anterior ou a nova inteira.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".requisicoes-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(snapshot, handle, ensure_ascii=False, allow_nan=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, directory / SNAPSHOT_NAME)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def _collection_lock(directory: Path):
    # Duas coletas simultâneas não podem publicar versões fora de ordem.
    lock = directory / ".coleta.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError("Já existe uma coleta em execução ou um lock pendente de revisão.") from exc
    try:
        os.close(descriptor)
        yield
    finally:
        lock.unlink(missing_ok=True)


def synchronize(directory: Path, collector, source: str = "erp") -> dict:
    """Publica uma coleta completa; falha conserva os dados e a data da última coleta válida.

    Collector é uma função sem argumentos. Essa fronteira permite testar falhas sem acessar banco.
    Retratos demonstrativos antigos nunca são reutilizados como dados reais.
    """
    if source != "erp":
        raise ValueError("A publicação aceita somente a fonte ERP.")
    directory.mkdir(parents=True, exist_ok=True)
    with _collection_lock(directory):
        attempted = utc_now()
        try:
            records = validate_records(collector())
            snapshot = {"schemaVersion": SCHEMA_VERSION, "source": source, "generatedAt": utc_now(),
                        "lastAttemptAt": attempted, "lastAttemptOk": True, "requests": records}
            _publish(directory, snapshot)
            return snapshot
        except Exception:
            # Uma falha inicial não é publicada como uma coleta vazia bem-sucedida.
            try:
                previous = read_snapshot(directory)
                previous.update(lastAttemptAt=attempted, lastAttemptOk=False)
                _publish(directory, previous)
            except (SnapshotUnavailable, OSError):
                pass
            raise


def dashboard_payload(directory: Path, max_age_seconds: int) -> dict:
    snapshot = read_snapshot(directory)
    age = (datetime.now(timezone.utc) - _date(snapshot["generatedAt"])).total_seconds()
    return {"meta": {"schemaVersion": SCHEMA_VERSION, "source": snapshot["source"],
                     "generatedAt": snapshot["generatedAt"], "lastAttemptAt": snapshot["lastAttemptAt"],
                     "lastAttemptOk": snapshot["lastAttemptOk"],
                     "stale": age > max_age_seconds or age < -60,
                     "maxAgeSeconds": max_age_seconds}, "requests": snapshot["requests"]}


def read_named_snapshot(directory: Path, filename: str, max_age_seconds: int = 900) -> dict:
    """Lê e valida um snapshot nomeado (ex.: tv_situac.json) com proteção contra traversal e cálculo de stale."""
    try:
        target = _safe_snapshot_path(directory, filename)
        snapshot = _read_secure_json(target)
        meta = snapshot.get("meta")
        if not isinstance(meta, dict):
            raise ValueError("Metadados ausentes no snapshot.")
        if meta.get("schemaVersion") != SCHEMA_VERSION or meta.get("source") != "erp":
            raise ValueError("Origem ou versão de snapshot incompatível.")
        if meta.get("generatedAt"):
            age = (datetime.now(timezone.utc) - _date(meta["generatedAt"])).total_seconds()
            meta = {
                **meta,
                "stale": age > max_age_seconds or age < -60,
                "maxAgeSeconds": max_age_seconds,
            }
            snapshot = {**snapshot, "meta": meta}
        return snapshot
    except SnapshotUnavailable:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SnapshotUnavailable("Não há um retrato válido disponível.") from exc


def synchronize_named_snapshot(directory: Path, filename: str, root_key: str, collector, source: str = "erp") -> dict:
    """Publica um snapshot específico de forma atômica com validação e autocura de locks."""
    if source != "erp":
        raise ValueError("A publicação aceita somente a fonte ERP.")

    directory.mkdir(parents=True, exist_ok=True)
    target_path = _safe_snapshot_path(directory, filename)
    lock_file = directory / f".{filename}.lock"

    # Autocura incondicional de locks órfãos (se tiver mais de 30s de inatividade)
    if lock_file.exists():
        try:
            import time
            if (time.time() - lock_file.stat().st_mtime) > 30:
                lock_file.unlink(missing_ok=True)
        except OSError:
            pass

    try:
        descriptor = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"Já existe uma coleta em execução para {filename}.") from exc

    try:
        os.close(descriptor)
        attempted = utc_now()
        raw_records = collector()
        records = validate_records(raw_records) if root_key == "requests" else raw_records
        snapshot = {
            "meta": {
                "schemaVersion": SCHEMA_VERSION,
                "source": source,
                "generatedAt": utc_now(),
                "lastAttemptAt": attempted,
                "lastAttemptOk": True,
                "stale": False,
                "maxAgeSeconds": 900,
            },
            root_key: records,
        }
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                             prefix=f".{filename}-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(snapshot, handle, ensure_ascii=False, allow_nan=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target_path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return snapshot
    finally:
        try:
            lock_file.unlink(missing_ok=True)
        except OSError:
            pass

