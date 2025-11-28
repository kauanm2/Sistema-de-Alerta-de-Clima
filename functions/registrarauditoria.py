import json
import os
from datetime import datetime

BASE_PATH = os.path.dirname(os.path.dirname(__file__))

DATA_PATH = os.path.join(BASE_PATH, "data")
QUEUE_PATH = os.path.join(BASE_PATH, "queue")

ARQ_AUDITORIA = os.path.join(DATA_PATH, "auditoriaEventos.json")   
ARQ_FILA_AUDITORIA = os.path.join(QUEUE_PATH, "filaAuditoria.json")  
ARQ_CONFIG_ALERTAS = os.path.join(DATA_PATH, "configAlertas.json")   


def carregar_json(caminho):
    if not os.path.exists(caminho):
        return {}
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar_json(caminho, dados):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)


def registrar_registro_auditoria(detalhes):
    """
    Recebe 'detalhes' e grava DIRETAMENTE em auditoriaEventos.json.

    Estrutura em auditoriaEventos.json:
    {
      "eventos": [
        {
          "date": "data/hora do REGISTRO DE AUDITORIA",
          "detalhes": { ... dados do sensor/alerta ... }
        },
        ...
      ]
    }
    """
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    registro = {
        "date": agora,       # data do registro de auditoria
        "detalhes": detalhes or {}
    }

    dados_auditoria = carregar_json(ARQ_AUDITORIA)
    if "eventos" not in dados_auditoria:
        dados_auditoria["eventos"] = []

    dados_auditoria["eventos"].append(registro)
    salvar_json(ARQ_AUDITORIA, dados_auditoria)

    print("✔ Registro de auditoria gravado em auditoriaEventos.json")
    return registro


def processar_fila_auditoria():
    """
    Lê todas as mensagens da fila de auditoria (filaAuditoria.json),
    grava cada uma no banco de auditoria (auditoriaEventos.json)
    e ESVAZIA a fila.
    """
    fila = carregar_json(ARQ_FILA_AUDITORIA)
    mensagens = fila.get("mensagens", [])

    registros_processados = []

    if not mensagens:
        print("⚠ Fila de auditoria vazia. Nada para processar.")
    else:
        for msg in mensagens:
            # Suporta tanto mensagens no formato {"detalhes": {...}}
            # quanto diretamente {...}
            if isinstance(msg, dict) and "detalhes" in msg:
                detalhes = msg.get("detalhes") or {}
            else:
                detalhes = msg or {}

            reg = registrar_registro_auditoria(detalhes)
            registros_processados.append(reg)

        print(f"✔ {len(registros_processados)} registros processados da fila de auditoria.")

    # Esvazia a fila
    fila["mensagens"] = []
    salvar_json(ARQ_FILA_AUDITORIA, fila)
    print("✔ Fila de auditoria esvaziada.")

    return registros_processados


# ============================
# Handler da Lambda (API GW)
# ============================

def lambda_handler(event, context):
    """
    Essa Lambda NÃO usa o payload da requisição.
    Ela apenas:
      - lê a filaAuditoria.json
      - grava tudo em auditoriaEventos.json
      - esvazia a fila
      - retorna quantos registros foram processados
    """

    registros = processar_fila_auditoria()

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "quantidadeProcessada": len(registros),
                "registros": registros
            },
            ensure_ascii=False
        )
    }


# ============================
# TESTE LOCAL
# ============================

def obter_ultimo_alerta():
    """
    Lê o 'banco' usado pela Lambda AvaliarLeituras (configAlertas.json)
    e retorna o último alerta registrado.
    """
    dados = carregar_json(ARQ_CONFIG_ALERTAS)
    alertas = dados.get("alertas", [])
    if not alertas:
        return None
    return alertas[-1]


def teste_fila_com_ultimo_alerta():
    """
    Teste local:
    - pega o último alerta de configAlertas.json
    - coloca na FILA de auditoria (filaAuditoria.json) como uma mensagem
    - chama processar_fila_auditoria()
    """
    alerta = obter_ultimo_alerta()
    if not alerta:
        print("⚠ Nenhum alerta encontrado em configAlertas.json.")
        print("  Rode a Lambda AvaliarLeituras primeiro para gerar alertas.")
        return

    # Monta mensagem no formato da fila: {"detalhes": {...}}
    mensagem = {
        "detalhes": {
            "sensorId": alerta.get("sensorId"),
            "temperatura": alerta.get("temperatura"),
            "umidade": alerta.get("umidade"),
            "date": alerta.get("date"),   # data da leitura/alerta original
            "acionado": True
        }
    }

    fila = carregar_json(ARQ_FILA_AUDITORIA)
    if "mensagens" not in fila:
        fila["mensagens"] = []

    fila["mensagens"].append(mensagem)
    salvar_json(ARQ_FILA_AUDITORIA, fila)
    print("✔ Mensagem de teste inserida na filaAuditoria.json")

    # Agora processa a fila e grava no banco
    registros = processar_fila_auditoria()

    print("\nRegistros gerados a partir da fila:")
    print(json.dumps(registros, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    # Executar teste local:
    # python registrarAuditoria.py
    teste_fila_com_ultimo_alerta()