import json
import os
from datetime import datetime

BASE_PATH = os.path.dirname(os.path.dirname(__file__))  

DATA_PATH = os.path.join(BASE_PATH, "data")
QUEUE_PATH = os.path.join(BASE_PATH, "queue")

ARQ_LEITURAS = os.path.join(DATA_PATH, "leituras.json")
ARQ_FILA = os.path.join(QUEUE_PATH, "filaLeituras.json")


def carregar_json(caminho):
    if not os.path.exists(caminho):
        return {}
    with open(caminho, "r") as f:
        return json.load(f)


def salvar_json(caminho, dados):
    with open(caminho, "w") as f:
        json.dump(dados, f, indent=4)


def registrar_leitura(sensorId, temperatura, umidade, date=None):
    if date is None:
        date = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    nova_leitura = {
        "sensorId": sensorId,
        "temperatura": temperatura,
        "umidade": umidade,
        "date": date
    }
    

    # 1. Salvar em LEITURAS
    dados_leituras = carregar_json(ARQ_LEITURAS)
    if "leituras" not in dados_leituras:
        dados_leituras["leituras"] = []

    dados_leituras["leituras"].append(nova_leitura)
    salvar_json(ARQ_LEITURAS, dados_leituras)

    print("✔ Leitura registrada em LEITURAS.json")

    # 2. Adicionar na FILA
    fila = carregar_json(ARQ_FILA)
    if "mensagens" not in fila:
        fila["mensagens"] = []

    fila["mensagens"].append(nova_leitura)
    salvar_json(ARQ_FILA, fila)

    print("✔ Leitura adicionada à FILA (queue/filaLeituras.json)")


if __name__ == "__main__":
    registrar_leitura("sensor-01", 32.5, 70)
