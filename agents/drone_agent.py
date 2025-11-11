from spade.agent import Agent
from spade.behaviour import PeriodicBehaviour, OneShotBehaviour,CyclicBehaviour
from spade.template import Template
import time
import asyncio
import json
import logging
import numpy as np

from agents.message import make_message

# Constantes de Limite
BATTERY_LOW_THRESHOLD = 20.0
PESTICIDE_LOW_THRESHOLD = 3.0
ONTOLOGY_FARM_DATA = "farm_data"
ONTOLOGY_FARM_ACTION = "farm_action"

# =====================
#   BEHAVIOURS
# =====================


class DoneFailure(CyclicBehaviour):
    """Comportamento que lida com o sucesso ou falha de recargas."""

    def __init__(self, timeout_wait):
        super().__init__()
        self.timeout_wait = timeout_wait

    async def run(self):
        # Aceder ao logger do agente para consistência
        self.agent.logger.info(f"[DRO][DoneFailure] Esperando por resposta de carregamento...")
        msg = await self.receive(timeout=self.timeout_wait)

        if not msg: 
            return

        content = json.loads(msg.body)
        details = content.get("details", {}) 
        if msg.get_metadata("performative") == "Done":
            if details.get("resource_type") == "battery":
                self.agent.energy = self.agent.energy + details.get("amount_delivered")
                self.agent.logger.info("[DRO] Recarga de bateria concluída com sucesso.")
            elif details.get("resource_type") == "pesticide":
                self.agent.pesticide_amount = self.agent.pesticide_amount + details.get("amount_delivered")
                self.agent.logger.info("[DRO] Reabastecimento de pesticida concluído com sucesso.")
            self.agent.status = "idle"
        elif msg.get_metadata("performative") == "Failure":
            self.agent.logger.error(f"[DRO] Falha na tarefa de {details.get('resource_type', 'desconhecido')}: {content.get('message', 'Sem detalhes')}")
            self.agent.status = "idle"
        else:
            self.agent.logger.warning(f"[DRO][DoneFailure] Recebida performativa inesperada: {msg.metadata.get('performative')}")


class CFPBehaviour(OneShotBehaviour):
    """Comportamento que envia um CFP e espera propostas."""

    def __init__(self, timeout_wait, task_type, required_resources, priority,position):
        super().__init__()
        self.timeout_wait = timeout_wait
        self.task_type = task_type
        self.required_resources = required_resources
        self.priority = priority
        self.task_id = f"cfp_{time.time()}"
        self.position = position

    async def run(self):
        self.agent.logger.info(f"[DRO][CFP] Enviando CFP {self.task_id} para {self.task_type}")
        for to_jid in self.agent.logistics_jid:
            body = {
                "sender_id": str(self.agent.jid),
                "receiver_id": to_jid,
                "cfp_id": self.task_id,
                "task_type": self.task_type,  # battery | pesticides
                "required_resources": self.required_resources,
                "position": self.position,  # Posição do drone para recarga/reabastecimento
                "priority": self.priority,
            }
            msg = make_message(to_jid, "cfp_recharge", body)
            await self.send(msg)
            self.agent.logger.info(f"[DRO] CFP_RECHARGE ({self.task_id}) enviado para {to_jid} a pedir {self.task_type} ({self.required_resources}).")
        # O agente deve esperar por propostas no seu CyclicBehaviour de receção
        # Este CFPBehaviour apenas envia o CFP e espera um tempo para que as propostas cheguem

        self.agent.awaiting_proposals.setdefault(self.task_id, [])

        # Espera o tempo de timeout para recolher propostas
        await asyncio.sleep(self.timeout_wait)

        proposals = self.agent.awaiting_proposals.pop(self.task_id, [])
        if not proposals:
            self.agent.logger.warning(f"[DRO][CFP] Nenhuma proposta recebida ({self.task_id}).")
            self.agent.status = "idle"
            return

        # Ordena por ETA
        proposals_sorted = sorted(proposals, key=lambda sp: sp[1].get("eta_ticks", float("inf")))
        chosen_sender, chosen_prop = proposals_sorted[0]
        self.agent.logger.info(f"[DRO][CFP] Escolhido: {chosen_sender} -> {chosen_prop}")

        # Envia accept/reject
        for sender, prop in proposals:
            if str(sender) == str(chosen_sender):
                acc_msg = make_message(
                    to=str(sender),
                    performative="accept-proposal",
                    body_dict={
                        "sender_id": str(self.agent.jid),
                        "receiver_id": str(sender),
                        "cfp_id": prop.get("cfp_id"),
                        "decision": "accept",
                    },)
                await self.send(acc_msg)
            else:
                rej_msg = make_message(
                    to=str(sender),
                    performative="reject-proposal",
                    body_dict={
                        "sender_id": str(self.agent.jid),
                        "receiver_id": str(sender),
                        "cfp_id": prop.get("cfp_id"),
                        "decision": "reject",
                    },
                )
                await self.send(rej_msg)

class ReceiveProposalsBehaviour(CyclicBehaviour):
    """Comportamento para receber propostas (propose) em resposta a um CFP."""
    
    async def run(self):

        msg = await self.receive(timeout=2) # Espera 2 segundos
        if msg:
            try:
                content = json.loads(msg.body)
                cfp_id = content.get("cfp_id")
                
                if cfp_id in self.agent.awaiting_proposals:
                    # Armazena a proposta (sender, content)
                    self.agent.awaiting_proposals[cfp_id].append((msg.sender, content))
                    self.agent.logger.info(f"[DRO][RecProposals] Proposta recebida de {msg.sender} para CFP {cfp_id}.")
                else:
                    self.agent.logger.warning(f"[DRO][RecProposals] Proposta recebida para CFP desconhecido: {cfp_id}")
            except json.JSONDecodeError:
                self.agent.logger.error(f"[DRO][RecProposals] Erro ao descodificar JSON da proposta: {msg.body}")
        
        # Não é necessário um sleep, pois o CyclicBehaviour já tem um mecanismo de espera/sleep interno

class PatrolBehaviour(PeriodicBehaviour):
    """Comportamento de patrulha periódica."""

    # =====================
    #   FUNÇÕES AUXILIARES DE COMUNICAÇÃO (MOVIDAS DO AGENT)
    # =====================
    async def _get_drone_data(self, row, col):
        """Solicita dados de observação (drone) ao Environment Agent."""
        body = {
            "action": "get_drone",
            "row": row,
            "col": col,
        }
        
        # Cria a mensagem de REQUEST
        msg = make_message(
            to=self.agent.environment_jid,
            performative="request",
            body_dict=body,
        )
        
        msg.set_metadata("ontology", ONTOLOGY_FARM_DATA)
        msg.set_metadata("performative", "request")
        self.agent.logger.info(f"[DRO] Solicitando dados de drone para ({row},{col}) ao Environment Agent.")
        
        # Envia a mensagem e espera pela resposta (inform)
        await self.send(msg)
        
        # Espera pela resposta com timeout
        reply = await self.receive(timeout=5)
        if reply:
            try:
                content = json.loads(reply.body)
                if content.get("status") == "success" and content.get("action") == "get_drone":
                    data = content.get("data")
                    self.agent.logger.info(f"[DRO] Dados de drone recebidos para ({row},{col}): {data}")
                    # Retorna (crop_stage, crop_type, pest_level)
                    return (data.get("crop_stage"), data.get("crop_type"), data.get("pest_level"))
                else:
                    self.agent.logger.error(f"[DRO] Resposta de erro do Environment Agent: {content.get('message')}")
                    return None, None, None
            except json.JSONDecodeError:
                self.agent.logger.error(f"[DRO] Erro ao descodificar JSON da resposta: {reply.body}")
                return None, None, None
        else:
            self.agent.logger.error("[DRO] Timeout ao esperar por resposta do Environment Agent.")
            return None, None, None

    async def _inform_crop(self, row, col, state,crop_type):
        """Envia uma mensagem inform_crop ao Logistics."""
        body = {
            "sender_id": str(self.agent.jid),
            "receiver_id": self.agent.logistics_jid[0],
            "inform_id": f"inform_crop_{time.time()}",
            "zone": [row, col],
            "crop_type": crop_type,
            "state": state,  # "0 -> not planted" ou "1 -> Ready for harvesting"
            "checked_at": time.time(),
        }
        msg = make_message(self.agent.logistics_jid[0], "inform_crop", body)
        await self.send(msg)
        self.agent.logger.info(f"[DRO] Mensagem enviada para {self.agent.logistics_jid[0]} (inform_crop).")

    async def _apply_pesticide(self, row, col):
        """Envia uma mensagem 'act' ao Environment Agent para aplicar pesticida."""
        if self.agent.pesticide_amount < 0.5:
            self.agent.logger.warning("[DRO] Pesticida insuficiente para aplicação.")
            return False

        body = {
            "action": "apply_pesticide",
            "row": row,
            "col": col,
        }

        # Cria a mensagem de ACT
        msg = make_message(
            to=self.agent.environment_jid,
            performative="act",
            body_dict=body,
        )
        msg.set_metadata("ontology", ONTOLOGY_FARM_ACTION)

        self.agent.logger.info(f"[DRO] Solicitando aplicação de pesticida em ({row},{col}) ao Environment Agent.")

        # Envia a mensagem e espera pela resposta (inform)
        await self.send(msg)

        # Espera pela resposta com timeout
        reply = await self.receive( timeout=5)
        if reply:
            try:
                content = json.loads(reply.body)
                if content.get("status") == "success" and content.get("action") == "apply_pesticide":
                    # Se a aplicação for bem-sucedida no ambiente, gasta os recursos do drone
                    self.agent.pesticide_amount -= 0.5
                    self.agent.energy -= np.random.uniform(1, 3)  # Gasto de energia
                    self.agent.logger.info(
                        f"[DRO] Pesticida aplicado em ({row},{col}) com sucesso. Restante: {self.agent.pesticide_amount:.2f} kg. Energia: {self.agent.energy:.2f}%"
                    )
                    return True
                else:
                    self.agent.logger.error(f"[DRO] Resposta de erro do Environment Agent ao aplicar pesticida: {content.get('message')}")
                    return False
            except json.JSONDecodeError:
                self.agent.logger.error(f"[DRO] Erro ao descodificar JSON da resposta: {reply.body}")
                return False
        else:
            self.agent.logger.error("[DRO] Timeout ao esperar por resposta do Environment Agent para aplicação de pesticida.")
            return False

    async def run(self):
        # 1. Verificar recursos
        if self.agent.status == "charging":
            # Se já estiver a carregar, não faz mais nada
            return

        if self.agent.energy < BATTERY_LOW_THRESHOLD:
            self.agent.logger.warning(f"Bateria baixa ({self.agent.energy:.2f}%). Solicitando recarga.")
            self.agent.status = "charging"

            # Adiciona o comportamento CFP para solicitar recarga
            self.agent.add_behaviour(
                CFPBehaviour(
                    timeout_wait=3,
                    task_type="battery",
                    required_resources=100.0 - self.agent.energy,
                    priority="High",
                    position=self.agent.position
                )
            )
            return

        if self.agent.pesticide_amount < PESTICIDE_LOW_THRESHOLD:
                    
            self.agent.status = "charging"
            self.agent.logger.warning(f"Pesticida baixo ({self.agent.pesticide_amount:.2f} kg). Solicitando reabastecimento.")
            # Adiciona o comportamento CFP para solicitar reabastecimento
            self.agent.add_behaviour(
                CFPBehaviour(
                    timeout_wait=2,
                    task_type="pesticide",
                    required_resources=self.agent.max_pesticide_amount - self.agent.pesticide_amount,
                    priority="High",
                    position=self.agent.position
                )
            )

            return

        # 2. Patrulhar
        self.agent.status = "flying"
        
        # Simula o movimento
        current_zone_index = self.agent.zones.index(self.agent.position)
        next_zone_index = (current_zone_index + 1) % len(self.agent.zones)
        next_zone = self.agent.zones[next_zone_index]
        
        self.agent.position = next_zone
        self.agent.energy -= np.random.uniform(0.1, 1)  # Gasto de energia por movimento
        
        row, col = self.agent.position
        self.agent.logger.info(f"Patrulhando zona ({row},{col}). Energia: {self.agent.energy:.2f}%. {self.agent.pesticide_amount:.2f} kg de pesticida restante.")

        # 3. Obter dados da cultura
        try:
            # A chamada foi corrigida para usar o método do Behaviour
            crop_stage, crop_type, pest_level = await self._get_drone_data(row, col)
        except Exception as e:
            self.agent.logger.error(f"Erro ao obter dados da cultura: {e}")
            return

        # 4. Analisar dados e agir
        if pest_level and pest_level == 1.0:
            self.agent.logger.warning(f"Alto nível de pragas ({pest_level:.2f}) em ({row},{col}). Aplicando pesticida.")
            # A chamada foi corrigida para usar o método do Behaviour
            self.agent.status = "handling_task"
            await self._apply_pesticide(row, col)
        
        if crop_stage == 4:
            self.agent.logger.info(f"Cultura madura em ({row},{col}). Informando Logistics.")
            # A chamada foi corrigida para usar o método do Behaviour
            await self._inform_crop(row, col, 4, crop_type)
        
        if crop_stage == 0:
            self.agent.logger.info(f"Zona ({row},{col}) não plantada. Informando Logistics.")
            # A chamada foi corrigida para usar o método do Behaviour
            await self._inform_crop(row, col, 0, None)

        self.agent.status = "idle"
        
        # 5. Log de recursos
        self.agent.logger.info(
            f"Recursos: Energia={self.agent.energy:.2f}%, Pesticida={self.agent.pesticide_amount:.2f}."
        )



class DroneAgent(Agent):
    def __init__(self, jid, password, zones, row, col,env_jid, log_jid):
        super().__init__(jid, password)
        logger = logging.getLogger(f"[DRO] {jid}")
        logger.setLevel(logging.INFO)
        self.logger = logger

        self.energy = 100  # Percentagem de bateria
        self.position = (row, col)
        self.zones = zones  # Lista de tuplos (row, col) que o drone patrulha
        self.status = "idle"  # flying, charging, handling_task
        self.pesticide_amount = 0.0  # Quantidade inicial de pesticida em KG
        self.max_pesticide_amount = 10.0
        self.environment_jid = env_jid  # JID do agente Environment
        self.logistics_jid = log_jid  # JID do agente Logistics

        # Estrutura para armazenar propostas recebidas (por cfp_id)
        self.awaiting_proposals = {}

        self.waiting_informs = {}

    # =====================
    #   SETUP
    # =====================
    async def setup(self):
        self.logger.info(f"DroneAgent {self.jid} iniciado. Posição: {self.position}")

        # Adiciona comportamentos principais
        patrol_b = PatrolBehaviour(period=5)  # patrulha a cada 5 ticks
        self.add_behaviour(patrol_b)

        # 2. Comportamento de Receção de Propostas (CFP)
        # Este comportamento é necessário para recolher as propostas enviadas pelo Logistics 
        # Cria um template para filtrar mensagens de "propose"
        template = Template()
        template.set_metadata("performative", "propose_recharge")
        receive_proposals_b = ReceiveProposalsBehaviour()
        self.add_behaviour(receive_proposals_b,template=template)

        template_done = Template()
        template_done.set_metadata("performative", "Done")

        template_fail = Template()
        template_fail.set_metadata("performative", "Failure")

        # Adiciona o comportamento DoneFailure para esperar pelo resultado

        self.add_behaviour(DoneFailure(timeout_wait=5), template=template_done)
        self.add_behaviour(DoneFailure(timeout_wait=5), template=template_fail)

        # O DoneFailure e o CFPBehaviour são adicionados dinamicamente pelo PatrolBehaviour
        # quando é necessário solicitar uma recarga/reabastecimento.