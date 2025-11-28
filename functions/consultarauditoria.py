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


def processar_fila_para_banco():
    """
    Move todos os REGISTROS de filaAuditoria.json para auditoriaEventos.json
    (simulação de consumir SQS e gravar em um banco).
    """
    fila = carregar_json(ARQ_FILA_AUDITORIA)
    dados_auditoria = carregar_json(ARQ_AUDITORIA)

    mensagens = fila.get("mensagens", [])
    if "eventos" not in dados_auditoria:
        dados_auditoria["eventos"] = []

    if mensagens:
        dados_auditoria["eventos"].extend(mensagens)
        print(f"✔ {len(mensagens)} registros movidos da fila para auditoriaEventos.json")

    # Limpa a fila
    fila["mensagens"] = []

    salvar_json(ARQ_AUDITORIA, dados_auditoria)
    salvar_json(ARQ_FILA_AUDITORIA, fila)


def consultar_eventos(
    sensorId=None,
    tipo_evento=None,
    tipo_sensor=None,
    somente_acionados=False,
    limite=50
):
    """
    Consulta REGISTROS já persistidos em auditoriaEventos.json

    Filtros opcionais:
      - sensorId         (detalhes.sensorId)
      - tipo_evento      (campo tipoEvento)  [usado pelo handler da Lambda]
      - tipo_sensor      (detalhes.tipoSensor) [não usado no menu atual]
      - somente_acionados: True -> apenas registros com detalhes.acionado == True
    """
    dados = carregar_json(ARQ_AUDITORIA)
    eventos = dados.get("eventos", [])

    filtrados = []
    # Mais recentes primeiro
    for e in reversed(eventos):
        if tipo_evento and e.get("tipoEvento") != tipo_evento:
            continue

        detalhes = e.get("detalhes", {}) or {}

        if sensorId and detalhes.get("sensorId") != sensorId:
            continue

        if tipo_sensor and detalhes.get("tipoSensor") != tipo_sensor:
            continue

        if somente_acionados and not detalhes.get("acionado", False):
            continue

        filtrados.append(e)

        if limite and len(filtrados) >= limite:
            break

    return filtrados


# ============================
# Handler da Lambda (API GW)
# ============================

def lambda_handler(event, context):
    """
    GET /auditoria?sensorId=sensor-01&tipoEvento=ALERTA_DISPARADO&limite=20
    (mantido para compatibilidade; o menu de terminal usa outros filtros)
    """

    # 1) Primeiro, consome a fila e grava no "banco"
    processar_fila_para_banco()

    params = (event or {}).get("queryStringParameters") or {}

    sensor_id = params.get("sensorId")
    tipo_evento = params.get("tipoEvento")

    try:
        limite = int(params.get("limite", "50"))
    except ValueError:
        limite = 50

    registros = consultar_eventos(
        sensorId=sensor_id,
        tipo_evento=tipo_evento,
        limite=limite
    )

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(registros, ensure_ascii=False)
    }


# ============================
# Funções extras para TERMINAL
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


def registrar_registro_teste():
    """
    Insere na FILA um REGISTRO de auditoria de teste
    usando dados do ÚLTIMO ALERTA gravado pela Lambda AvaliarLeituras.
    (não exposto no menu; pode ser usado em testes manuais se quiser)
    """
    alerta = obter_ultimo_alerta()
    if not alerta:
        print("⚠ Nenhum alerta encontrado em configAlertas.json.")
        print("  Rode a Lambda AvaliarLeituras primeiro para gerar alertas.")
        return

    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    sensor_id = alerta.get("sensorId")
    if isinstance(sensor_id, str) and "-" in sensor_id:
        tipo_sensor = sensor_id.split("-")[0]
    else:
        tipo_sensor = "desconhecido"

    registro_teste = {
        "tipoEvento": "TESTE_ALERTA",
        "date": agora,
        "detalhes": {
            "sensorId": sensor_id,
            "temperatura": alerta.get("temperatura"),
            "umidade": alerta.get("umidade"),
            "date": alerta.get("date"),    # data da leitura/alerta original
            "tipoSensor": tipo_sensor,
            "acionado": True               # foi acionado (alerta gerado)
        }
    }

    fila = carregar_json(ARQ_FILA_AUDITORIA)
    if "mensagens" not in fila:
        fila["mensagens"] = []

    fila["mensagens"].append(registro_teste)
    salvar_json(ARQ_FILA_AUDITORIA, fila)

    print("✔ Registro de TESTE inserido na filaAuditoria.json com base no último alerta.")


def exibir_eventos_no_terminal(registros):
    os.system("cls" if os.name == "nt" else "clear")
    print("==== RESULTADO DA CONSULTA DE AUDITORIA ====\n")

    if not registros:
        print("Nenhum registro encontrado.\n")
        return

    for idx, e in enumerate(registros, start=1):
        print(f"Registro #{idx}")

        detalhes = e.get("detalhes", {}) or {}

        sensor_id = detalhes.get("sensorId")
        temperatura = detalhes.get("temperatura")
        umidade = detalhes.get("umidade")
        data_leitura = detalhes.get("date")
        tipo_sensor = detalhes.get("tipoSensor")
        acionado = detalhes.get("alerta acionado", False)

        # Dados principais do sensor
        print("  Dados do sensor / alerta:")
        if sensor_id:
            print(f"    - sensorId:    {sensor_id}")
        if tipo_sensor:
            print(f"    - tipoSensor:  {tipo_sensor}")
        if temperatura is not None:
            print(f"    - temperatura: {temperatura}")
        if umidade is not None:
            print(f"    - umidade:     {umidade}")
        if data_leitura:
            print(f"    - date:        {data_leitura}")
        print(f"    - alerta acionado:   {bool(acionado)}")

        # Outros detalhes, se houver
        outros = {
            k: v for k, v in detalhes.items()
            if k not in {"sensorId", "temperatura", "umidade", "date", "tipoSensor", "acionado"}
        }
        if outros:
            print("  Outros detalhes:")
            for k, v in outros.items():
                print(f"    - {k}: {v}")

        print("-" * 40)
    print()


def exibir_config_alerta_terminal():
    """
    Mostra a configuração atual de alerta (temperatura máxima e umidade máxima)
    baseada no arquivo configAlertas.json.
    """
    os.system("cls" if os.name == "nt" else "clear")
    print("==== CONFIGURAÇÃO ATUAL DE ALERTA ====\n")

    dados = carregar_json(ARQ_CONFIG_ALERTAS)
    limites = dados.get("limites", {})

    temp_max = limites.get("tempMax")
    umi_max = limites.get("umiMax")

    if temp_max is None and umi_max is None:
        print("Nenhuma configuração de limites encontrada em configAlertas.json.\n")
    else:
        if temp_max is not None:
            print(f"Temperatura máxima configurada: {temp_max}")
        else:
            print("Temperatura máxima configurada: não definida")

        if umi_max is not None:
            print(f"Umidade máxima configurada:     {umi_max}")
        else:
            print("Umidade máxima configurada:     não definida")

        print()

    input("Pressione ENTER para voltar ao menu...")


def menu_terminal():
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print("===== MENU AUDITORIA =====")
        print("1 - Filtrar por sensorId")
        print("2 - Listar somente registros que emitiram alerta")
        print("3 - Mostrar configuração atual de alerta")
        print("0 - Sair")
        opcao = input("\nEscolha uma opção: ").strip()

        if opcao == "0":
            print("Saindo...")
            break

        if opcao == "3":
            exibir_config_alerta_terminal()
            continue

        sensor_id = None
        somente_alerta = False

        if opcao == "1":
            sensor_id = input("Informe o sensorId: ").strip() or None
        elif opcao == "2":
            somente_alerta = True
        else:
            print("Opção inválida!")
            input("Pressione ENTER para continuar...")
            continue

        limite_str = input("Limite de registros (padrão 50): ").strip() or "50"
        try:
            limite = int(limite_str)
        except ValueError:
            limite = 50

        # Sempre processa a fila antes de consultar
        processar_fila_para_banco()

        registros = consultar_eventos(
            sensorId=sensor_id,
            somente_acionados=somente_alerta,
            limite=limite
        )

        exibir_eventos_no_terminal(registros)
        input("Pressione ENTER para voltar ao menu...")


if __name__ == "__main__":
    menu_terminal()