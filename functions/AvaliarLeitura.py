import json
import os
from datetime import datetime

BASE_PATH = os.path.dirname(os.path.dirname(__file__))  

DATA_PATH = os.path.join(BASE_PATH, "data")
QUEUE_PATH = os.path.join(BASE_PATH, "queue")

ARQ_LEITURAS = os.path.join(DATA_PATH, "leituras.json")
ARQ_FILA = os.path.join(QUEUE_PATH, "filaLeituras.json")
ARQ_CONFIG_ALERTAS = os.path.join(DATA_PATH, "configAlertas.json")
ARQ_NOTIFICACOES = os.path.join(QUEUE_PATH, "notificacaoAlerta.json")

ARQ_FILA_AUDITORIA = os.path.join(QUEUE_PATH, "filaAuditoria.json")


def carregar_json(caminho):
    if not os.path.exists(caminho):
        return {}
    with open(caminho, "r") as f:
        return json.load(f)


def salvar_json(caminho, dados):
    with open(caminho, "w") as f:
        json.dump(dados, f, indent=4)


def enviar_evento_auditoria(leitura, alerta_acionado):
    """
    Envia para fila de auditoria no formato desejado.
    """
    fila_audit = carregar_json(ARQ_FILA_AUDITORIA)

    if "eventos" not in fila_audit:
        fila_audit["eventos"] = []

    evento = {
        "date": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "detalhes": {
            "sensorId": leitura["sensorId"],
            "temperatura": leitura["temperatura"],
            "umidade": leitura["umidade"],
            "date": leitura["date"],
            "alerta acionado": "sim" if alerta_acionado else "não"
        }
    }

    fila_audit["eventos"].append(evento)
    salvar_json(ARQ_FILA_AUDITORIA, fila_audit)

    print("📤 Evento de auditoria registrado na fila.")


def avaliar_leituras():
    fila = carregar_json(ARQ_FILA)

    if "mensagens" not in fila or len(fila["mensagens"]) == 0:
        print("⚠ Fila vazia. Nada para avaliar.")
        return

    config = carregar_json(ARQ_CONFIG_ALERTAS)
    if "alertas" not in config:
        config["alertas"] = []

    limites = config.get("limites", {})
    tempMax = limites.get("tempMax")
    umiMax = limites.get("umiMax")

    notificacoes = carregar_json(ARQ_NOTIFICACOES)
    if "notificacoes" not in notificacoes:
        notificacoes["notificacoes"] = []

    print("\n=== Avaliando Leituras da Fila ===")

    for leitura in fila["mensagens"]:
        sensor = leitura["sensorId"]
        temp = leitura["temperatura"]
        umi = leitura["umidade"]

        temp_alerta = tempMax is not None and temp > tempMax
        umi_alerta = umiMax is not None and umi > umiMax

        alerta_acionado = temp_alerta or umi_alerta

        if alerta_acionado:
            print(f"🚨 ALERTA! Sensor {sensor} ultrapassou os limites!")

            alerta = {
                "sensorId": sensor,
                "temperatura": temp,
                "umidade": umi,
                "date": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            }

            config["alertas"].append(alerta)
            notificacoes["notificacoes"].append(alerta)

            print("✔ Gravado em configAlertas.json")
            print("✔ Gravado em notificacaoAlerta.json")
            print("✔ Notificação SNS simulada (SMS enviado)")

        else:
            print(f"✔ Sensor {sensor}: dentro dos limites.")

        # 🔵 SEMPRE manda para auditoria agora
        enviar_evento_auditoria(leitura, alerta_acionado)

    salvar_json(ARQ_CONFIG_ALERTAS, config)
    salvar_json(ARQ_NOTIFICACOES, notificacoes)

    fila["mensagens"] = []
    salvar_json(ARQ_FILA, fila)

    print("\n✔ Fila processada e limpa!")


if __name__ == "__main__":
    avaliar_leituras()
