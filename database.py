import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAMINHO_BANCO = os.path.join(BASE_DIR, "politech.db")


def conectar():
    return sqlite3.connect(CAMINHO_BANCO)


def criar_tabelas():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("DROP TABLE IF EXISTS lado_poligonal")
    cursor.execute("DROP TABLE IF EXISTS levantamento")

    cursor.execute("""
    CREATE TABLE levantamento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        lados INTEGER NOT NULL,
        cidade TEXT,
        tipo_angulo TEXT,
        sentido TEXT,
        azimute_inicial REAL,
        x_inicial REAL,
        y_inicial REAL,
        criterio_precisao INTEGER DEFAULT 1000
    )
    """)

    cursor.execute("""
    CREATE TABLE lado_poligonal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        levantamento_id INTEGER NOT NULL,
        ordem INTEGER NOT NULL,
        nome_ponto TEXT NOT NULL,
        distancia REAL NOT NULL,
        angulo_graus INTEGER NOT NULL,
        angulo_minutos INTEGER NOT NULL,
        angulo_segundos REAL NOT NULL,
        FOREIGN KEY (levantamento_id) REFERENCES levantamento(id)
    )
    """)

    conexao.commit()
    conexao.close()

    print(f"Banco recriado com sucesso em: {CAMINHO_BANCO}")


if __name__ == "__main__":
    criar_tabelas()