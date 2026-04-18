import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAMINHO_BANCO = os.path.join(BASE_DIR, "politech.db")


def criar_banco():
    conexao = sqlite3.connect(CAMINHO_BANCO)
    cursor = conexao.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS levantamento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            lados INTEGER NOT NULL,
            cidade TEXT,
            tipo_angulo TEXT NOT NULL,
            sentido TEXT NOT NULL,
            azimute_graus INTEGER NOT NULL,
            azimute_minutos INTEGER NOT NULL,
            azimute_segundos REAL NOT NULL,
            ponto_azimute INTEGER NOT NULL,
            x_inicial REAL NOT NULL,
            y_inicial REAL NOT NULL,
            tolerancia_angular_segundos REAL NOT NULL,
            criterio_precisao INTEGER NOT NULL,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lado_poligonal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            levantamento_id INTEGER NOT NULL,
            ordem INTEGER NOT NULL,
            nome_ponto TEXT NOT NULL,
            distancia REAL NOT NULL,
            angulo_graus INTEGER NOT NULL,
            angulo_minutos INTEGER NOT NULL,
            angulo_segundos REAL NOT NULL,
            FOREIGN KEY (levantamento_id) REFERENCES levantamento(id) ON DELETE CASCADE
        )
    """)

    conexao.commit()
    conexao.close()
    print("Banco de dados e tabelas criados com sucesso.")


if __name__ == "__main__":
    criar_banco()