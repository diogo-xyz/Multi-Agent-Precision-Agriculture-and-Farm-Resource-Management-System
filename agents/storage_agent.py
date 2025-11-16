import json
import logging
import time


from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.template import Template
from agents.message import make_message

PERFORMATIVE_INFORM_RECEIVED = "inform_received"
PERFORMATIVE_INFORM_HARVEST = "inform_harvest"
class InformHarvestReceiver(CyclicBehaviour):
    """Comportamento cíclico que recebe colheitas e atualiza o armazenamento.
    
    Este behaviour aguarda mensagens do tipo INFORM_HARVEST enviadas por
    Harvester Agents, processa a informação de colheita recebida, atualiza
    o armazenamento de sementes e envia uma confirmação de receção.
    """
    async def run(self):
        """Executa o ciclo de receção e processamento de mensagens de colheita.
        
        Aguarda mensagens com informação sobre colheitas, extrai os dados de
        quantidade e tipo de semente, atualiza o yield_storage do agente e
        envia uma mensagem de confirmação ao remetente.
        
        A mensagem esperada deve conter:
            - amount_type (list): Lista de dicionários com 'seed_type' e 'amount'
        
        Raises:
            json.JSONDecodeError: Se o corpo da mensagem não for JSON válido.
            Exception: Para outros erros durante o processamento. """ 
        
        msg = await self.receive(timeout=5)
        if msg:
            try:
                content = json.loads(msg.body)
                amount_type_list = content.get("amount_type", [])
                sender_jid = str(msg.sender)
                
                self.agent.logger.info(f"[INFORM_HARVEST] Recebido colheita de {sender_jid}.")

                details_received = []
                for item in amount_type_list:
                    seed_type = item.get("seed_type")
                    amount = item.get("amount")
                    
                    if seed_type is not None and amount is not None:
                        self.agent.yield_storage[seed_type] += amount
                        
                        details_received.append({"seed_type": seed_type, "amount": amount})
                        self.agent.logger.info(f"[INFORM_HARVEST] Yield de semente {seed_type} atualizado. Adicionado: {amount}. Total: {self.agent.yield_storage[seed_type]}.")

                #print(self.agent.yield_storage)
                # Enviar confirmação `inform_received`
                if details_received:
                    msg = await self.agent.send_inform_received(sender_jid, details_received)
                    await self.send(msg)
                    self.agent.logger.info(f"[INFORM_HARVEST] Confirmação 'inform_received' enviada para {sender_jid}.")

            except json.JSONDecodeError:
                self.agent.logger.error(f"[INFORM_HARVEST] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[INFORM_HARVEST] Erro ao processar INFORM_HARVEST: {e}")


class StorageAgent(Agent):
    """Agente responsável pelo armazenamento de colheitas agrícolas.
    
    O StorageAgent recebe informações de colheita de outros agentes (Harvester),
    armazena as quantidades de diferentes tipos de sementes e mantém um registo
    total da produção durante a simulação.
    
    Attributes:
        logger (logging.Logger): Logger configurado para este agente.
        yield_storage (dict): Dicionário que mapeia tipos de sementes (int) para
            quantidades armazenadas (int). Tipos disponíveis:
                - 0: Tomate
                - 1: Pimento
                - 2: Trigo
                - 3: Couve
                - 4: Alface
                - 5: Cenoura
        numb_to_string (dict): Mapeamento de códigos numéricos para nomes de sementes.
    """
    def __init__(self, jid, password):
        """Inicializa o StorageAgent.
        
        Args:
            jid (str): Jabber ID do agente.
            password (str): Password para autenticação do agente.
        """
        super().__init__(jid, password)
        
        self.logger = logging.getLogger(f"[STO] {jid}")
        self.logger.setLevel(logging.INFO)

        self.yield_storage = {
            0: 0, # 0: Tomate
            1: 0, # 1: Pimento
            2: 0, # 2: Trigo
            3: 0, # 3: Couve
            4: 0, # 4: Alface
            5: 0  # 5: Cenoura
        }

        self.numb_to_string = {
            0: "Tomate",
            1: "Pimento",
            2: "Trigo",
            3: "Couve",
            4: "Alface",
            5: "Cenoura"
        }
    
    async def setup(self):
        """Configura o agente e inicia os seus comportamentos.
        
        Regista o behaviour InformHarvestReceiver com um template que filtra
        mensagens com performative PERFORMATIVE_INFORM_HARVEST.
        """
        self.logger.info("Storage started")

        template = Template()
        template.set_metadata("performative", PERFORMATIVE_INFORM_HARVEST)

        self.add_behaviour(InformHarvestReceiver(),template=template)

    async def stop(self):
        """Encerra o agente e apresenta um sumário da produção total.
        
        Apresenta no log um resumo de todas as quantidades de sementes
        armazenadas durante a simulação antes de parar o agente.
        """
        self.logger.info(f"{'=' * 35} STOR {'=' * 35}")
        self.logger.info(f"{self.jid} guardou em toda a simulação:")
        for seed, amount in self.yield_storage.items():
            self.logger.info(f"{self.numb_to_string[seed]}: {amount}")
        self.logger.info(f"{'=' * 35} STOR {'=' * 35}")
        await super().stop()

    
    async def send_inform_received(self, to, details):
        """Cria uma mensagem de confirmação de receção.
        
        Args:
            to (str): JID do destinatário da mensagem.
            details (list): Lista de dicionários com informação sobre as colheitas
                recebidas. Cada dicionário deve conter 'seed_type' e 'amount'.
        
        Returns:
            spade.message.Message: Mensagem configurada com performative
                PERFORMATIVE_INFORM_RECEIVED e corpo contendo o ID da confirmação
                e os detalhes da receção.
        """
        msg = make_message(
            to=to,
            performative=PERFORMATIVE_INFORM_RECEIVED,
            body_dict={
                "inform_id": f"inform_received_{time.time()}",
                "details": details
            }
        )
        return msg