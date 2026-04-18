# Politech – Sistema de Cálculo de Poligonais Fechadas

Sistema web desenvolvido para auxiliar no cálculo, ajuste e visualização de poligonais fechadas, com foco em clareza, organização e transparência dos processos topográficos.

---

## 🎯 Objetivo

O Politech tem como objetivo facilitar o entendimento e a execução dos cálculos de levantamentos planimétricos, apresentando cada etapa do processo de forma estruturada e visual.

A proposta do sistema é permitir que o usuário não apenas obtenha o resultado final, mas compreenda **como cada cálculo está sendo realizado**, seguindo a metodologia topográfica.

---

## ⚙️ Funcionalidades atuais

- Interface web estruturada com Flask
- Cadastro de levantamentos
- Inserção de lados e dados da poligonal
- Organização das páginas (histórico, metodologia, estatísticas, etc.)
- Separação da lógica de cálculo em serviços
- Estrutura preparada para cálculo completo da poligonal fechada

---

## 🧠 Metodologia aplicada

O sistema segue a sequência clássica de cálculo e ajuste de poligonais fechadas, incluindo:

- Soma teórica dos ângulos
- Cálculo do erro angular
- Verificação da tolerância angular
- Correção dos ângulos
- Cálculo de azimutes
- Cálculo das projeções (ΔX e ΔY)
- Cálculo do erro de fechamento linear
- Ajuste proporcional das projeções
- Cálculo das coordenadas finais

---

## 🛠️ Tecnologias utilizadas

- Python (Flask)
- HTML5
- CSS3
- JavaScript
- SQLite (estrutura prevista)

---

# Clonar o repositório
git clone https://github.com/SEU-USUARIO/politech.git

# Entrar na pasta
cd politech

# Instalar dependências
pip install flask

# Executar o sistema
python app.py

Acesse no navegador: http://127.0.0.1:5000

⚠️ Status do projeto

🚧 Projeto em desenvolvimento

Atualmente, o sistema está com a estrutura principal da interface e organização lógica implementadas, porém ainda existem etapas em andamento:

❗ Implementação completa do banco de dados
❗ Ajustes e validações nos cálculos da poligonal fechada
❗ Integração total entre interface e processamento dos dados
❗ Refinamento dos resultados e validações topográficas

🚀 Próximas melhorias
Implementação completa do banco de dados (persistência dos levantamentos)
Finalização do motor de cálculo da poligonal


## 📂 Estrutura do projeto

```bash
politech/
├─ app.py
├─ models.py
├─ database.py
├─ services/
│  └─ poligonal_service.py
├─ templates/
│  ├─ index.html
│  ├─ levantamentos.html
│  ├─ novo_levantamento.html
│  ├─ resultado.html
│  └─ ...
├─ static/
│  ├─ css/
│  ├─ js/
│  └─ img/
├─ instance/
├─ graficos/

