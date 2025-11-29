import os
import json
from datetime import datetime

from flask import Flask, request, jsonify

# ============================================================
# Configuração de paths (igual ao restante do projeto)
# ============================================================

BASE_PATH = os.path.dirname(os.path.abspath(__file__))

DATA_PATH = os.path.join(BASE_PATH, "date")
QUEUE_PATH = os.path.join(BASE_PATH, "queue")

ARQ_AUDITORIA = os.path.join(DATA_PATH, "auditoriaEventos.json")
ARQ_FILA_AUDITORIA = os.path.join(QUEUE_PATH, "filaAuditoria.json")
ARQ_CONFIG_ALERTAS = os.path.join(DATA_PATH, "configAlertas.json")


# ============================================================
# Funções utilitárias de arquivo JSON
# ============================================================

def carregar_json(caminho):
    if not os.path.exists(caminho):
        return {}
    with open(caminho, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def salvar_json(caminho, dados):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)


# ============================================================
# Lógica de AUDITORIA (coerente com as Lambdas)
# ============================================================

def registrar_registro_auditoria(detalhes):
    """
    Grava diretamente em auditoriaEventos.json:
    {
      "eventos": [
        { "date": "...", "detalhes": {...} }
      ]
    }
    """
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    registro = {
        "date": agora,
        "detalhes": detalhes or {}
    }

    dados_auditoria = carregar_json(ARQ_AUDITORIA)
    if "eventos" not in dados_auditoria:
        dados_auditoria["eventos"] = []

    dados_auditoria["eventos"].append(registro)
    salvar_json(ARQ_AUDITORIA, dados_auditoria)

    return registro


def registrar_evento_na_fila(detalhes):
    """
    Simula o produtor de auditoria:
    grava na fila queue/filaAuditoria.json (campo 'mensagens') no formato:
    { "detalhes": { ... } }
    """
    mensagem = {"detalhes": detalhes or {}}

    fila = carregar_json(ARQ_FILA_AUDITORIA)
    if "mensagens" not in fila:
        fila["mensagens"] = []

    fila["mensagens"].append(mensagem)
    salvar_json(ARQ_FILA_AUDITORIA, fila)

    return mensagem


def processar_fila_para_banco():
    """
    Consumidor da fila:
    - lê queue/filaAuditoria.json
    - para cada mensagem, chama registrar_registro_auditoria(detalhes)
    - esvazia a fila
    - retorna a lista de registros gravados
    """
    fila = carregar_json(ARQ_FILA_AUDITORIA)
    mensagens = fila.get("mensagens", [])

    registros_processados = []

    for msg in mensagens:
        if isinstance(msg, dict) and "detalhes" in msg:
            detalhes = msg.get("detalhes") or {}
        else:
            detalhes = msg or {}
        reg = registrar_registro_auditoria(detalhes)
        registros_processados.append(reg)

    # esvazia a fila
    fila["mensagens"] = []
    salvar_json(ARQ_FILA_AUDITORIA, fila)

    return registros_processados


def consultar_eventos(sensorId=None, somente_acionados=False, limite=50):
    """
    Consulta os registros gravados em date/auditoriaEventos.json
    Filtros:
      - sensorId          (detalhes.sensorId)
      - somente_acionados (detalhes.acionado == True)
    """
    dados = carregar_json(ARQ_AUDITORIA)
    eventos = dados.get("eventos", [])

    filtrados = []
    for e in reversed(eventos):  # mais recentes primeiro
        detalhes = e.get("detalhes", {}) or {}

        if sensorId and detalhes.get("sensorId") != sensorId:
            continue

        if somente_acionados and not detalhes.get("acionado", False):
            continue

        filtrados.append(e)
        if limite and len(filtrados) >= limite:
            break

    return filtrados


def obter_config_alerta():
    dados = carregar_json(ARQ_CONFIG_ALERTAS)
    limites = dados.get("limites", {})
    return {
        "tempMax": limites.get("tempMax"),
        "umiMax": limites.get("umiMax")
    }


# ============================================================
# Flask APP (API REST semelhante ao API Gateway + Lambdas)
# ============================================================

app = Flask(__name__)


@app.route("/auditoria", methods=["POST"])
def registrar_auditoria():
    """
    POST /auditoria
    Body JSON (dois formatos aceitos):

    1) Somente detalhes:
    {
      "sensorId": "sensor-01",
      "temperatura": 32.5,
      "umidade": 70,
      "date": "10/10/2024 10:10:10",
      "acionado": true
    }

    2) Envolto em 'detalhes':
    {
      "detalhes": {
        "sensorId": "sensor-01",
        "temperatura": 32.5,
        "umidade": 70,
        "date": "10/10/2024 10:10:10",
        "acionado": true
      }
    }
    """
    dados = request.get_json(silent=True) or {}

    # aceita tanto {"detalhes": {...}} quanto {...} direto
    if "detalhes" in dados and isinstance(dados["detalhes"], dict):
        detalhes = dados["detalhes"]
    else:
        detalhes = dados

    # se não vier date na leitura, coloca agora
    if "date" not in detalhes:
        detalhes["date"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # se não vier acionado, por padrão False
    if "acionado" not in detalhes:
        detalhes["acionado"] = False

    mensagem = registrar_evento_na_fila(detalhes)

    # 202 = Accepted (aceito para processamento assíncrono)
    return jsonify(mensagem), 202


@app.route("/auditoria", methods=["GET"])
def consultar_auditoria():
    """
    GET /auditoria?sensorId=sensor-01&somenteAlerta=true&limite=20
    - Primeiro processa a fila -> grava no "banco"
    - Depois consulta auditoriaEventos.json
    """
    sensor_id = request.args.get("sensorId")
    somente_alerta_str = (request.args.get("somenteAlerta") or "").lower()
    somente_alerta = somente_alerta_str in ("1", "true", "t", "sim", "yes", "y")

    try:
        limite = int(request.args.get("limite", "50"))
    except ValueError:
        limite = 50

    # processa a fila (como a Lambda registrar/processarFila)
    processar_fila_para_banco()

    # consulta o "banco" de auditoria
    eventos = consultar_eventos(
        sensorId=sensor_id,
        somente_acionados=somente_alerta,
        limite=limite
    )

    return jsonify(eventos), 200


@app.route("/auditoria/config", methods=["GET"])
def consultar_config_alerta():
    """
    GET /auditoria/config
    Retorna a configuração atual de alerta (tempMax, umiMax)
    baseada em configAlertas.json
    """
    cfg = obter_config_alerta()
    return jsonify(cfg), 200


if __name__ == "__main__":
    # Modo desenvolvimento
    app.run(host="0.0.0.0", port=5000, debug=True)