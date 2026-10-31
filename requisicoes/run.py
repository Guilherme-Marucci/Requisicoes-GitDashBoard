"""Ponto de entrada do Painel de Requisições (MySQL + RBAC).

Desenvolvimento:  python run.py          -> http://127.0.0.1:5000
Produção:         use um servidor WSGI apontando para `run:app`.
"""

from painel import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
