"""Executa a coleta fora do servidor web e publica os retratos JSON privados."""
import argparse
import sys
import time
from pathlib import Path

from core.config import ConfigurationError
from core.database import DatabaseError, conectar_sqlserver, consultar
from core.erp import MappingError, CONFIG_COLETAS_TV
from core.requisicoes import storage_directory, synchronize_named_snapshot


def limpar_locks_mortos():
    """Garante a limpeza de locks órfãos (travados há mais de 30s) direto no Python."""
    diretorio = storage_directory()
    if diretorio.exists():
        for f in diretorio.glob("*.lock"):
            try:
                if (time.time() - f.stat().st_mtime) > 30:
                    f.unlink(missing_ok=True)
            except OSError:
                pass


def executar_coleta_tv(alvo: str, connection=None) -> bool:
    """Coleta e publica uma tabela específica da TV de forma atômica."""
    if alvo not in CONFIG_COLETAS_TV:
        print(f"Alvo '{alvo}' desconhecido. Opções: {list(CONFIG_COLETAS_TV.keys())}", file=sys.stderr)
        return False

    cfg = CONFIG_COLETAS_TV[alvo]
    diretorio = storage_directory()

    try:
        def coletor():
            linhas = consultar(cfg["consulta"], connection=connection)
            return cfg["mapeador"](linhas)

        snapshot = synchronize_named_snapshot(
            directory=diretorio,
            filename=cfg["arquivo"],
            root_key=cfg["campo_raiz"],
            collector=coletor,
            source="erp"
        )
        total = len(snapshot[cfg["campo_raiz"]])
        print(f"[OK] {alvo}: Publicado {total} registros em {cfg['arquivo']}.")
        return True
    except (MappingError, ConfigurationError, DatabaseError) as exc:
        print(f"[ERRO] {alvo}: Coleta falhou: {exc}. Retrato anterior mantido.", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"[ERRO] {alvo}: Exceção inesperada ({type(exc).__name__}: {exc}).", file=sys.stderr)
        return False


def main(argv=None) -> int:
    # 1. Limpeza automática antes de qualquer operação
    limpar_locks_mortos()
    
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fonte", choices=["erp"], help="Fonte autorizada de dados.")
    parser.add_argument("--alvo", choices=["requisicoes", "tv", "tv_situac", "tv_pedidos", "tv_nf"],
                        default="tv", help="Qual conjunto de dados coletar.")
    parser.add_argument("--verificar-config", action="store_true", help="Valida credenciais SQL Server.")
    parser.add_argument("--testar-conexao", action="store_true", help="Testa conectividade.")
    args = parser.parse_args(argv)

    if args.verificar_config or args.testar_conexao:
        from core.config import SQLServerConfig
        try:
            config = SQLServerConfig.from_environment()
            config.validate_connection()
            if args.testar_conexao:
                consultar("diagnostico", config=config)
                print("Conexão com SQL Server validada com sucesso.")
            else:
                print("Configuração do SQL Server válida.")
            return 0
        except (ConfigurationError, DatabaseError) as exc:
            print(str(exc), file=sys.stderr)
            return 1

    if args.alvo == "tv":
        conn = None
        try:
            conn = conectar_sqlserver()
        except (DatabaseError, ConfigurationError) as exc:
            print(f"[ERRO] Falha geral ao conectar ao SQL Server: {exc}", file=sys.stderr)
            return 1

        try:
            sucessos = [executar_coleta_tv(alvo, connection=conn) for alvo in CONFIG_COLETAS_TV]
            return 0 if all(sucessos) else 1
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
    else:
        sucesso = executar_coleta_tv(args.alvo)
        return 0 if sucesso else 1


if __name__ == "__main__":
    raise SystemExit(main())
