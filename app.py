from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import sqlite3
import os
import math
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from datetime import datetime

app = Flask(__name__)
app.secret_key = "politech_chave_local"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAMINHO_BANCO = os.path.join(BASE_DIR, "politech.db")


# =========================================================
# BANCO
# =========================================================

def conectar():
    return sqlite3.connect(CAMINHO_BANCO)


def garantir_coluna_created_at():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("PRAGMA table_info(levantamento)")
    colunas = [coluna[1] for coluna in cursor.fetchall()]

    if "created_at" not in colunas:
        cursor.execute("ALTER TABLE levantamento ADD COLUMN created_at TEXT")
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE levantamento SET created_at = ? WHERE created_at IS NULL", (agora,))

    conexao.commit()
    conexao.close()


# =========================================================
# VALIDAÇÕES
# =========================================================

def validar_levantamento_form(form):
    erros = []

    nome = form.get("nome", "").strip()
    tipo_angulo = form.get("tipo_angulo", "").strip()
    sentido = form.get("sentido", "").strip()

    try:
        lados = int(form.get("lados", "0"))
        if lados < 3:
            erros.append("O número de lados deve ser pelo menos 3.")
    except ValueError:
        erros.append("Número de lados inválido.")

    try:
        azimute_inicial = float(form.get("azimute_inicial", ""))
        if azimute_inicial < 0 or azimute_inicial >= 360:
            erros.append("O azimute inicial deve estar entre 0° e menor que 360°.")
    except ValueError:
        erros.append("Azimute inicial inválido.")

    try:
        float(form.get("x_inicial", ""))
    except ValueError:
        erros.append("Coordenada X inicial inválida.")

    try:
        float(form.get("y_inicial", ""))
    except ValueError:
        erros.append("Coordenada Y inicial inválida.")

    try:
        criterio_precisao = int(form.get("criterio_precisao", ""))
        if criterio_precisao not in [1000, 5000, 10000]:
            erros.append("Critério de precisão inválido.")
    except ValueError:
        erros.append("Critério de precisão inválido.")

    if not nome:
        erros.append("O nome do levantamento é obrigatório.")

    if tipo_angulo not in ["interno", "externo"]:
        erros.append("Selecione um tipo de ângulo válido.")

    if sentido not in ["horario", "anti-horario"]:
        erros.append("Selecione um sentido válido.")

    return erros


def validar_lados_form(form, quantidade_lados):
    erros = []

    for i in range(1, quantidade_lados + 1):
        nome_ponto = form.get(f"nome_ponto_{i}", "").strip()

        if not nome_ponto:
            erros.append(f"O nome do ponto do lado {i} é obrigatório.")

        try:
            distancia = float(form.get(f"distancia_{i}", ""))
            if distancia <= 0:
                erros.append(f"A distância do lado {i} deve ser maior que zero.")
        except ValueError:
            erros.append(f"Distância inválida no lado {i}.")

        try:
            graus = int(form.get(f"angulo_graus_{i}", ""))
            if graus < 0 or graus >= 360:
                erros.append(f"Os graus do lado {i} devem estar entre 0 e 359.")
        except ValueError:
            erros.append(f"Graus inválidos no lado {i}.")

        try:
            minutos = int(form.get(f"angulo_minutos_{i}", ""))
            if minutos < 0 or minutos > 59:
                erros.append(f"Os minutos do lado {i} devem estar entre 0 e 59.")
        except ValueError:
            erros.append(f"Minutos inválidos no lado {i}.")

        try:
            segundos = float(form.get(f"angulo_segundos_{i}", ""))
            if segundos < 0 or segundos >= 60:
                erros.append(f"Os segundos do lado {i} devem estar entre 0 e menor que 60.")
        except ValueError:
            erros.append(f"Segundos inválidos no lado {i}.")

    return erros
# =========================================================
# FUNÇÕES AUXILIARES DE CÁLCULO
# =========================================================

def dms_para_decimal(graus, minutos, segundos):
    return float(graus) + float(minutos) / 60 + float(segundos) / 3600


def calcular_soma_teorica_angulos(num_lados, tipo_angulo):
    if tipo_angulo == "interno":
        return 180 * (num_lados - 2)
    return 180 * (num_lados + 2)


def calcular_tolerancia_angular_segundos(num_lados):
    return 15 * math.sqrt(num_lados)


def calcular_azimutes(angulos_compensados, azimute_inicial, tipo_angulo, sentido):
    azimutes = [float(azimute_inicial)]

    for i in range(1, len(angulos_compensados)):
        az_anterior = azimutes[i - 1]
        angulo = angulos_compensados[i]

        if sentido == "horario":
            if tipo_angulo == "externo":
                az = az_anterior + angulo + 180
            else:  # interno
                az = az_anterior - angulo + 180
        else:  # anti-horario
            if tipo_angulo == "interno":
                az = az_anterior + angulo + 180
            else:  # externo
                az = az_anterior - angulo + 180

        while az < 0:
            az += 360

        while az >= 360:
            az -= 360

        azimutes.append(az)

    return azimutes


def calcular_projecoes(distancias, azimutes):
    dx = []
    dy = []

    for distancia, azimute in zip(distancias, azimutes):
        rad = math.radians(azimute)
        dx.append(distancia * math.sin(rad))
        dy.append(distancia * math.cos(rad))

    return dx, dy


def compensar_projecoes(distancias, dx, dy):
    perimetro = sum(distancias)
    ex = sum(dx)
    ey = sum(dy)

    correcoes_x = []
    correcoes_y = []
    dx_comp = []
    dy_comp = []

    for d, valor_dx, valor_dy in zip(distancias, dx, dy):
        cx = -(ex * d) / perimetro if perimetro != 0 else 0
        cy = -(ey * d) / perimetro if perimetro != 0 else 0

        correcoes_x.append(cx)
        correcoes_y.append(cy)
        dx_comp.append(valor_dx + cx)
        dy_comp.append(valor_dy + cy)

    return ex, ey, correcoes_x, correcoes_y, dx_comp, dy_comp

def calcular_distancias_corrigidas(dx_comp, dy_comp):
    distancias_corrigidas = []

    for x, y in zip(dx_comp, dy_comp):
        d_corrigida = math.sqrt((x ** 2) + (y ** 2))
        distancias_corrigidas.append(d_corrigida)

    return distancias_corrigidas


def calcular_coordenadas_compensadas(x0, y0, dx_comp, dy_comp):
    xs = [float(x0)]
    ys = [float(y0)]

    for i in range(len(dx_comp)):
        xs.append(xs[i] + dx_comp[i])
        ys.append(ys[i] + dy_comp[i])

    return xs, ys


def gerar_elementos_svg(xs, ys, nomes_pontos, largura=760, altura=500, margem=55):
    if not xs or not ys:
        return {
            "pontos_svg": [],
            "polyline_svg": "",
            "eixo_x": (margem, altura - margem, largura - margem, altura - margem),
            "eixo_y": (margem, margem, margem, altura - margem),
            "bbox": (margem, margem, largura - 2 * margem, altura - 2 * margem),
        }

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    faixa_x = max_x - min_x
    faixa_y = max_y - min_y

    if faixa_x == 0:
        faixa_x = 1
    if faixa_y == 0:
        faixa_y = 1

    escala_x = (largura - 2 * margem) / faixa_x
    escala_y = (altura - 2 * margem) / faixa_y
    escala = min(escala_x, escala_y)

    pontos_svg = []
    for i, (x, y) in enumerate(zip(xs, ys)):
        px = margem + (x - min_x) * escala
        py = altura - margem - (y - min_y) * escala

        if i < len(nomes_pontos):
            nome = nomes_pontos[i]
        else:
            nome = nomes_pontos[0] if nomes_pontos else f"P{i+1}"

        pontos_svg.append({
            "x": round(px, 2),
            "y": round(py, 2),
            "nome": nome
        })

    polyline_svg = " ".join(f"{p['x']},{p['y']}" for p in pontos_svg)

    return {
        "pontos_svg": pontos_svg,
        "polyline_svg": polyline_svg,
        "eixo_x": (margem, altura - margem, largura - margem, altura - margem),
        "eixo_y": (margem, margem, margem, altura - margem),
        "bbox": (margem, margem, largura - 2 * margem, altura - 2 * margem),
    }


def classificar_precisao(m):
    if m >= 10000:
        return "Poligonal eletrônica (1:10000)"
    elif m >= 5000:
        return "Poligonal com trena (1:5000)"
    elif m >= 1000:
        return "Poligonal estadimétrica (1:1000)"
    return "Abaixo de 1:1000"


# =========================================================
# ESTATÍSTICAS
# =========================================================

def obter_estatisticas():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("SELECT COUNT(*) FROM levantamento")
    total_levantamentos = cursor.fetchone()[0]

    cursor.execute("""
        SELECT cidade, COUNT(*) as quantidade
        FROM levantamento
        WHERE cidade IS NOT NULL AND cidade != ''
        GROUP BY cidade
        ORDER BY quantidade DESC
        LIMIT 1
    """)
    cidade_top = cursor.fetchone()

    cursor.execute("""
        SELECT strftime('%m/%Y', created_at) AS mes_ano, COUNT(*) as quantidade
        FROM levantamento
        WHERE created_at IS NOT NULL AND created_at != ''
        GROUP BY strftime('%Y-%m', created_at)
        ORDER BY quantidade DESC, strftime('%Y-%m', created_at) DESC
        LIMIT 1
    """)
    mes_top = cursor.fetchone()

    conexao.close()

    cidade_mais_usada = cidade_top[0] if cidade_top else "Sem dados"
    mes_maior_cadastro = mes_top[0] if mes_top and mes_top[0] else "Sem dados"

    return {
        "total_levantamentos": total_levantamentos,
        "cidade_mais_usada": cidade_mais_usada,
        "mes_maior_cadastro": mes_maior_cadastro
    }


# =========================================================
# MOTOR DE CÁLCULO
# =========================================================

def obter_resultados_calculo(id_levantamento):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT nome, lados, tipo_angulo, azimute_inicial, x_inicial, y_inicial, criterio_precisao, sentido
        FROM levantamento
        WHERE id = ?
    """, (id_levantamento,))
    levantamento = cursor.fetchone()

    cursor.execute("""
        SELECT ordem, nome_ponto, distancia, angulo_graus, angulo_minutos, angulo_segundos
        FROM lado_poligonal
        WHERE levantamento_id = ?
        ORDER BY ordem
    """, (id_levantamento,))
    lados = cursor.fetchall()

    conexao.close()

    if levantamento is None or not lados:
        return None

    nome = levantamento[0]
    num_lados = int(levantamento[1])
    tipo_angulo = levantamento[2]
    azimute_inicial = float(levantamento[3])
    x0 = float(levantamento[4])
    y0 = float(levantamento[5])
    criterio_minimo = int(levantamento[6])
    sentido = levantamento[7]

    nomes_pontos = []
    distancias = []
    angulos = []

    for lado in lados:
        nomes_pontos.append(lado[1])
        distancias.append(float(lado[2]))
        angulo_decimal = dms_para_decimal(lado[3], lado[4], lado[5])
        angulos.append(angulo_decimal)

    soma_angulos = sum(angulos)
    soma_teorica = calcular_soma_teorica_angulos(num_lados, tipo_angulo)
    erro_angular = soma_angulos - soma_teorica

    tolerancia_segundos = calcular_tolerancia_angular_segundos(num_lados)
    erro_angular_segundos = abs(erro_angular) * 3600
    erro_aceitavel = erro_angular_segundos <= tolerancia_segundos

    correcao_por_angulo = -erro_angular / num_lados
    angulos_compensados = [angulo + correcao_por_angulo for angulo in angulos]

    azimutes = calcular_azimutes(
        angulos_compensados,
        azimute_inicial,
        tipo_angulo,
        sentido
    )

    dx, dy = calcular_projecoes(distancias, azimutes)

    ex, ey, correcoes_x, correcoes_y, dx_comp, dy_comp = compensar_projecoes(distancias, dx, dy)
    xs, ys = calcular_coordenadas_compensadas(x0, y0, dx_comp, dy_comp)

    erro_linear = math.sqrt(ex**2 + ey**2)
    perimetro = sum(distancias)

    if erro_linear > 0:
        modulo_escala = perimetro / erro_linear
    else:
        modulo_escala = float("inf")

    classificacao_precisao = classificar_precisao(modulo_escala)
    precisao_aprovada = modulo_escala == float("inf") or modulo_escala >= criterio_minimo

    distancias_corrigidas = calcular_distancias_corrigidas(dx_comp, dy_comp)

    soma_dx_comp = sum(dx_comp)
    soma_dy_comp = sum(dy_comp)

    if tipo_angulo == "interno":
        formula_soma_teorica = "180 × (n - 2)"
    else:
        formula_soma_teorica = "180 × (n + 2)"

    nomes_pontos_desenho = nomes_pontos + [nomes_pontos[0]]
    svg_data = gerar_elementos_svg(xs, ys, nomes_pontos_desenho)

    return {
        "nome": nome,
        "nomes_pontos": nomes_pontos,
        "distancias": distancias,
        "distancias_corrigidas": distancias_corrigidas,
        "angulos": angulos,
        "angulos_compensados": angulos_compensados,
        "azimutes": azimutes,
        "dx": dx,
        "dy": dy,
        "ex": ex,
        "ey": ey,
        "correcoes_x": correcoes_x,
        "correcoes_y": correcoes_y,
        "dx_comp": dx_comp,
        "dy_comp": dy_comp,
        "xs": xs,
        "ys": ys,
        "soma_dx_comp": soma_dx_comp,
        "soma_dy_comp": soma_dy_comp,
        "soma_angulos": soma_angulos,
        "soma_teorica": soma_teorica,
        "formula_soma_teorica": formula_soma_teorica,
        "erro_angular": erro_angular,
        "tolerancia_segundos": tolerancia_segundos,
        "erro_angular_segundos": erro_angular_segundos,
        "erro_aceitavel": erro_aceitavel,
        "correcao_por_angulo": correcao_por_angulo,
        "erro_linear": erro_linear,
        "perimetro": perimetro,
        "modulo_escala": modulo_escala,
        "classificacao_precisao": classificacao_precisao,
        "criterio_minimo": criterio_minimo,
        "precisao_aprovada": precisao_aprovada,
        "pontos_svg": svg_data["pontos_svg"],
        "polyline_svg": svg_data["polyline_svg"],
        "eixo_x": svg_data["eixo_x"],
        "eixo_y": svg_data["eixo_y"],
        "bbox": svg_data["bbox"],
        "tipo_angulo": tipo_angulo,
        "sentido": sentido,
    }



# =========================================================
# ROTAS
# =========================================================

@app.route("/")
def home():
    return render_template("index.html", pagina_ativa="inicio")


@app.route("/historia")
def historia():
    return render_template("historia.html", pagina_ativa="historia")


@app.route("/novo", methods=["GET", "POST"])
def novo():
    if request.method == "POST":
        erros = validar_levantamento_form(request.form)

        if erros:
            for erro in erros:
                flash(erro, "erro")
            return render_template("novo_levantamento.html", pagina_ativa="levantamentos")

        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conexao = conectar()
        cursor = conexao.cursor()

        cursor.execute("""
            INSERT INTO levantamento (
                nome, lados, cidade, tipo_angulo, sentido,
                azimute_inicial, x_inicial, y_inicial, criterio_precisao, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["nome"].strip(),
            int(request.form["lados"]),
            request.form["cidade"].strip(),
            request.form["tipo_angulo"],
            request.form["sentido"],
            float(request.form["azimute_inicial"]),
            float(request.form["x_inicial"]),
            float(request.form["y_inicial"]),
            int(request.form["criterio_precisao"]),
            created_at
        ))

        levantamento_id = cursor.lastrowid
        conexao.commit()
        conexao.close()

        flash("Levantamento criado com sucesso.", "sucesso")
        return redirect(url_for("cadastrar_lados", id=levantamento_id))

    return render_template("novo_levantamento.html", pagina_ativa="levantamentos")


@app.route("/levantamentos")
def listar():
    nome_busca = request.args.get("nome", "").strip()
    cidade_busca = request.args.get("cidade", "").strip()
    lados_busca = request.args.get("lados", "").strip()
    ordenacao = request.args.get("ordenacao", "mais_recente")

    conexao = conectar()
    cursor = conexao.cursor()

    query = """
        SELECT id, nome, lados, cidade, tipo_angulo, sentido,
               azimute_inicial, x_inicial, y_inicial, criterio_precisao, created_at
        FROM levantamento
        WHERE 1=1
    """
    parametros = []

    if nome_busca:
        query += " AND nome LIKE ?"
        parametros.append(f"%{nome_busca}%")

    if cidade_busca:
        query += " AND cidade LIKE ?"
        parametros.append(f"%{cidade_busca}%")

    if lados_busca:
        query += " AND lados = ?"
        parametros.append(int(lados_busca))

    mapa_ordenacao = {
        "mais_recente": "id DESC",
        "mais_antigo": "id ASC",
        "nome_az": "nome ASC",
        "nome_za": "nome DESC",
        "menos_lados": "lados ASC",
        "mais_lados": "lados DESC",
    }

    query += f" ORDER BY {mapa_ordenacao.get(ordenacao, 'id DESC')}"

    cursor.execute(query, parametros)
    levantamentos = cursor.fetchall()
    conexao.close()

    estatisticas = obter_estatisticas()

    return render_template(
        "levantamentos.html",
        levantamentos=levantamentos,
        pagina_ativa="levantamentos",
        nome_busca=nome_busca,
        cidade_busca=cidade_busca,
        lados_busca=lados_busca,
        ordenacao=ordenacao,
        **estatisticas
    )


@app.route("/levantamentos/<int:id>")
def detalhe_levantamento(id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id, nome, lados, cidade, tipo_angulo, sentido,
               azimute_inicial, x_inicial, y_inicial, criterio_precisao
        FROM levantamento
        WHERE id = ?
    """, (id,))
    levantamento = cursor.fetchone()

    cursor.execute("""
        SELECT ordem, nome_ponto, distancia, angulo_graus, angulo_minutos, angulo_segundos
        FROM lado_poligonal
        WHERE levantamento_id = ?
        ORDER BY ordem
    """, (id,))
    lados = cursor.fetchall()
    conexao.close()

    if levantamento is None:
        flash("Levantamento não encontrado.", "erro")
        return redirect(url_for("listar"))

    return render_template(
        "detalhe_levantamento.html",
        levantamento=levantamento,
        lados=lados,
        pagina_ativa="levantamentos"
    )


@app.route("/levantamentos/<int:id>/lados", methods=["GET", "POST"])
def cadastrar_lados(id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("SELECT id, nome, lados FROM levantamento WHERE id = ?", (id,))
    levantamento = cursor.fetchone()

    if levantamento is None:
        conexao.close()
        flash("Levantamento não encontrado.", "erro")
        return redirect(url_for("listar"))

    if request.method == "POST":
        quantidade_lados = int(levantamento[2])
        erros = validar_lados_form(request.form, quantidade_lados)

        if erros:
            conexao.close()
            for erro in erros:
                flash(erro, "erro")
            return render_template(
                "cadastrar_lados.html",
                levantamento=levantamento,
                pagina_ativa="levantamentos"
            )

        cursor.execute("DELETE FROM lado_poligonal WHERE levantamento_id = ?", (id,))

        for i in range(1, quantidade_lados + 1):
            cursor.execute("""
                INSERT INTO lado_poligonal (
                    levantamento_id, ordem, nome_ponto, distancia,
                    angulo_graus, angulo_minutos, angulo_segundos
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                id,
                i,
                request.form[f"nome_ponto_{i}"].strip(),
                float(request.form[f"distancia_{i}"]),
                int(request.form[f"angulo_graus_{i}"]),
                int(request.form[f"angulo_minutos_{i}"]),
                float(request.form[f"angulo_segundos_{i}"])
            ))

        conexao.commit()
        conexao.close()
        flash("Lados cadastrados com sucesso.", "sucesso")
        return redirect(url_for("detalhe_levantamento", id=id))

    conexao.close()
    return render_template(
        "cadastrar_lados.html",
        levantamento=levantamento,
        pagina_ativa="levantamentos"
    )


@app.route("/levantamentos/<int:id>/editar", methods=["GET", "POST"])
def editar_levantamento(id):
    conexao = conectar()
    cursor = conexao.cursor()

    if request.method == "POST":
        erros = validar_levantamento_form(request.form)

        if erros:
            for erro in erros:
                flash(erro, "erro")

            cursor.execute("""
                SELECT id, nome, lados, cidade, tipo_angulo, sentido,
                       azimute_inicial, x_inicial, y_inicial, criterio_precisao
                FROM levantamento
                WHERE id = ?
            """, (id,))
            levantamento = cursor.fetchone()
            conexao.close()

            return render_template(
                "editar_levantamento.html",
                levantamento=levantamento,
                pagina_ativa="levantamentos"
            )

        cursor.execute("""
            UPDATE levantamento
            SET nome = ?, lados = ?, cidade = ?, tipo_angulo = ?, sentido = ?,
                azimute_inicial = ?, x_inicial = ?, y_inicial = ?, criterio_precisao = ?
            WHERE id = ?
        """, (
            request.form["nome"].strip(),
            int(request.form["lados"]),
            request.form["cidade"].strip(),
            request.form["tipo_angulo"],
            request.form["sentido"],
            float(request.form["azimute_inicial"]),
            float(request.form["x_inicial"]),
            float(request.form["y_inicial"]),
            int(request.form["criterio_precisao"]),
            id
        ))

        conexao.commit()
        conexao.close()
        flash("Levantamento atualizado com sucesso.", "sucesso")
        return redirect(url_for("detalhe_levantamento", id=id))

    cursor.execute("""
        SELECT id, nome, lados, cidade, tipo_angulo, sentido,
               azimute_inicial, x_inicial, y_inicial, criterio_precisao
        FROM levantamento
        WHERE id = ?
    """, (id,))
    levantamento = cursor.fetchone()
    conexao.close()

    if levantamento is None:
        flash("Levantamento não encontrado.", "erro")
        return redirect(url_for("listar"))

    return render_template(
        "editar_levantamento.html",
        levantamento=levantamento,
        pagina_ativa="levantamentos"
    )


@app.route("/levantamentos/<int:id>/excluir", methods=["POST"])
def excluir_levantamento(id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("DELETE FROM lado_poligonal WHERE levantamento_id = ?", (id,))
    cursor.execute("DELETE FROM levantamento WHERE id = ?", (id,))

    conexao.commit()
    conexao.close()

    flash("Levantamento excluído com sucesso.", "sucesso")
    return redirect(url_for("listar"))


@app.route("/levantamentos/<int:id>/calcular")
def calcular(id):
    resultado = obter_resultados_calculo(id)

    if resultado is None:
        flash("Levantamento não encontrado ou sem lados cadastrados.", "erro")
        return redirect(url_for("listar"))

    return render_template(
        "resultado.html",
        **resultado,
        id_levantamento=id,
        pagina_ativa="levantamentos"
    )

@app.route("/metodologia")
def metodologia():
    return render_template("metodologia.html", pagina_ativa="metodologia")

@app.route("/levantamentos/<int:id>/pdf", methods=["GET", "POST"])
def gerar_pdf(id):
    resultado = obter_resultados_calculo(id)

    if resultado is None:
        flash("Levantamento não encontrado ou sem lados cadastrados.", "erro")
        return redirect(url_for("listar"))

    nome_responsavel = ""
    data_levantamento = ""

    if request.method == "POST":
        nome_responsavel = request.form.get("nome_responsavel", "").strip()
        data_levantamento = request.form.get("data_levantamento", "").strip()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    largura, altura = A4
    y = altura - 50

    verde = (0.37, 0.52, 0.31)

    def desenhar_bordas():
        pdf.setStrokeColorRGB(*verde)
        pdf.setLineWidth(6)
        pdf.line(25, altura - 20, largura - 25, altura - 20)
        pdf.line(25, 20, largura - 25, 20)
        pdf.setLineWidth(1)
        pdf.setStrokeColorRGB(0, 0, 0)

    def nova_pagina(titulo=None):
        pdf.showPage()
        desenhar_bordas()
        y_local = altura - 50
        if titulo:
            pdf.setFont("Helvetica-Bold", 14)
            pdf.drawString(40, y_local, titulo)
            y_local -= 20
        return y_local

    desenhar_bordas()

    # Logo
    caminho_logo = os.path.join(BASE_DIR, "static", "img", "logo.png")
    if os.path.exists(caminho_logo):
        try:
            pdf.drawImage(caminho_logo, 40, y - 10, width=38, height=38, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(90, y + 10, "RELATÓRIO TÉCNICO - POLITECH")
    y -= 22

    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, y, f"Levantamento: {resultado['nome']}")
    y -= 14
    pdf.drawString(40, y, f"Tipo de ângulo: {resultado['tipo_angulo']} | Sentido: {resultado['sentido']}")
    y -= 14
    pdf.drawString(40, y, f"Critério mínimo: 1:{resultado['criterio_minimo']}")
    y -= 14

    if nome_responsavel:
        pdf.drawString(40, y, f"Responsável: {nome_responsavel}")
        y -= 14

    if data_levantamento:
        pdf.drawString(40, y, f"Data do levantamento: {data_levantamento}")
        y -= 14

    y -= 8

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(40, y, "Resumo técnico")
    y -= 18

    pdf.setFont("Helvetica", 9)
    resumo = [
        f"Soma dos ângulos: {resultado['soma_angulos']:.0f}",
        f"Soma teórica: {resultado['soma_teorica']:.0f}",
        f"Erro angular: {resultado['erro_angular']:.0f}",
        f"Erro angular (seg): {resultado['erro_angular_segundos']:.0f}",
        f"Tolerância angular: {resultado['tolerancia_segundos']:.0f}",
        f"Erro em X (Ex): {resultado['ex']:.3f}",
        f"Erro em Y (Ey): {resultado['ey']:.3f}",
        f"Erro linear: {resultado['erro_linear']:.3f}",
        f"Perímetro: {resultado['perimetro']:.3f}",
        f"Classificação da precisão: {resultado['classificacao_precisao']}",
        f"Condição de fechamento em X: {resultado['soma_dx_comp']:.3f}",
        f"Condição de fechamento em Y: {resultado['soma_dy_comp']:.3f}",
    ]

    if resultado["erro_linear"] == 0:
        resumo.append("Módulo da escala: Infinito")
    else:
        resumo.append(f"Módulo da escala: 1:{resultado['modulo_escala']:.0f}")

    resumo.append(
        "Situação final: Aprovada"
        if resultado["precisao_aprovada"]
        else "Situação final: Reprovada"
    )

    for linha in resumo:
        if y < 60:
            y = nova_pagina("Continuação do resumo")
            pdf.setFont("Helvetica", 9)
        pdf.drawString(50, y, linha)
        y -= 12

    y -= 8
    if y < 150:
        y = nova_pagina("Passo a passo resumido")

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(40, y, "Passo a passo resumido")
    y -= 18

    pdf.setFont("Helvetica", 9)
    passos = [
        f"1) Soma teórica = {resultado['formula_soma_teorica']}",
        f"2) Erro angular = soma medida - soma teórica = {resultado['erro_angular']:.0f}",
        f"3) Tolerância angular = 15'' x raiz(n) = {resultado['tolerancia_segundos']:.0f}",
        f"4) Correção angular = -erro angular / n = {resultado['correcao_por_angulo']:.0f}",
        f"5) Ângulo compensado = ângulo lido ± correção",
        f"6) Azimutes conforme tipo de ângulo e sentido",
        f"7) Distâncias horizontais adotadas",
        f"8) Projeções: ΔX = D·sen(Az) e ΔY = D·cos(Az)",
        f"9) Ex = soma das projeções em X | Ey = soma das projeções em Y",
        f"10) EL = raiz(Ex² + Ey²) = {resultado['erro_linear']:.3f}",
        f"11) M = P / EL = {'Infinito' if resultado['erro_linear'] == 0 else f'1:{resultado['modulo_escala']:.0f}'}",
        f"12) Distribuição do erro proporcional às distâncias",
        f"13) Projeções compensadas com somatórios nulos",
        f"14) Coordenadas totais = coordenada anterior + projeção compensada",
        f"15) Distâncias corrigidas = raiz(ΔXpc² + ΔYpc²)",
    ]

    for linha in passos:
        if y < 60:
            y = nova_pagina("Passo a passo resumido")
            pdf.setFont("Helvetica", 9)
        pdf.drawString(50, y, linha)
        y -= 12

    # Tabela principal angular
    y -= 8
    if y < 140:
        y = nova_pagina("Tabela angular principal")

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(40, y, "Tabela angular principal")
    y -= 18

    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(40, y, "Lado")
    pdf.drawString(75, y, "Ponto")
    pdf.drawString(130, y, "Dist.")
    pdf.drawString(185, y, "Âng. med.")
    pdf.drawString(255, y, "Âng. comp.")
    pdf.drawString(340, y, "Azimute")
    y -= 10
    pdf.line(40, y, 560, y)
    y -= 10

    pdf.setFont("Helvetica", 8)
    for i in range(len(resultado["distancias"])):
        if y < 45:
            y = nova_pagina("Tabela angular principal")
            pdf.setFont("Helvetica-Bold", 8)
            pdf.drawString(40, y, "Lado")
            pdf.drawString(75, y, "Ponto")
            pdf.drawString(130, y, "Dist.")
            pdf.drawString(185, y, "Âng. med.")
            pdf.drawString(255, y, "Âng. comp.")
            pdf.drawString(340, y, "Azimute")
            y -= 10
            pdf.line(40, y, 560, y)
            y -= 10
            pdf.setFont("Helvetica", 8)

        pdf.drawString(40, y, str(i + 1))
        pdf.drawString(75, y, str(resultado["nomes_pontos"][i]))
        pdf.drawString(130, y, f"{resultado['distancias'][i]:.3f}")
        pdf.drawString(185, y, f"{resultado['angulos'][i]:.0f}")
        pdf.drawString(255, y, f"{resultado['angulos_compensados'][i]:.0f}")
        pdf.drawString(340, y, f"{resultado['azimutes'][i]:.0f}")
        y -= 12

    # Tabela principal linear
    y -= 10
    if y < 140:
        y = nova_pagina("Tabela linear principal")

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(40, y, "Tabela linear principal")
    y -= 18

    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(40, y, "Lado")
    pdf.drawString(75, y, "DX")
    pdf.drawString(130, y, "DY")
    pdf.drawString(185, y, "Cx")
    pdf.drawString(240, y, "Cy")
    pdf.drawString(295, y, "DX comp")
    pdf.drawString(380, y, "DY comp")
    pdf.drawString(465, y, "D corr")
    y -= 10
    pdf.line(40, y, 560, y)
    y -= 10

    pdf.setFont("Helvetica", 8)
    for i in range(len(resultado["distancias"])):
        if y < 45:
            y = nova_pagina("Tabela linear principal")
            pdf.setFont("Helvetica-Bold", 8)
            pdf.drawString(40, y, "Lado")
            pdf.drawString(75, y, "DX")
            pdf.drawString(130, y, "DY")
            pdf.drawString(185, y, "Cx")
            pdf.drawString(240, y, "Cy")
            pdf.drawString(295, y, "DX comp")
            pdf.drawString(380, y, "DY comp")
            pdf.drawString(465, y, "D corr")
            y -= 10
            pdf.line(40, y, 560, y)
            y -= 10
            pdf.setFont("Helvetica", 8)

        pdf.drawString(40, y, str(i + 1))
        pdf.drawString(75, y, f"{resultado['dx'][i]:.3f}")
        pdf.drawString(130, y, f"{resultado['dy'][i]:.3f}")
        pdf.drawString(185, y, f"{resultado['correcoes_x'][i]:.3f}")
        pdf.drawString(240, y, f"{resultado['correcoes_y'][i]:.3f}")
        pdf.drawString(295, y, f"{resultado['dx_comp'][i]:.3f}")
        pdf.drawString(380, y, f"{resultado['dy_comp'][i]:.3f}")
        pdf.drawString(465, y, f"{resultado['distancias_corrigidas'][i]:.3f}")
        y -= 12

    # Desenho
    y -= 14
    if y < 240:
        y = nova_pagina("Desenho da poligonal")

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(40, y, "Desenho da poligonal")
    y -= 18

    x0_pdf = 55
    y0_pdf = y - 210
    largura_pdf = 470
    altura_pdf = 190

    pdf.rect(x0_pdf, y0_pdf, largura_pdf, altura_pdf)

    pontos = resultado["pontos_svg"]
    if pontos:
        escala_x = largura_pdf / 760
        escala_y = altura_pdf / 500

        pontos_pdf = []
        for p in pontos:
            x_pdf = x0_pdf + (p["x"] * escala_x)
            y_pdf = y0_pdf + altura_pdf - (p["y"] * escala_y)
            pontos_pdf.append((x_pdf, y_pdf, p["nome"]))

        for i in range(len(pontos_pdf) - 1):
            pdf.line(
                pontos_pdf[i][0], pontos_pdf[i][1],
                pontos_pdf[i + 1][0], pontos_pdf[i + 1][1]
            )

        for xp, yp, nome in pontos_pdf:
            pdf.circle(xp, yp, 2.5, fill=1)
            pdf.drawString(xp + 4, yp + 4, str(nome))

    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(40, 28, "Gerado automaticamente pelo Politech")

    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"relatorio_{resultado['nome']}.pdf",
        mimetype="application/pdf"
    )


# =========================================================
# INICIALIZAÇÃO
# =========================================================

garantir_coluna_created_at()

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)