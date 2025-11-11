import asyncio
import json
import logging
import numpy as np

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, PeriodicBehaviour
from spade.template import Template
from spade.message import Message

# Configuração de Logging
logger = logging.getLogger("FarmEnvironmentAgent")


# --- Constantes e Tipos de Mensagem ---
# Performatives para interações Agente-Ambiente
PERFORMATIVE_REQUEST = "request"
PERFORMATIVE_INFORM = "inform"
PERFORMATIVE_ACT = "act"

# Ontology para interações Agente-Ambiente
ONTOLOGY_FARM_DATA = "farm_data"
ONTOLOGY_FARM_ACTION = "farm_action"
ONTOLOGY_DYNAMIC_EVENT = "dynamic_event"


def display_matrix(field):
    """Imprime o estado atual do ambiente."""
    print("\n==================================================================")
    print("==================================================================")
    print("==================================================================\n")
    print(f"Day: {field.day} \t Hour: {field.hours}")
    print(f"Temperatura: {field.temperature.temperature}")
    print(f"Rain: {field.rain.rain}   Hours_remaining: {field.rain._rain_hours_remaining}")
    print("Humidade:")
    print(np.array2string(field.moisture.moisture, precision=2, separator=', ', suppress_small=True))
    print("\nNutrientes:")
    print(np.array2string(field.nutrients.nutrients, precision=2, separator=', ', suppress_small=True))
    print("\nCrop_stage:")
    print(np.array2string(field.crop.crop_stage, precision=2, separator=', ', suppress_small=True))
    print("\nCrop_type:")
    print(np.array2string(field.crop.crop_type, precision=2, separator=', ', suppress_small=True))
    print("\nCrop_health:")
    print(np.array2string(field.crop.crop_health, precision=2, separator=', ', suppress_small=True))
    print("\nPest:")
    print(np.array2string(field.pest.pest, precision=2, separator=', ', suppress_small=True))
    print("\n==================================================================")

# --- Comportamentos ---

class EnvironmentTicker(PeriodicBehaviour):
    """
    Comportamento Periódico para avançar o estado do ambiente (Field.step()).
    Simula a passagem do tempo.
    """
    def __init__(self, period, field_instance):
        super().__init__(period)
        self.field = field_instance

    async def run(self):
        self.field.step()
        logger.info(50*"=")
        logger.info(f"TICK: Ambiente avançou para o dia {self.field.day}, hora {self.field.hours}. Seca: {self.field.drought}, Peste: {self.field.isPestActive}, Temperatura: {self.field.temperature.temperature}")
        logger.info(50*"=")

class EnvironmentManager(CyclicBehaviour):
    """
    Comportamento Cíclico para receber e processar todas as mensagens de interação
    (Perceção, Atuação e Eventos Dinâmicos).
    """
    def __init__(self, field_instance):
        super().__init__()
        self.field = field_instance


    async def run(self):
        # Espera por qualquer mensagem
        msg = await self.receive(timeout=5)
        if msg:
            try:
                logger.debug(f"Mensagem recebida raw: from={msg.sender}, metadata={msg.metadata}, body={msg.body}")
                content = json.loads(msg.body)
                action = content.get("action")
                
                if not action:
                    logger.warning(f"Mensagem recebida sem 'action': {msg.body}")
                    return

                logger.info(f"Mensagem recebida: {action} de {msg.sender}")

                # 1. Processar Eventos Dinâmicos (Controlo Humano)
                if msg.metadata.get("ontology") == ONTOLOGY_DYNAMIC_EVENT:
                    await self.handle_dynamic_event(msg, content, action)
                
                # 2. Processar Pedidos de Agentes (Perceção/Atuação)
                elif msg.metadata.get("ontology") in [ONTOLOGY_FARM_DATA, ONTOLOGY_FARM_ACTION]:
                    await self.handle_agent_request(msg, content, action)
                
                else:
                    logger.warning(f"Ontology desconhecida: {msg.metadata.get('ontology')}")

            except json.JSONDecodeError:
                logger.exception(f"Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                logger.exception(f"Erro ao processar mensagem: {e}")
        else:
            # Sem mensagem, espera um pouco antes do próximo ciclo
            await asyncio.sleep(0.1)

    async def handle_dynamic_event(self, msg, content, action):
        """
        Processa comandos de Eventos Dinâmicos (Chuva, Seca, Peste)
        que o utilizador pode ativar/desativar.
        """
        response_body = {"status": "success", "action": action}
        
        if action == "apply_rain":
            intensity = content.get("intensity") 
            self.field.apply_rain(intensity)
            response_body["message"] = f"Chuva de intensidade {intensity} ativada."
        
        elif action == "stop_rain":
            self.field.stop_rain()
            response_body["message"] = "Chuva parada."

        elif action == "toggle_drought":
            self.field.toggle_drought()
            drought_status = "ATIVA" if self.field.drought == 1 else "INATIVA"
            response_body["message"] = f"Seca alternada. Estado atual: {drought_status}"

        elif action == "apply_pest":
            self.field.apply_pest()
            response_body["message"] = "Peste ativada numa célula aleatória."

        elif action == "remove_pest":
            self.field.remove_pest()
            response_body["message"] = "Peste removida (grelha limpa)."

        elif action == "view_environment":
            # Apenas imprime o ambiente no lado do EnvironmentAgent e envia confirmação
            display_matrix(self.field)
            response_body["message"] = "Ambiente visualizado."

        else:
            response_body = {"status": "error", "message": f"Evento dinâmico desconhecido: {action}"}

        # Envia confirmação ao remetente
        reply = Message(to=str(msg.sender), body=json.dumps(response_body))
        reply.set_metadata("performative", PERFORMATIVE_INFORM)
        reply.set_metadata("ontology", ONTOLOGY_DYNAMIC_EVENT)
        await self.send(reply)


    async def handle_agent_request(self, msg, content, action):
        """
        Processa pedidos de Perceção (REQUEST) e Atuação (ACT) dos agentes.
        """
        response_body = {"status": "success", "action": action}
        
        try:
            row = content.get("row")
            col = content.get("col")
            logger.info(f"Recebida mensagem: metadata={msg.metadata} body={msg.body}")

            # --- Ações de Perceção (REQUEST) ---
            if msg.get_metadata("performative") == PERFORMATIVE_REQUEST:
                if action == "get_soil":
                    data = self.field.get_soil(row, col)
                    response_body["data"] = {
                        "temperature": round(data[0],2),
                        "nutrients": round(data[1],2),
                        "moisture": round(data[2],2),
                    }
                elif action == "get_drone":
                    data = self.field.get_drone(row, col)
                    response_body["data"] = {
                        "crop_stage": int(data[0]),
                        "crop_type": int(data[1]),
                        "pest_level": int(data[2])
                    }
                else:
                    response_body = {"status": "error", "message": f"Pedido de dados desconhecido: {action}"}
            
            # --- Ações de Atuação (ACT) ---
            elif msg.get_metadata("performative")  == PERFORMATIVE_ACT:
                if action == "apply_irrigation":
                    flow_rate = content.get("flow_rate")
                    self.field.apply_irrigation(row, col, flow_rate)
                    response_body["message"] = f"Irrigação aplicada em ({row},{col}) com taxa {flow_rate}."
                
                elif action == "apply_fertilize":
                    fertilizer_kg = content.get("fertilizer")
                    self.field.apply_fertilize(row, col, fertilizer_kg)
                    response_body["message"] = f"Fertilizante aplicado em ({row},{col})."
                
                elif action == "apply_pesticide":
                    self.field.apply_pesticide(row, col)
                    response_body["message"] = f"Pesticida aplicado em ({row},{col})."

                elif action == "plant_seed":
                    plant_type = content.get("plant_type")
                    if plant_type is None:
                        raise ValueError("plant_type é obrigatório para plant_seed.")
                    self.field.plant_seed(row, col, plant_type)
                    response_body["message"] = f"Semente de tipo {plant_type} plantada em ({row},{col})."

                elif action == "harvest":
                    health = self.field.harvest(row, col)
                    response_body["yield"] = float(health/100)
                    response_body["message"] = f"Colheita realizada em ({row},{col}). Rendimento: {health/100:.2f}."

                else:
                    response_body = {"status": "error", "message": f"Ação desconhecida: {action}"}

            else:
                response_body = {"status": "error", "message": f"Performative não suportada: {msg.performative}"}

        except Exception as e:
            response_body = {"status": "error", "message": f"Erro ao executar ação {action}: {e}"}
            logger.error(f"Erro ao executar ação {action}: {e}")

        # Envia resposta
        reply = Message(to=msg.sender, body=json.dumps(response_body))
        reply.set_metadata("performative", PERFORMATIVE_INFORM)
        reply.set_metadata("ontology", msg.metadata.get("ontology"))
        await self.send(reply)

# --- Agente ---

class FarmEnvironmentAgent(Agent):
    """
    Agente que encapsula a lógica do ambiente (Field) e gere a interação
    com os outros agentes e com o controlo de eventos dinâmicos.
    """
    def __init__(self, jid, password, Field, verify_security=False):
        super().__init__(jid, password, verify_security=verify_security)
        self.field = Field
        self.ticker_period = 15 # 30 segundos por "tick" de simulação (pode ser ajustado)

    async def setup(self):
        logger.info(f"FarmEnvironmentAgent {self.jid} a iniciar...")
        
        # 1. Adicionar o Ticker (passagem do tempo)
        ticker_b = EnvironmentTicker(period=self.ticker_period, field_instance=self.field)
        self.add_behaviour(ticker_b)

        # 2. Adicionar o Manager (receber e processar mensagens)
        # Criar um template para eventos dinâmicos (humanos) e outro para pedidos/agentes
        template_dynamic = Template()
        template_dynamic.set_metadata("ontology", ONTOLOGY_DYNAMIC_EVENT)

        template_farm_data = Template()
        template_farm_data.set_metadata("ontology", ONTOLOGY_FARM_DATA)

        template_farm_action = Template()
        template_farm_action.set_metadata("ontology", ONTOLOGY_FARM_ACTION)

        # Adiciona um manager capaz de receber mensagens de eventos dinâmicos (human) e pedidos de agentes.
        # Podemos adicionar o mesmo behaviour com diferentes templates (ou adicionar 1 behaviour sem template).
        self.add_behaviour(EnvironmentManager(self.field), template=template_dynamic)
        self.add_behaviour(EnvironmentManager(self.field), template=template_farm_data)
        self.add_behaviour(EnvironmentManager(self.field), template=template_farm_action)


        logger.info("FarmEnvironmentAgent iniciado com sucesso.")