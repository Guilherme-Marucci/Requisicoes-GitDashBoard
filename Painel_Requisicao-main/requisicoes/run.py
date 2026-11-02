"""Ponto de entrada do Painel de Requisições (MySQL + RBAC).

Desenvolvimento:  python run.py          -> http://127.0.0.1:5000
Produção:         use um servidor WSGI apontando para `run:app`.
"""

import os
from painel import create_app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("PAINEL_HOST", "0.0.0.0")
    port = int(os.environ.get("PAINEL_PORT", 5000))
    app.run(host=host, port=port, debug=False)
