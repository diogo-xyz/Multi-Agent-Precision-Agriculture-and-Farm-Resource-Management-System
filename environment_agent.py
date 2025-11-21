"""
Módulo FarmEnvironmentAgent para gestão de ambiente agrícola em sistemas multi-agente.

Este módulo implementa um agente SPADE que encapsula e gere o estado de um
ambiente agrícola (Field), processando eventos dinâmicos, perceções de sensores
e atuações de agentes autónomos.
"""

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


def print_matrix(title, matrix):
    """
    Imprime uma matriz formatada no log.
    
    Args:
        title (str): Título a ser exibido antes da matriz.
        matrix (np.ndarray): Matriz a ser impressa.
        
    Note:
        Cada elemento é formatado com 6 caracteres e 2 casas decimais.
    """
    logger.info(f"\n{title}:")
    for row in matrix:
        logger.info(" ".join(f"{x:6.2f}" for x in row))

def display_matrix(field):
    """
    Exibe o estado completo do ambiente agrícola no log.
    
    Apresenta informação detalhada sobre:
    - Dia e hora atuais
    - Temperatura
    - Estado da chuva
    - Matrizes de humidade, nutrientes, estágio das culturas, tipo de culturas,
      saúde das culturas e pragas
    
    Args:
        field (Field): Instância do ambiente agrícola a ser visualizado.
    """
    logger.info("="*70)
    logger.info(f"Dia: {field.day}\tHora: {field.hours}")
    logger.info(f"Temperatura: {field.temperature.temperature:.2f}")
    logger.info(f"Chuva: {field.rain.rain} | Horas restantes: {field.rain._rain_hours_remaining:.2f}")
    
    print_matrix("Humidade", field.moisture.moisture)
    print_matrix("Nutrientes", field.nutrients.nutrients)
    print_matrix("Estágio da Cultura", field.crop.crop_stage)
    print_matrix("Tipo de Cultura", field.crop.crop_type)
    print_matrix("Saúde da Cultura", field.crop.crop_health)
    print_matrix("Pragas", field.pest.pest)
    logger.info("="*70)


# --- Comportamentos ---

class EnvironmentTicker(PeriodicBehaviour):
    """
    Comportamento periódico para avançar o estado do ambiente agrícola.
    
    Este comportamento simula a passagem do tempo, invocando o método step()
    do ambiente em intervalos regulares. Cada tick representa um avanço
    temporal na simulação.
    
    Attributes:
        field (Field): Instância do ambiente agrícola a ser atualizado.
    """

    def __init__(self, period, field_instance):
        """
        Inicializa o ticker do ambiente.
        
        Args:
            period (float): Período em segundos entre cada tick.
            field_instance (Field): Instância do ambiente agrícola.
        """
        
        super().__init__(period)
        self.field = field_instance

    async def run(self):
        """
        Executa um tick de simulação.
        
        Avança o estado do ambiente e regista informações sobre o novo estado.
        Termina automaticamente após n ticks.
        
        Note:
            Quando o limite de ticks é atingido, o comportamento é terminado
            e o agente é parado.
        """

        #logger.info(f"{'=' * 35} ENV {'=' * 35}")
        if self.agent.numb_ticks >=  100: 
            logger.info("Limite de ticks atingido. Parando EnvironmentTicker.")
            logger.info(f"{'=' * 35} ENV {'=' * 35}")
            logger.info("Morreram as seguintes quantidades de plantas:")
            for seed, amount in self.agent.field.crop.dead_crop.items():
                logger.info(f"{self.agent.numb_to_string[seed]}: {amount}")
            logger.info(f"{'=' * 35} ENV {'=' * 35}")
            self.kill()
            asyncio.create_task(self.agent.stop())
            return

        self.field.step()
        logger.info(50*"=")
        logger.info(f"TICK: Ambiente avançou para o dia {self.field.day}, hora {self.field.hours}. Seca: {self.field.drought}, Peste: {self.field.isPestActive}, Temperatura: {self.field.temperature.temperature}")
        logger.info(50*"=")
        self.agent.numb_ticks += 1
        #logger.info(f"{'=' * 35} ENV {'=' * 35}")

class EnvironmentManager(CyclicBehaviour):
    """
    Comportamento cíclico para processar mensagens de interação com o ambiente.
    
    Este comportamento recebe e processa três tipos de mensagens:
    1. Eventos dinâmicos (chuva, seca, pragas) controlados por humanos
    2. Pedidos de perceção de agentes (leituras de sensores)
    3. Ações de atuação de agentes (irrigação, fertilização, etc.)
    
    Attributes:
        field (Field): Instância do ambiente agrícola gerido.
    """

    def __init__(self, field_instance):
        """
        Inicializa o gestor do ambiente.
        
        Args:
            field_instance (Field): Instância do ambiente agrícola a ser gerido.
        """

        super().__init__()
        self.field = field_instance


    async def run(self):
        """
        Processa mensagens recebidas em ciclo contínuo.
        
        Aguarda mensagens, identifica o tipo de pedido através das metadata
        (ontologi e performative) e delega o processamento para os métodos
        apropriados.
        
        Raises:
            json.JSONDecodeError: Se o corpo da mensagem não for JSON válido.
            Exception: Para outros erros no processamento da mensagem.
            
        Note:
            Se não houver mensagens, aguarda 0.1 segundos antes do próximo ciclo.
        """

        # Espera por qualquer mensagem
        msg = await self.receive(timeout=5)
        if msg:
            try:
                #logger.info(f"{'=' * 35} ENV {'=' * 35}")
                logger.debug(f"Mensagem recebida raw: from={msg.sender}, metadata={msg.metadata}, body={msg.body}")
                content = json.loads(msg.body)
                action = content.get("action")
                
                if not action:
                    logger.warning(f"Mensagem recebida sem 'action': {msg.body}")
                    logger.info(f"{'=' * 35} ENV {'=' * 35}")
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
                #logger.info(f"{'=' * 35} ENV {'=' * 35}")
            except json.JSONDecodeError:
                #logger.info(f"{'=' * 35} ENV {'=' * 35}")
                logger.exception(f"Erro ao descodificar JSON: {msg.body}")
                #logger.info(f"{'=' * 35} ENV {'=' * 35}")
            except Exception as e:
                #logger.info(f"{'=' * 35} ENV {'=' * 35}")
                logger.exception(f"Erro ao processar mensagem: {e}")
                #logger.info(f"{'=' * 35} ENV {'=' * 35}")
        else:
            # Sem mensagem, espera um pouco antes do próximo ciclo
            await asyncio.sleep(0.1)

    async def handle_dynamic_event(self, msg, content, action):
        """
        Processa comandos de eventos dinâmicos controlados por humanos.
        
        Trata os seguintes eventos:
        - apply_rain: Aplica chuva com intensidade especificada
        - stop_rain: Para a chuva
        - toggle_drought: Alterna o estado de seca
        - apply_pest: Ativa pragas numa célula aleatória
        - remove_pest: Remove todas as pragas
        - view_environment: Visualiza o estado atual do ambiente
        
        Args:
            msg (Message): Mensagem SPADE recebida.
            content (dict): Conteúdo da mensagem parseado como dicionário.
            action (str): Tipo de ação a ser executada.
            
        Note:
            Envia sempre uma resposta ao remetente com o status da operação.
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
        #logger.info(f"{'=' * 35} ENV {'=' * 35}")
        await self.send(reply)


    async def handle_agent_request(self, msg, content, action):
        """
        Processa pedidos de perceção e atuação dos agentes autónomos.
        
        Pedidos de perceção (REQUEST):
        - get_soil: Retorna temperatura, nutrientes e humidade
        - get_drone: Retorna estágio da cultura, tipo e nível de pragas
        
        Ações de atuação (ACT):
        - apply_irrigation: Aplica irrigação com taxa de fluxo especificada
        - apply_fertilize: Aplica fertilizante
        - apply_pesticide: Aplica pesticida
        - plant_seed: Planta uma semente do tipo especificado
        - harvest: Realiza colheita e retorna o rendimento
        
        Args:
            msg (Message): Mensagem SPADE recebida.
            content (dict): Conteúdo da mensagem parseado como dicionário.
            action (str): Tipo de ação a ser executada.
            
        Raises:
            ValueError: Se parâmetros obrigatórios estiverem ausentes.
            Exception: Para erros durante a execução da ação.
            
        Note:
            Todas as respostas incluem o status da operação e dados relevantes.
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
        #logger.info(f"{'=' * 35} ENV {'=' * 35}")
        await self.send(reply)

# --- Agente ---

class FarmEnvironmentAgent(Agent):
    """
    Agente SPADE que encapsula e gere o ambiente agrícola.
    
    Este agente é responsável por:
    - Avançar o tempo da simulação através de ticks periódicos
    - Processar eventos dinâmicos (chuva, seca, pragas)
    - Responder a pedidos de perceção de agentes
    - Executar ações de atuação solicitadas por agentes
    
    Attributes:
        field (Field): Instância do ambiente agrícola gerido.
        ticker_period (float): Período em segundos entre cada tick de simulação.
        numb_ticks (int): Contador de ticks executados.
    """

    def __init__(self, jid, password, Field, verify_security=False):
        """
        Inicializa o FarmEnvironmentAgent.
        
        Args:
            jid (str): Jabber ID do agente.
            password (str): Palavra-passe para autenticação XMPP.
            Field (Field): Instância do ambiente agrícola a ser gerido.
            verify_security (bool, optional): Se deve verificar certificados SSL.
                Defaults to False.
        """
                
        super().__init__(jid, password, verify_security=verify_security)
        self.field = Field
        self.ticker_period = 10 # 10 segundos por "tick" de simulação (pode ser ajustado)
        self.numb_ticks = 0

        self.numb_to_string = {
            0: "Tomate",
            1: "Pimento",
            2: "Trigo",
            3: "Couve",
            4: "Alface",
            5: "Cenoura"
        }

    async def setup(self):
        """
        Configura e inicia o agente de ambiente.
        
        Este método:
        1. Adiciona o comportamento EnvironmentTicker para simular passagem do tempo
        2. Adiciona múltiplas instâncias de EnvironmentManager com templates
           diferentes para processar eventos dinâmicos, pedidos de perceção
           e ações de atuação
        
        Note:
            São criados três templates distintos para diferenciar os tipos de
            mensagens recebidas (eventos dinâmicos, dados da quinta e ações).
        """
        
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

    
    async def stop(self):
        logger.info(f"{'=' * 35} ENV {'=' * 35}")
        logger.info("Morreram as seguintes quantidades de plantas:")
        for seed, amount in self.field.crop.dead_crop.items():
            logger.info(f"{self.numb_to_string[seed]}: {amount}")
        logger.info(f"{'=' * 35} ENV {'=' * 35}")
        await super().stop()