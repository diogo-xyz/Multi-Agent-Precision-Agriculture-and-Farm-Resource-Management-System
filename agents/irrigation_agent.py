from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message as SpadeMessage
from spade.template import Template
import json
import time
import logging

# Configuração básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# JIDs dos agentes
LOGISTICS_JID = "logistics@localhost"
FIELD_CONTROLLER_JID = "fieldcontroller@localhost"  # Agente que faz ligação com o ambiente aquele que aidna tinhas-se por fazer

# Constantes de Limite
BATTERY_LOW_THRESHOLD = 20.0
WATER_LOW_THRESHOLD = 50.0  # Litros

class IrrigationAgent(Agent):
    def __init__(self, jid, password, field_ref=None):
        super().__init__(jid, password)
        self.battery = 100.0  # Percentagem de bateria
        self.water = 500.0  # Litros de água disponíveis
        self.max_water = 500.0
        self.position = (0, 0)  # Posição base
        self.status = "idle"  # idle | busy | charging | refilling
        self.field = field_ref  # Referência ao objeto Field (para simulação)
        self.pending_recharges = {}  # {cfp_id: (resource_type, amount)}
        self.pending_tasks = {}  # {cfp_id: (zone, water_amount)}

    async def setup(self):
        logger.info(f"IrrigationAgent {self.jid.localpart} iniciado. Posição: {self.position}")
        logger.info(f"Inventário inicial - Bateria: {self.battery}%, Água: {self.water}L")

        # 1. Comportamento para receber pedidos de irrigação (CFP-Task)
        template_task = Template()
        template_task.set_metadata("performative", "cfp_task")
        self.add_behaviour(self.TaskRequestBehaviour(), template_task)

        # 2. Comportamento para receber propostas de reabastecimento (Propose-Recharge)
        template_propose = Template()
        template_propose.set_metadata("performative", "propose_recharge")
        self.add_behaviour(self.ProposeRechargeBehaviour(), template_propose)

        # 3. Comportamento para receber confirmação de reabastecimento (Done/Failure)
        template_done = Template()
        template_done.set_metadata("performative", "Done")
        self.add_behaviour(self.RechargeConfirmationBehaviour(), template_done)

        template_failure = Template()
        template_failure.set_metadata("performative", "failure")
        self.add_behaviour(self.RechargeFailureBehaviour(), template_failure)

    def _send_message(self, receiver_jid, performative, body):
        """Função auxiliar para enviar mensagens Spade."""
        msg = SpadeMessage(to=receiver_jid, body=json.dumps(body), metadata={"performative": performative})
        self.send(msg)
        logger.info(f"Mensagem enviada para {receiver_jid} com performative: {performative}")

    def _check_resources(self, water_needed):
        """Verifica se há recursos suficientes para realizar a tarefa."""
        # Calcula bateria necessária (assume 1% por litro de água + 5% para movimento)
        battery_needed = (water_needed * 0.1) + 5.0
        
        if self.battery < battery_needed:
            logger.warning(f"Bateria insuficiente. Atual: {self.battery}%, Necessário: {battery_needed}%")
            return False, "battery"
        
        if self.water < water_needed:
            logger.warning(f"Água insuficiente. Atual: {self.water}L, Necessário: {water_needed}L")
            return False, "water"
        
        return True, None

    def _request_recharge(self, resource_type, amount):
        """Solicita reabastecimento ao Logistics Agent."""
        cfp_id = f"cfp_recharge_{time.time()}"
        
        priority = "Urgent" if resource_type == "battery" and self.battery < 10 else "High"
        
        body = {
            "sender_id": str(self.jid),
            "receiver_id": LOGISTICS_JID,
            "cfp_id": cfp_id,
            "task_type": resource_type,
            "required_resources": amount,
            "priority": priority
        }
        
        self._send_message(LOGISTICS_JID, "cfp_recharge", body)
        self.pending_recharges[cfp_id] = (resource_type, amount)
        self.status = "waiting_recharge"
        logger.info(f"Solicitado reabastecimento de {resource_type}: {amount}")

    def _execute_irrigation(self, zone, water_amount):
        """Executa a irrigação na zona especificada."""
        row, col = zone #ainda por confirmar se é assim
        
        # Gasta bateria para movimento
        self.battery -= 5.0
        self.position = (row, col)
        logger.info(f"Movido para zona ({row},{col}). Bateria: {self.battery}%")
        
        # Gasta água e bateria para irrigação
        self.water -= water_amount
        self.battery -= water_amount * 0.1
        
        logger.info(f"Irrigação executada em ({row},{col}) com {water_amount}L de água.")
        logger.info(f"Recursos restantes - Bateria: {self.battery}%, Água: {self.water}L")
        
        # Comunica ao Field Controller para atualizar o ambiente
        field_body = {
            "sender_id": str(self.jid),
            "receiver_id": FIELD_CONTROLLER_JID,
            "action": "irrigate",
            "zone": list(zone),
            "water_amount": water_amount,
            "timestamp": time.time()
        }
        self._send_message(FIELD_CONTROLLER_JID, "inform", field_body)
        
        return True

    class TaskRequestBehaviour(CyclicBehaviour):
        """Lida com pedidos de irrigação (CFP-Task) do Soil Sensor."""
        async def run(self):
            msg = await self.receive(timeout=1)
            if msg:
                try:
                    content = json.loads(msg.body)
                    sender_jid = str(msg.sender)
                    performative = msg.get_metadata("performative")
                    
                    if performative == "cfp_task":
                        cfp_id = content.get("cfp_id")
                        task_type = content.get("task_type")
                        zone = tuple(content.get("zone"))
                        required_resources = content.get("required_resources", [])
                        priority = content.get("priority", "Medium")
                        
                        # Filtra apenas tarefas de irrigação
                        if task_type != "irrigation_application":
                            logger.info(f"Tarefa {task_type} não é de irrigação. Ignorado.")
                            return
                        
                        logger.info(f"Recebido pedido de irrigação de {sender_jid} para zona {zone}")
                        
                        # Extrai a quantidade de água necessária
                        water_needed = 0
                        for resource in required_resources:
                            if resource.get("type") == "water":
                                water_needed = resource.get("amount", 0)
                                break
                        
                        if water_needed == 0:
                            logger.warning(f"Quantidade de água não especificada no CFP {cfp_id}")
                            return
                        
                        # Verifica recursos disponíveis
                        has_resources, missing_resource = self.agent._check_resources(water_needed)
                        
                        if not has_resources:
                            # Solicita reabastecimento
                            logger.info(f"Recursos insuficientes. Solicitando {missing_resource}")
                            
                            if missing_resource == "battery":
                                amount_needed = 100 - self.agent.battery
                                self.agent._request_recharge("battery", amount_needed)
                            elif missing_resource == "water":
                                amount_needed = self.agent.max_water - self.agent.water
                                self.agent._request_recharge("water", amount_needed)
                            
                            # Adiciona tarefa à lista de pendentes
                            self.agent.pending_tasks[cfp_id] = (zone, water_needed, sender_jid)
                            return
                        
                        # Recursos suficientes, envia proposta
                        battery_cost = (water_needed * 0.1) + 5.0
                        eta_ticks = 3  # Tempo estimado
                        
                        propose_body = {
                            "sender_id": str(self.agent.jid),
                            "receiver_id": sender_jid,
                            "cfp_id": cfp_id,
                            "eta_ticks": eta_ticks,
                            "battery_lost": battery_cost,
                            "available_resources": [{"type": "water", "amount": water_needed}]
                        }
                        
                        self.agent._send_message(sender_jid, "propose_task", propose_body)
                        self.agent.pending_tasks[cfp_id] = (zone, water_needed, sender_jid)
                        logger.info(f"Proposta enviada para tarefa {cfp_id}")
                        
                except json.JSONDecodeError:
                    logger.error(f"Erro ao decodificar JSON da mensagem de {msg.sender}")
                except Exception as e:
                    logger.error(f"Erro ao processar CFP-Task: {e}")

    class ProposeRechargeBehaviour(CyclicBehaviour):
        """Lida com propostas de reabastecimento (Propose-Recharge) do Logistics."""
        async def run(self):
            msg = await self.receive(timeout=1)
            if msg:
                try:
                    content = json.loads(msg.body)
                    sender_jid = str(msg.sender)
                    cfp_id = content.get("cfp_id")
                    
                    if cfp_id in self.agent.pending_recharges:
                        eta_ticks = content.get("eta_ticks")
                        resources = content.get("resources")
                        
                        logger.info(f"Recebida proposta de reabastecimento. ETA: {eta_ticks} ticks")
                        
                        # Aceita a proposta automaticamente
                        accept_body = {
                            "sender_id": str(self.agent.jid),
                            "receiver_id": sender_jid,
                            "cfp_id": cfp_id,
                            "decision": "accept"
                        }
                        
                        self.agent._send_message(sender_jid, "accept-proposal", accept_body)
                        logger.info(f"Proposta de reabastecimento aceite para CFP {cfp_id}")
                        
                except json.JSONDecodeError:
                    logger.error(f"Erro ao decodificar JSON da mensagem de {msg.sender}")
                except Exception as e:
                    logger.error(f"Erro ao processar Propose-Recharge: {e}")

    class RechargeConfirmationBehaviour(CyclicBehaviour):
        """Lida com confirmação de reabastecimento (Done) do Logistics."""
        async def run(self):
            msg = await self.receive(timeout=1)
            if msg:
                try:
                    content = json.loads(msg.body)
                    cfp_id = content.get("cfp_id")
                    
                    if cfp_id in self.agent.pending_recharges:
                        resource_type, amount = self.agent.pending_recharges.pop(cfp_id)
                        
                        # Atualiza os recursos
                        if resource_type == "battery":
                            self.agent.battery = min(100.0, self.agent.battery + amount)
                            logger.info(f"Bateria recarregada. Nível atual: {self.agent.battery}%")
                        elif resource_type == "water":
                            self.agent.water = min(self.agent.max_water, self.agent.water + amount)
                            logger.info(f"Água reabastecida. Quantidade atual: {self.agent.water}L")
                        
                        self.agent.status = "idle"
                        
                        # Verifica se há tarefas pendentes que agora podem ser executadas
                        await self._check_pending_tasks()
                        
                except json.JSONDecodeError:
                    logger.error(f"Erro ao decodificar JSON da mensagem de {msg.sender}")
                except Exception as e:
                    logger.error(f"Erro ao processar Done: {e}")

        async def _check_pending_tasks(self):
            """Verifica e executa tarefas pendentes após reabastecimento."""
            for cfp_id, task_data in list(self.agent.pending_tasks.items()):
                zone, water_needed, requester_jid = task_data
                
                has_resources, _ = self.agent._check_resources(water_needed)
                
                if has_resources:
                    # Executa a tarefa
                    self.agent.status = "busy"
                    success = self.agent._execute_irrigation(zone, water_needed)
                    
                    if success:
                        # Envia Done ao solicitante
                        done_body = {
                            "sender_id": str(self.agent.jid),
                            "receiver_id": requester_jid,
                            "cfp_id": cfp_id,
                            "status": "done",
                            "details": {
                                "water_used": water_needed,
                                "zone": list(zone),
                                "battery_remaining": self.agent.battery
                            }
                        }
                        self.agent._send_message(requester_jid, "Done", done_body)
                        self.agent.pending_tasks.pop(cfp_id)
                        logger.info(f"Tarefa {cfp_id} concluída e removida dos pendentes")
                    
                    self.agent.status = "idle"

    class RechargeFailureBehaviour(CyclicBehaviour):
        """Lida com falhas de reabastecimento (Failure) do Logistics."""
        async def run(self):
            msg = await self.receive(timeout=1)
            if msg:
                try:
                    content = json.loads(msg.body)
                    cfp_id = content.get("cfp_id")
                    
                    if cfp_id in self.agent.pending_recharges:
                        resource_type, amount = self.agent.pending_recharges.pop(cfp_id)
                        logger.error(f"Falha no reabastecimento de {resource_type}. Tentando novamente...")
                        
                        # Tenta solicitar novamente após um tempo
                        self.agent._request_recharge(resource_type, amount)
                        
                except json.JSONDecodeError:
                    logger.error(f"Erro ao decodificar JSON da mensagem de {msg.sender}")
                except Exception as e:
                    logger.error(f"Erro ao processar Failure: {e}")