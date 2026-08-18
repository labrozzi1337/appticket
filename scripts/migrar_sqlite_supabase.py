"""Envia o dados.db local para appticket.transacoes sem apagar o SQLite."""
import os
import sqlite3
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.environ["STORAGE_BACKEND"] = "supabase"

import app  # noqa: E402


def main():
    caminho = os.path.join(RAIZ, "dados.db")
    with sqlite3.connect(caminho) as conexao:
        linhas = conexao.execute(f"SELECT {','.join(app.COLS)} FROM resultado").fetchall()
    objetos = [dict(zip(app.COLS, linha)) for linha in linhas]
    for inicio in range(0, len(objetos), 200):
        app.gravar(objetos[inicio:inicio + 200])
        print(f"{min(inicio + 200, len(objetos))}/{len(objetos)} registros enviados")
    print("Migracao concluida sem alterar o arquivo SQLite local.")


if __name__ == "__main__":
    main()
