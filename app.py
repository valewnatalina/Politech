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
    conexao = sqlite3.connect(CAMINHO_BANCO)
    conexao.row_factory = sqlite3.Row
    return conexao


def tabela_levantamento_existe():
    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name='levantamento'
    """)
    existe = cursor.fetchone() is not None
    conexao.close()
    return existe


# =========================================================
# CONVERSÕES E FUNÇÕES BÁSICAS
# =========================================================

def dms_para_decimal(graus, minutos=0, segundos=0):
    return float(graus) + float(minutos) / 60 + float(segundos) / 3600


def decimal_para_dms_simples(decimal):
    decimal = float(decimal)
    graus = int(decimal)
    minutos_decimal = (decimal - graus) * 60
    minutos = int(minutos_decimal)
    segundos = (minutos_decimal - minutos) * 60
    return graus, minutos, round(segundos, 2)


def decimal_para_dms_completo(decimal):
    decimal = abs(float(decimal))
    graus = int(decimal)
    minutos_decimal = (decimal - graus) * 60
    minutos = int(minutos_decimal)
    segundos = (minutos_decimal - minutos) * 60
    return graus, minutos, round(segundos, 2)


def dms_para_segundos(graus, minutos, segundos):
    return float(graus) * 3600 + float(minutos) * 60 + float(segundos)


def segundos_para_dms(segundos):
    graus = int(segundos // 3600)
    segundos_restantes = segundos % 3600
    minutos = int(segundos_restantes // 60)
    segundos_finais = round(segundos_restantes % 60, 2)
    return graus, minutos, segundos_finais


def arredondamento_topografico(valor, casas_decimais=3):
    fator = 10 ** casas_decimais
    valor_ampliado = valor * fator
    parte_inteira = int(valor_ampliado)
    parte_decimal = valor_ampliado - parte_inteira

    if parte_decimal >= 0.5:
        return (parte_inteira + 1) / fator
    return parte_inteira / fator


def formatar_dms(graus, minutos, segundos):
    return f"{int(graus)}° {int(minutos):02d}' {round(segundos):02.0f}\""


def formatar_decimal_em_dms(decimal):
    g, m, s = decimal_para_dms_simples(decimal)
    return formatar_dms(g, m, s)


# =========================================================
# VALIDAÇÕES
# =========================================================

def validar_levantamento_form(form):
    erros = []

    nome = form.get("nome", "").strip()
    tipo_angulo = form.get("tipo_angulo", "").strip()
    sentido = form.get("sentido", "").strip()

    if not nome:
        erros.append("O nome do levantamento é obrigatório.")

    if tipo_angulo not in ["interno", "externo"]:
        erros.append("Selecione um tipo de ângulo válido.")

    if sentido not in ["horario", "anti-horario"]:
        erros.append("Selecione um sentido válido.")

    try:
        lados = int(form.get("lados", "0"))
        if lados < 3:
            erros.append("O número de lados deve ser pelo menos 3.")
    except ValueError:
        erros.append("Número de lados inválido.")

    try:
        ponto_azimute = int(form.get("ponto_azimute", "0"))
        lados_int = int(form.get("lados", "0"))
        if ponto_azimute < 1 or ponto_azimute > lados_int:
            erros.append("O ponto do azimute conhecido deve estar entre 1 e o número de vértices.")
    except ValueError:
        erros.append("Ponto do azimute conhecido inválido.")

    try:
        az_graus = int(form.get("azimute_graus", ""))
        if az_graus < 0 or az_graus > 360:
            erros.append("Os graus do azimute devem estar entre 0 e 360.")
    except ValueError:
        erros.append("Graus do azimute inválidos.")

    try:
        az_minutos = int(form.get("azimute_minutos", ""))
        if az_minutos < 0 or az_minutos > 59:
            erros.append("Os minutos do azimute devem estar entre 0 e 59.")
    except ValueError:
        erros.append("Minutos do azimute inválidos.")

    try:
        az_segundos = float(form.get("azimute_segundos", ""))
        if az_segundos < 0 or az_segundos > 59:
            erros.append("Os segundos do azimute devem estar entre 0 e 59.")
    except ValueError:
        erros.append("Segundos do azimute inválidos.")

    try:
        float(form.get("x_inicial", ""))
    except ValueError:
        erros.append("Coordenada X inicial inválida.")

    try:
        float(form.get("y_inicial", ""))
    except ValueError:
        erros.append("Coordenada Y inicial inválida.")

    try:
        tolerancia = float(form.get("tolerancia_angular_segundos", ""))
        if tolerancia <= 0:
            erros.append("A tolerância angular em segundos deve ser maior que zero.")
    except ValueError:
        erros.append("Tolerância angular inválida.")

    try:
        criterio = int(form.get("criterio_precisao", ""))
        if criterio < 1:
            erros.append("O critério de precisão deve ser maior que zero.")
    except ValueError:
        erros.append("Critério de precisão inválido.")

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
            if graus < 0 or graus > 360:
                erros.append(f"Os graus do lado {i} devem estar entre 0 e 360.")
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
            if segundos < 0 or segundos > 59:
                erros.append(f"Os segundos do lado {i} devem estar entre 0 e 59.")
        except ValueError:
            erros.append(f"Segundos inválidos no lado {i}.")

    return erros


# =========================================================
# LÓGICA DA POLIGONAL — MESMA LINHA DO PROGRAMA BASE
# =========================================================

def calcular_soma_teorica_angulos(num_lados, tipo_angulo):
    if tipo_angulo == "interno":
        return 180 * (num_lados - 2)
    return 180 * (num_lados + 2)


def calcular_azimute(azimute_anterior, angulo_atual, tipo_angulo, sentido):
    if tipo_angulo == "interno":
        if sentido == "horario":
            azimute_preliminar = azimute_anterior - angulo_atual
        else:
            azimute_preliminar = azimute_anterior + angulo_atual
    else:
        if sentido == "horario":
            azimute_preliminar = azimute_anterior + angulo_atual
        else:
            azimute_preliminar = azimute_anterior - angulo_atual

    if azimute_preliminar > 180:
        azimute_atual = azimute_preliminar - 180
    else:
        azimute_atual = azimute_preliminar + 180

    if azimute_atual >= 360:
        azimute_atual -= 360
    elif azimute_atual < 0:
        azimute_atual += 360

    return azimute_atual


def calcular_azimutes_a_partir_de(angulos_compensados_decimal, azimute_inicial, ponto_inicio, tipo_angulo, sentido, nomes_pontos):
    num_pontos = len(angulos_compensados_decimal)
    azimutes = [0] * num_pontos
    azimutes[ponto_inicio] = azimute_inicial

    for i in range(1, num_pontos):
        indice_atual = (ponto_inicio + i) % num_pontos
        indice_anterior = (ponto_inicio + i - 1) % num_pontos

        azimute_anterior = azimutes[indice_anterior]
        angulo_atual = angulos_compensados_decimal[indice_atual]
        azimute_atual = calcular_azimute(azimute_anterior, angulo_atual, tipo_angulo, sentido)
        azimutes[indice_atual] = azimute_atual

    return azimutes


def classificar_precisao(m):
    if m >= 10000:
        return "Poligonal eletrônica (1:10000)"
    elif m >= 5000:
        return "Poligonal com trena (1:5000)"
    elif m >= 1000:
        return "Poligonal estadimétrica (1:1000)"
    return "Abaixo de 1:1000"


def gerar_elementos_svg(coordenadas_x, coordenadas_y, nomes_pontos, largura=760, altura=500, margem=55):
    if not coordenadas_x or not coordenadas_y:
        return {
            "pontos_svg": [],
            "polyline_svg": "",
            "eixo_x": (margem, altura - margem, largura - margem, altura - margem),
            "eixo_y": (margem, margem, margem, altura - margem),
            "bbox": (margem, margem, largura - 2 * margem, altura - 2 * margem),
        }

    min_x = min(coordenadas_x)
    max_x = max(coordenadas_x)
    min_y = min(coordenadas_y)
    max_y = max(coordenadas_y)

    faixa_x = max_x - min_x if max_x != min_x else 1
    faixa_y = max_y - min_y if max_y != min_y else 1

    escala_x = (largura - 2 * margem) / faixa_x
    escala_y = (altura - 2 * margem) / faixa_y
    escala = min(escala_x, escala_y)

    pontos_svg = []
    for i, (x, y) in enumerate(zip(coordenadas_x, coordenadas_y)):
        px = margem + (x - min_x) * escala
        py = altura - margem - (y - min_y) * escala
        pontos_svg.append({
            "x": round(px, 2),
            "y": round(py, 2),
            "nome": nomes_pontos[i] if i < len(nomes_pontos) else f"V{i+1}"
        })

    polyline_svg = " ".join(f"{p['x']},{p['y']}" for p in pontos_svg)

    return {
        "pontos_svg": pontos_svg,
        "polyline_svg": polyline_svg,
        "eixo_x": (margem, altura - margem, largura - margem, altura - margem),
        "eixo_y": (margem, margem, margem, altura - margem),
        "bbox": (margem, margem, largura - 2 * margem, altura - 2 * margem),
    }


# =========================================================
# ESTATÍSTICAS
# =========================================================

def obter_estatisticas():
    if not tabela_levantamento_existe():
        return {
            "total_levantamentos": 0,
            "cidade_mais_usada": "Sem dados",
            "mes_maior_cadastro": "Sem dados"
        }

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("SELECT COUNT(*) AS total FROM levantamento")
    total = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT cidade, COUNT(*) AS quantidade
        FROM levantamento
        WHERE cidade IS NOT NULL AND cidade != ''
        GROUP BY cidade
        ORDER BY quantidade DESC
        LIMIT 1
    """)
    cidade_top = cursor.fetchone()

    cursor.execute("""
        SELECT strftime('%m/%Y', created_at) AS mes_ano, COUNT(*) AS quantidade
        FROM levantamento
        WHERE created_at IS NOT NULL AND created_at != ''
        GROUP BY strftime('%Y-%m', created_at)
        ORDER BY quantidade DESC, strftime('%Y-%m', created_at) DESC
        LIMIT 1
    """)
    mes_top = cursor.fetchone()

    conexao.close()

    return {
        "total_levantamentos": total,
        "cidade_mais_usada": cidade_top["cidade"] if cidade_top else "Sem dados",
        "mes_maior_cadastro": mes_top["mes_ano"] if mes_top else "Sem dados",
    }


# =========================================================
# MOTOR DE CÁLCULO — LÓGICA EXATA DO PROGRAMA BASE
# =========================================================

def obter_resultados_calculo(id_levantamento):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id, nome, lados, cidade, tipo_angulo, sentido,
               azimute_graus, azimute_minutos, azimute_segundos,
               ponto_azimute, x_inicial, y_inicial,
               tolerancia_angular_segundos, criterio_precisao, created_at
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

    nome = levantamento["nome"]
    num_lados = int(levantamento["lados"])
    cidade = levantamento["cidade"]
    tipo_angulo = levantamento["tipo_angulo"]
    sentido = levantamento["sentido"]
    azimute_inicial_decimal = dms_para_decimal(
        levantamento["azimute_graus"],
        levantamento["azimute_minutos"],
        levantamento["azimute_segundos"]
    )
    ponto_azimute = int(levantamento["ponto_azimute"]) - 1
    x_inicial = float(levantamento["x_inicial"])
    y_inicial = float(levantamento["y_inicial"])
    tolerancia_segundos = float(levantamento["tolerancia_angular_segundos"])
    criterio_minimo = int(levantamento["criterio_precisao"])

    nomes_pontos = []
    distancias = []
    angulos_usuario_decimal = []
    angulos_usuario_dms = []

    for lado in lados:
        nomes_pontos.append(lado["nome_ponto"])
        distancias.append(round(float(lado["distancia"]), 3))

        graus = int(lado["angulo_graus"])
        minutos = int(lado["angulo_minutos"])
        segundos = float(lado["angulo_segundos"])

        angulos_usuario_decimal.append(dms_para_decimal(graus, minutos, segundos))
        angulos_usuario_dms.append(formatar_dms(graus, minutos, segundos))

    # PASSO 1
    soma_decimal = sum(angulos_usuario_decimal)

    # PASSO 2
    soma_teorica = calcular_soma_teorica_angulos(num_lados, tipo_angulo)

    # PASSO 3
    erro_angular = soma_decimal - soma_teorica
    erro_angular_segundos = abs(erro_angular) * 3600

    # PASSO 4
    erro_aceitavel = erro_angular_segundos <= tolerancia_segundos

    # PASSO 5 - distribuição compensada em segundos
    correcao_total_segundos = abs(erro_angular) * 3600
    correcao_segundos_por_angulo = correcao_total_segundos / num_lados

    resto = 0
    correcoes_em_segundos = []

    for i in range(num_lados):
        acumulado = correcao_segundos_por_angulo * (i + 1)
        parte_inteira = int(acumulado)
        parte_decimal = acumulado - parte_inteira

        if parte_decimal >= 0.49:
            arredondado = parte_inteira + 1
        else:
            arredondado = parte_inteira

        correcao = arredondado - resto
        resto += correcao
        correcoes_em_segundos.append(correcao)

    angulos_compensados_decimal = []
    angulos_compensados_dms = []

    for i, lado in enumerate(lados):
        segundos_originais = dms_para_segundos(
            lado["angulo_graus"],
            lado["angulo_minutos"],
            lado["angulo_segundos"]
        )

        if erro_angular < 0:
            segundos_corrigidos = segundos_originais + correcoes_em_segundos[i]
        else:
            segundos_corrigidos = segundos_originais - correcoes_em_segundos[i]

        g_corr, m_corr, s_corr = segundos_para_dms(segundos_corrigidos)
        angulo_compensado_decimal = segundos_corrigidos / 3600

        angulos_compensados_decimal.append(angulo_compensado_decimal)
        angulos_compensados_dms.append(formatar_dms(g_corr, m_corr, s_corr))

    soma_compensada = sum(angulos_compensados_decimal)

    # PASSO 6
    azimutes_decimal = calcular_azimutes_a_partir_de(
        angulos_compensados_decimal,
        azimute_inicial_decimal,
        ponto_azimute,
        tipo_angulo,
        sentido,
        nomes_pontos
    )
    azimutes_dms = [formatar_decimal_em_dms(az) for az in azimutes_decimal]

    # PASSO 7
    perimetro = sum(distancias)

    # PASSO 8
    projecoes_x = []
    projecoes_y = []

    for i in range(num_lados):
        d = distancias[i]
        az = math.radians(azimutes_decimal[i])

        dx = d * math.sin(az)
        dy = d * math.cos(az)

        dx_arred = arredondamento_topografico(dx, 3)
        dy_arred = arredondamento_topografico(dy, 3)

        projecoes_x.append(dx_arred)
        projecoes_y.append(dy_arred)

    # PASSO 9
    somatorio_x = sum(projecoes_x)
    somatorio_y = sum(projecoes_y)

    somatorio_x_arred = arredondamento_topografico(somatorio_x, 3)
    somatorio_y_arred = arredondamento_topografico(somatorio_y, 3)

    if abs(somatorio_x_arred) < 0.0001:
        somatorio_x_arred = 0.0
    if abs(somatorio_y_arred) < 0.0001:
        somatorio_y_arred = 0.0

    ex = somatorio_x_arred
    ey = somatorio_y_arred

    # PASSO 10
    erro_linear = math.sqrt(ex ** 2 + ey ** 2)
    erro_linear_arred = arredondamento_topografico(erro_linear, 3)

    # PASSO 11
    modulo_escala = perimetro / erro_linear if erro_linear > 0 else float("inf")
    precisao_aprovada = modulo_escala == float("inf") or modulo_escala >= criterio_minimo
    classificacao_precisao = classificar_precisao(modulo_escala)

    # PASSO 12
    correcoes_x = []
    correcoes_y = []

    for i in range(num_lados):
        cxi = -(ex * distancias[i]) / perimetro
        cyi = -(ey * distancias[i]) / perimetro
        correcoes_x.append(cxi)
        correcoes_y.append(cyi)

    # PASSO 13
    projecoes_x_comp = []
    projecoes_y_comp = []

    for i in range(num_lados):
        dx_comp = projecoes_x[i] + correcoes_x[i]
        dy_comp = projecoes_y[i] + correcoes_y[i]
        projecoes_x_comp.append(dx_comp)
        projecoes_y_comp.append(dy_comp)

    soma_dx_comp = sum(projecoes_x_comp)
    soma_dy_comp = sum(projecoes_y_comp)

    if abs(soma_dx_comp) < 0.0001:
        soma_dx_comp = 0.0
    if abs(soma_dy_comp) < 0.0001:
        soma_dy_comp = 0.0

    # PASSO 14
    coordenadas_x = [x_inicial]
    coordenadas_y = [y_inicial]

    for i in range(num_lados):
        x_proximo = coordenadas_x[i] + projecoes_x_comp[i]
        y_proximo = coordenadas_y[i] + projecoes_y_comp[i]
        coordenadas_x.append(x_proximo)
        coordenadas_y.append(y_proximo)

    # PASSO 15
    distancias_corrigidas = []
    for i in range(num_lados):
        d_corr = math.sqrt(projecoes_x_comp[i] ** 2 + projecoes_y_comp[i] ** 2)
        distancias_corrigidas.append(d_corr)

    nomes_pontos_desenho = nomes_pontos + [nomes_pontos[0]]
    svg_data = gerar_elementos_svg(coordenadas_x, coordenadas_y, nomes_pontos_desenho)

    if tipo_angulo == "interno":
        formula_soma_teorica = "180 × (n - 2)"
    else:
        formula_soma_teorica = "180 × (n + 2)"

    ponto_azimute_nome = nomes_pontos[ponto_azimute] if 0 <= ponto_azimute < len(nomes_pontos) else f"P{ponto_azimute + 1}"

    return {
        "id": levantamento["id"],
        "nome": nome,
        "cidade": cidade,
        "num_lados": num_lados,
        "tipo_angulo": tipo_angulo,
        "sentido": sentido,
        "ponto_azimute": ponto_azimute,
        "ponto_azimute_nome": ponto_azimute_nome,
        "azimute_inicial_decimal": azimute_inicial_decimal,
        "azimute_inicial_dms": formatar_dms(
            levantamento["azimute_graus"],
            levantamento["azimute_minutos"],
            levantamento["azimute_segundos"]
        ),
        "x_inicial": x_inicial,
        "y_inicial": y_inicial,
        "tolerancia_segundos": tolerancia_segundos,
        "criterio_minimo": criterio_minimo,

        "nomes_pontos": nomes_pontos,
        "distancias": distancias,
        "distancias_corrigidas": distancias_corrigidas,

        "angulos": angulos_usuario_decimal,
        "angulos_dms": angulos_usuario_dms,
        "angulos_compensados": angulos_compensados_decimal,
        "angulos_compensados_dms": angulos_compensados_dms,

        "correcoes_angulares_segundos": correcoes_em_segundos,
        "correcao_por_angulo": correcao_segundos_por_angulo,

        "azimutes": azimutes_decimal,
        "azimutes_dms": azimutes_dms,

        "dx": projecoes_x,
        "dy": projecoes_y,
        "ex": ex,
        "ey": ey,

        "correcoes_x": correcoes_x,
        "correcoes_y": correcoes_y,
        "dx_comp": projecoes_x_comp,
        "dy_comp": projecoes_y_comp,

        "xs": coordenadas_x,
        "ys": coordenadas_y,

        "soma_angulos": soma_decimal,
        "soma_teorica": soma_teorica,
        "soma_compensada": soma_compensada,
        "formula_soma_teorica": formula_soma_teorica,

        "erro_angular": erro_angular,
        "erro_angular_segundos": erro_angular_segundos,
        "erro_aceitavel": erro_aceitavel,

        "erro_linear": erro_linear_arred,
        "perimetro": perimetro,
        "modulo_escala": modulo_escala,
        "classificacao_precisao": classificacao_precisao,
        "precisao_aprovada": precisao_aprovada,

        "soma_dx_comp": soma_dx_comp,
        "soma_dy_comp": soma_dy_comp,

        "pontos_svg": svg_data["pontos_svg"],
        "polyline_svg": svg_data["polyline_svg"],
        "eixo_x": svg_data["eixo_x"],
        "eixo_y": svg_data["eixo_y"],
        "bbox": svg_data["bbox"],
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


@app.route("/metodologia")
def metodologia():
    return render_template("metodologia.html", pagina_ativa="metodologia")


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
                azimute_graus, azimute_minutos, azimute_segundos,
                ponto_azimute, x_inicial, y_inicial,
                tolerancia_angular_segundos, criterio_precisao, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["nome"].strip(),
            int(request.form["lados"]),
            request.form.get("cidade", "").strip(),
            request.form["tipo_angulo"],
            request.form["sentido"],
            int(request.form["azimute_graus"]),
            int(request.form["azimute_minutos"]),
            float(request.form["azimute_segundos"]),
            int(request.form["ponto_azimute"]),
            float(request.form["x_inicial"]),
            float(request.form["y_inicial"]),
            float(request.form["tolerancia_angular_segundos"]),
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
    if not tabela_levantamento_existe():
        estatisticas = obter_estatisticas()
        return render_template(
            "levantamentos.html",
            levantamentos=[],
            pagina_ativa="levantamentos",
            nome_busca="",
            cidade_busca="",
            lados_busca="",
            ordenacao="mais_recente",
            **estatisticas
        )

    nome_busca = request.args.get("nome", "").strip()
    cidade_busca = request.args.get("cidade", "").strip()
    lados_busca = request.args.get("lados", "").strip()
    ordenacao = request.args.get("ordenacao", "mais_recente")

    conexao = conectar()
    cursor = conexao.cursor()

    query = """
        SELECT id, nome, lados, cidade, tipo_angulo, sentido,
               azimute_graus, azimute_minutos, azimute_segundos,
               ponto_azimute, x_inicial, y_inicial,
               tolerancia_angular_segundos, criterio_precisao, created_at
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
               azimute_graus, azimute_minutos, azimute_segundos,
               ponto_azimute, x_inicial, y_inicial,
               tolerancia_angular_segundos, criterio_precisao, created_at
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
        quantidade_lados = int(levantamento["lados"])
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
                       azimute_graus, azimute_minutos, azimute_segundos,
                       ponto_azimute, x_inicial, y_inicial,
                       tolerancia_angular_segundos, criterio_precisao, created_at
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
                azimute_graus = ?, azimute_minutos = ?, azimute_segundos = ?,
                ponto_azimute = ?, x_inicial = ?, y_inicial = ?,
                tolerancia_angular_segundos = ?, criterio_precisao = ?
            WHERE id = ?
        """, (
            request.form["nome"].strip(),
            int(request.form["lados"]),
            request.form.get("cidade", "").strip(),
            request.form["tipo_angulo"],
            request.form["sentido"],
            int(request.form["azimute_graus"]),
            int(request.form["azimute_minutos"]),
            float(request.form["azimute_segundos"]),
            int(request.form["ponto_azimute"]),
            float(request.form["x_inicial"]),
            float(request.form["y_inicial"]),
            float(request.form["tolerancia_angular_segundos"]),
            int(request.form["criterio_precisao"]),
            id
        ))

        conexao.commit()
        conexao.close()
        flash("Levantamento atualizado com sucesso.", "sucesso")
        return redirect(url_for("detalhe_levantamento", id=id))

    cursor.execute("""
        SELECT id, nome, lados, cidade, tipo_angulo, sentido,
               azimute_graus, azimute_minutos, azimute_segundos,
               ponto_azimute, x_inicial, y_inicial,
               tolerancia_angular_segundos, criterio_precisao, created_at
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
    pdf.drawString(40, y, f"Ponto do azimute conhecido: {resultado['ponto_azimute_nome']}")
    y -= 14
    pdf.drawString(40, y, f"Azimute inicial: {resultado['azimute_inicial_dms']}")
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
        f"Soma dos ângulos: {resultado['soma_angulos']:.6f}",
        f"Soma teórica: {resultado['soma_teorica']:.6f}",
        f"Soma compensada: {resultado['soma_compensada']:.6f}",
        f"Erro angular: {resultado['erro_angular']:.6f}",
        f"Erro angular (seg): {resultado['erro_angular_segundos']:.3f}",
        f"Tolerância angular: {resultado['tolerancia_segundos']:.3f}",
        f"Erro em X (Ex): {resultado['ex']:.3f}",
        f"Erro em Y (Ey): {resultado['ey']:.3f}",
        f"Erro linear: {resultado['erro_linear']:.3f}",
        f"Perímetro: {resultado['perimetro']:.3f}",
        f"Classificação da precisão: {resultado['classificacao_precisao']}",
        f"Condição de fechamento em X: {resultado['soma_dx_comp']:.6f}",
        f"Condição de fechamento em Y: {resultado['soma_dy_comp']:.6f}",
    ]

    if resultado["modulo_escala"] == float("inf"):
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
        y = nova_pagina("Tabela principal")

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(40, y, "Tabela principal")
    y -= 18

    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(40, y, "Lado")
    pdf.drawString(70, y, "Ponto")
    pdf.drawString(120, y, "Dist.")
    pdf.drawString(170, y, "Âng. lido")
    pdf.drawString(250, y, "Corr.")
    pdf.drawString(295, y, "Âng. comp.")
    pdf.drawString(380, y, "Azimute")
    y -= 10
    pdf.line(40, y, 560, y)
    y -= 10

    pdf.setFont("Helvetica", 8)
    for i in range(len(resultado["distancias"])):
        if y < 45:
            y = nova_pagina("Tabela principal")
            pdf.setFont("Helvetica-Bold", 8)
            pdf.drawString(40, y, "Lado")
            pdf.drawString(70, y, "Ponto")
            pdf.drawString(120, y, "Dist.")
            pdf.drawString(170, y, "Âng. lido")
            pdf.drawString(250, y, "Corr.")
            pdf.drawString(295, y, "Âng. comp.")
            pdf.drawString(380, y, "Azimute")
            y -= 10
            pdf.line(40, y, 560, y)
            y -= 10
            pdf.setFont("Helvetica", 8)

        pdf.drawString(40, y, str(i + 1))
        pdf.drawString(70, y, str(resultado["nomes_pontos"][i]))
        pdf.drawString(120, y, f"{resultado['distancias'][i]:.3f}")
        pdf.drawString(170, y, resultado["angulos_dms"][i])
        pdf.drawString(250, y, f"{resultado['correcoes_angulares_segundos'][i]}\"")
        pdf.drawString(295, y, resultado["angulos_compensados_dms"][i])
        pdf.drawString(380, y, resultado["azimutes_dms"][i])
        y -= 12

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

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)