from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message as SpadeMessage
from spade.template import Template
import json
import time
import logging
import random

# Configuração básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# JIDs dos agentes (assumindo um padrão)
# Estes JIDs devem ser ajustados para o ambiente de execução real (e.g., @dominio.com)
DRONE_JID = "drone@localhost"
IRRIGATION_JID = "irrigation@localhost"
FERTILIZER_JID = "fertilizer@localhost"
HARVESTER_JID = "harvester@localhost"
SOIL_SENSOR_JID = "soilsensor@localhost" # Adicionado para completar a lista

PLANT_TYPES = {
    0: "Tomate",
    1: "Pimento",
    2: "Trigo",
    3: "Couve",
    4: "Alface",
    5: "Cenoura"
}

class LogisticsAgent(Agent):
    def __init__(self, jid, password):
        super().__init__(jid, password)
        self.inventory = {
            "battery": 1000, # Capacidade total de recarga de bateria (simulada)
            "water": 5000,   # Litros (para Irrigation Agent)
            "fertilizer": 1000, # Kg (para Fertilizer Agent)
            "pesticides": 500, # Doses (para Drone Agent)
            "seeds": 1000,   # Gramas (para Harvester Agent)
            "fuel": 2000     # Litros (para Harvester Agent, se aplicável)
        }
        self.max_inventory = self.inventory.copy()
        self.status = "idle"
        self.recharge_rate = 100 # Taxa de recarga por tick (para simulação)
        self.pending_recharges = {} # {cfp_id: (sender_jid, resource_key, required_amount)}
        self.pending_tasks = {} # {cfp_id: (receiver_jid, task_type, zone)}

    async def setup(self):
        logger.info(f"LogisticsAgent {self.jid.localpart} iniciado. Inventário inicial: {self.inventory}")

        # 1. Comportamento para recarregar o inventário quando ocioso
        self.add_behaviour(self.InventoryRechargeBehaviour(period=5))

        # 2. Comportamento para receber pedidos de reabastecimento (CFP-Recharge)
        template_recharge = Template()
        template_recharge.set_metadata("performative", "cfp_recharge")
        self.add_behaviour(self.RechargeRequestBehaviour(), template_recharge)

        # 3. Comportamento para receber informações de colheita/plantação (Inform-Crop)
        template_inform_crop = Template()
        template_inform_crop.set_metadata("performative", "inform_crop")
        self.add_behaviour(self.CropInformBehaviour(), template_inform_crop)

        # 4. Comportamento para receber aceitação de proposta de recarga (Accept-Proposal)
        template_accept = Template()
        template_accept.set_metadata("performative", "accept-proposal")
        self.add_behaviour(self.AcceptProposalBehaviour(), template_accept)

        # 5. Comportamento para receber rejeição de proposta de recarga (Reject-Proposal)
        template_reject = Template()
        template_reject.set_metadata("performative", "reject-proposal")
        self.add_behaviour(self.RejectProposalBehaviour(), template_reject)

        # 6. Comportamento para receber respostas a tarefas (PROPOSE, DONE, FAILURE)
        # O Logistics envia CFP-TASK e espera PROPOSE, DONE, FAILURE do Harvester
        # Usamos um template mais genérico e filtramos internamente
        template_task_response = Template()
        # O Logistics só envia CFP-TASK para o Harvester, então esperamos respostas dele.
        # Se o Logistics enviasse CFP-TASK para outros agentes, o template teria de ser mais abrangente.
        self.add_behaviour(self.TaskResponseBehaviour(), template_task_response)


    def _send_message(self, receiver_jid, performative, body):
        """Função auxiliar para enviar mensagens Spade."""
        msg = SpadeMessage(to=receiver_jid, body=json.dumps(body), metadata={"performative": performative})
        self.send(msg)
        logger.info(f"Mensagem enviada para {receiver_jid} com performative: {performative}")

    def _recharge_resource(self, resource_type, amount):
        """Simula a dedução do recurso do inventário do Logistics após a aceitação da proposta."""
        if self.inventory.get(resource_type, 0) >= amount:
            self.inventory[resource_type] -= amount
            logger.info(f"Recurso {resource_type} de {amount} unidades deduzido do inventário. Restante: {self.inventory[resource_type]}")
            return True
        else:
            logger.warning(f"Recurso {resource_type} insuficiente no inventário do Logistics para dedução.")
            return False

    class InventoryRechargeBehaviour(CyclicBehaviour):
        """Recarrega o inventário do agente quando está ocioso."""
        async def run(self):
            # O agente recarrega o inventário se estiver ocioso (sem tarefas pendentes)
            is_busy = bool(self.agent.pending_recharges or self.agent.pending_tasks)
            
            if not is_busy:
                self.agent.status = "idle"
                recharged = False
                for resource, current_amount in self.agent.inventory.items():
                    max_amount = self.agent.max_inventory[resource]
                    if current_amount < max_amount:
                        recharge_amount = min(self.agent.recharge_rate, max_amount - current_amount)
                        self.agent.inventory[resource] += recharge_amount
                        recharged = True
                
                if recharged:
                    logger.info(f"Inventário recarregado. Estado atual: {self.agent.inventory}")
            else:
                self.agent.status = "busy"
            
            await self.sleep(self.period)

    class RechargeRequestBehaviour(CyclicBehaviour):
        """Lida com pedidos de reabastecimento (CFP-Recharge)."""
        async def run(self):
            # O timeout é importante para não bloquear o agente
            msg = await self.receive(timeout=1) 
            if msg:
                try:
                    content = json.loads(msg.body)
                    sender_jid = str(msg.sender)
                    performative = msg.get_metadata("performative")
                    
                    if performative == "cfp_recharge":
                        cfp_id = content.get("cfp_id")
                        task_type = content.get("task_type") # Ex: battery, water, pesticides
                        required_resources = content.get("required_resources")
                        priority = content.get("priority")

                        logger.info(f"Recebido CFP-Recharge de {sender_jid} para {task_type} ({required_resources}). Prioridade: {priority}")

                        # Mapear task_type para a chave de inventário
                        resource_map = {
                            "battery": "battery",
                            "water": "water",
                            "fertilizer": "fertilizer",
                            "pesticides": "pesticides",
                            "seeds": "seeds",
                            "fuel": "fuel"
                        }
                        resource_key = resource_map.get(task_type)

                        if resource_key and self.agent.inventory.get(resource_key, 0) >= required_resources:
                            # Recurso disponível, envia PROPOSE-RECHARGE
                            eta_ticks = 5 # Simulação de tempo de chegada
                            
                            propose_body = {
                                "sender_id": str(self.agent.jid),
                                "receiver_id": sender_jid,
                                "cfp_id": cfp_id,
                                "eta_ticks": eta_ticks,
                                "resources": required_resources,
                                "priority": priority
                            }
                            self.agent._send_message(sender_jid, "propose_recharge", propose_body)
                            
                            # Adiciona à lista de recargas pendentes
                            self.agent.pending_recharges[cfp_id] = (sender_jid, resource_key, required_resources)

                        else:
                            # Recurso indisponível, não responde. O agente solicitante deve re-enviar o CFP.
                            logger.warning(f"Recurso {task_type} indisponível ou insuficiente para {sender_jid}. Não foi enviada proposta.")

                except json.JSONDecodeError:
                    logger.error(f"Erro ao decodificar JSON da mensagem de {msg.sender}.")
                except Exception as e:
                    logger.error(f"Erro ao processar CFP-Recharge: {e}")

    class CropInformBehaviour(CyclicBehaviour):
        """Lida com informações de colheita/plantação (Inform-Crop) do Drone."""
        async def run(self):
            msg = await self.receive(timeout=1)
            if msg:
                try:
                    content = json.loads(msg.body)
                    sender_jid = str(msg.sender)
                    performative = msg.get_metadata("performative")

                    if performative == "inform_crop":
                        inform_id = content.get("inform_id")
                        zone = content.get("zone")
                        state = content.get("state") # "0" (plantar) ou "1" (colher)

                        logger.info(f"Recebido Inform-Crop de {sender_jid} para zona {zone}. Estado: {state}")

                        task_type = ""
                        required_resources = []
                        
                        if state == "0":
                            task_type = "plant_application"
                            # Simulação de recurso necessário: 50g de sementes
                            required_resources = [{"type":"seed", "amount": 50}]
                            # Selecionar aleatoriamente o tipo de planta
                            seed_type_id = random.choice(list(PLANT_TYPES.keys()))
                            logger.info(f"Coordenando plantação de {PLANT_TYPES[seed_type_id]} (ID: {seed_type_id}) na zona {zone}.")
                        elif state == "1":
                            task_type = "harvest_application"
                            # Simulação de recurso necessário: 100kg de espaço de armazenamento
                            required_resources = [{"type":"storage", "amount": 100}] 
                            logger.info(f"Coordenando colheita na zona {zone}.")
                        else:
                            logger.warning(f"Estado de cultura desconhecido: {state}")
                            return

                        # Enviar CFP-Task para o Harvester
                        cfp_task_id = f"cfp_task_{time.time()}"
                        cfp_task_body = {
                            "sender_id": str(self.agent.jid),
                            "receiver_id": HARVESTER_JID,
                            "cfp_id": cfp_task_id,
                            "task_type": task_type,
                            "seed_type": seed_type_id,
                            "zone": zone,
                            "required_resources": required_resources,
                            "priority": "High",
                        }
                        self.agent._send_message(HARVESTER_JID, "cfp_task", cfp_task_body)
                        
                        # Adiciona à lista de tarefas pendentes
                        self.agent.pending_tasks[cfp_task_id] = (HARVESTER_JID, task_type, zone)

                except json.JSONDecodeError:
                    logger.error(f"Erro ao decodificar JSON da mensagem de {msg.sender}.")
                except Exception as e:
                    logger.error(f"Erro ao processar Inform-Crop: {e}")

    class AcceptProposalBehaviour(CyclicBehaviour):
        """Lida com a aceitação de propostas (Accept-Proposal) após o Logistics ter enviado um PROPOSE-RECHARGE."""
        async def run(self):
            msg = await self.receive(timeout=1)
            if msg:
                try:
                    content = json.loads(msg.body)
                    sender_jid = str(msg.sender)
                    cfp_id = content.get("cfp_id")
                    
                    if cfp_id in self.agent.pending_recharges:
                        # Processar a recarga
                        sender_jid_original, resource_key, required_amount = self.agent.pending_recharges.pop(cfp_id)
                        
                        if self.agent._recharge_resource(resource_key, required_amount):
                            logger.info(f"Recarga de {resource_key} de {required_amount} para {sender_jid} ACEITE e processada.")
                            
                            # Enviar mensagem de Done para o agente solicitante
                            done_body = {
                                "sender_id": str(self.agent.jid),
                                "receiver_id": sender_jid,
                                "cfp_id": cfp_id,
                                "status": "done",
                                "details": {"resource_recharged": resource_key, "amount": required_amount}
                            }
                            self.agent._send_message(sender_jid, "Done", done_body)
                        else:
                            logger.error(f"Falha crítica: Recurso {resource_key} insuficiente no momento da aceitação para {sender_jid}.")
                            # Enviar mensagem de Failure
                            failure_body = {
                                "sender_id": str(self.agent.jid),
                                "receiver_id": sender_jid,
                                "cfp_id": cfp_id,
                                "status": "failure",
                            }
                            self.agent._send_message(sender_jid, "failure", failure_body)
                    else:
                        logger.warning(f"Recebido ACCEPT-PROPOSAL para CFP-ID desconhecido: {cfp_id} de {sender_jid}.")

                except json.JSONDecodeError:
                    logger.error(f"Erro ao decodificar JSON da mensagem de {msg.sender}.")
                except Exception as e:
                    logger.error(f"Erro ao processar Accept-Proposal: {e}")

    class RejectProposalBehaviour(CyclicBehaviour):
        """Lida com a rejeição de propostas (Reject-Proposal) após o Logistics ter enviado um PROPOSE-RECHARGE."""
        async def run(self):
            msg = await self.receive(timeout=1)
            if msg:
                try:
                    content = json.loads(msg.body)
                    sender_jid = str(msg.sender)
                    cfp_id = content.get("cfp_id")
                    
                    if cfp_id in self.agent.pending_recharges:
                        # Remove da lista de pendentes, o agente solicitante recusou a proposta
                        self.agent.pending_recharges.pop(cfp_id)
                        logger.info(f"Recarga para {sender_jid} REJEITADA. Removido dos pendentes.")
                    else:
                        logger.warning(f"Recebido REJECT-PROPOSAL para CFP-ID desconhecido: {cfp_id} de {sender_jid}.")

                except json.JSONDecodeError:
                    logger.error(f"Erro ao decodificar JSON da mensagem de {msg.sender}.")
                except Exception as e:
                    logger.error(f"Erro ao processar Reject-Proposal: {e}")

    class TaskResponseBehaviour(CyclicBehaviour):
        """Lida com as respostas (PROPOSE, DONE, FAILURE) do Harvester à CFP-Task enviada pelo Logistics."""
        async def run(self):
            # Este comportamento deve ser capaz de receber mensagens de qualquer agente
            # Mas o Logistics só envia CFP-TASK para o Harvester neste cenário.
            msg = await self.receive(timeout=1)
            if msg:
                try:
                    content = json.loads(msg.body)
                    sender_jid = str(msg.sender)
                    performative = msg.get_metadata("performative")
                    cfp_id = content.get("cfp_id")

                    if cfp_id not in self.agent.pending_tasks:
                        # Pode ser uma resposta a um CFP-TASK que não foi enviado pelo Logistics
                        # ou uma resposta a um CFP-RECHARGE que não foi filtrada pelos outros comportamentos
                        logger.warning(f"Recebido {performative} para CFP-ID de tarefa desconhecido: {cfp_id} de {sender_jid}.")
                        return

                    receiver_jid, task_type, zone = self.agent.pending_tasks[cfp_id]

                    if performative == "propose_task":
                        # O Harvester propôs a execução. O Logistics deve aceitar ou rejeitar.
                        # Para simplificar, o Logistics sempre aceita a primeira proposta.
                        
                        accept_body = {
                            "sender_id": str(self.agent.jid),
                            "receiver_id": sender_jid,
                            "cfp_id": cfp_id,
                            "decision": "accept",
                        }
                        self.agent._send_message(sender_jid, "accept-proposal", accept_body)
                        logger.info(f"Aceite proposta de tarefa {cfp_id} ({task_type} na zona {zone}) do Harvester.")

                    elif performative == "Done":
                        # Tarefa concluída pelo Harvester
                        self.agent.pending_tasks.pop(cfp_id)
                        logger.info(f"Tarefa {cfp_id} ({task_type} na zona {zone}) concluída pelo Harvester.")
                        # O Logistics pode agora atualizar o estado do campo ou registar a colheita/plantação

                    elif performative == "failure":
                        # Tarefa falhou
                        self.agent.pending_tasks.pop(cfp_id)
                        logger.error(f"Tarefa {cfp_id} ({task_type} na zona {zone}) falhou no Harvester.")
                        # O Logistics deve tentar encontrar outro agente ou reagendar

                except json.JSONDecodeError:
                    logger.error(f"Erro ao decodificar JSON da mensagem de {msg.sender}.")
                except Exception as e:
                    logger.error(f"Erro ao processar resposta de tarefa: {e}")

# Exemplo de uso (para teste local)
# if __name__ == "__main__":
#     import asyncio
#     from spade import quit_spade
#     
#     async def main():
#         # Certifique-se de que o servidor XMPP está a correr (e.g., com o docker-compose do SPADE)
#         logistics_agent = LogisticsAgent("logistics@localhost", "password")
#         await logistics_agent.start()
#         
#         print("Agente Logistics iniciado. Pressione Ctrl+C para parar.")
#         
#         # Simulação de um pedido de recarga (de um agente fictício)
#         # msg_recharge = SpadeMessage(to="logistics@localhost", body=json.dumps({"cfp_id": "test_recharge_1", "task_type": "battery", "required_resources": 50, "priority": "High"}), metadata={"performative": "cfp_recharge"})
#         # await logistics_agent.send(msg_recharge)
#         
#         # Simulação de um inform-crop (do drone)
#         # msg_crop = SpadeMessage(to="logistics@localhost", body=json.dumps({"inform_id": "test_crop_1", "zone": [2, 3], "state": "1"}), metadata={"performative": "inform_crop"})
#         # await logistics_agent.send(msg_crop)
#         
#         await asyncio.sleep(60)
#         await logistics_agent.stop()
#         quit_spade()
#         
#     if __name__ == "__main__":
#         asyncio.run(main())