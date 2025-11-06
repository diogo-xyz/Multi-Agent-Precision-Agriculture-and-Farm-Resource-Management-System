from spade.agent import Agent
from spade.template import Template
from spade.behaviour import PeriodicBehaviour, OneShotBehaviour, CyclicBehaviour
import spade
import time
import asyncio
import json
import logging

from message import make_message


ENV_JID = "environment@localhost"
LOG_JID = "logistics@localhost"

# Constantes de Limite
BATTERY_LOW_THRESHOLD = 20.0
PESTICIDE_LOW_THRESHOLD = 1.0

logger = logging.getLogger("DroneAgent")
logger.setLevel(logging.INFO)



class DroneAgent(Agent):
    def __init__(self, jid, password, zones, row, col):
        super().__init__(jid, password)
        self.logger = logger

        self.energy = 100.0
        self.row_initial = row
        self.col_initial = col
        self.position = (row, col)
        self.zones = zones  # Lista de tuplos (row, col) que o drone patrulha
        self.status = "idle"  # flying, charging, handling_task
        self.pesticide_amount = 10.0  # Quantidade inicial de pesticida em KG
        self.max_pesticide_amount = 10.0
        self.environment_jid = ENV_JID  # JID do agente Environment
        self.logistics_jid = LOG_JID  # JID do agente Logistics

        # Estrutura para armazenar propostas recebidas (por cfp_id)
        self.awaiting_proposals = {}

    # =====================
    #   SETUP
    # =====================
    async def setup(self):
        self.logger.info(f"DroneAgent {self.jid} iniciado. Posição: {self.position}")

        # Adiciona comportamentos principais
        patrol_b = self.PatrolBehaviour(period=5)  # patrulha a cada 10 ticks
        self.add_behaviour(patrol_b)

        # Comportamento receptor de propostas
        self.add_behaviour(self.ProposalReceiverBehaviour())

    # =====================
    #   BEHAVIOURS
    # =====================

    class ProposalReceiverBehaviour(CyclicBehaviour):
        """Recebe propostas dos agentes de logística."""

        async def run(self):
            msg = await self.receive(timeout=1)
            if msg:
                try:
                    # Tenta converter JSON -> dict, se necessário
                    body = msg.body
                    if isinstance(body, str):
                        body = json.loads(body)

                    cfp_id = body.get("cfp_id")
                    if not cfp_id:
                        return

                    proposal = body.get("proposal", body)
                    self.agent.awaiting_proposals.setdefault(cfp_id, []).append((str(msg.sender), proposal))
                    self.agent.logger.info(
                        f"[DRO][PROPOSAL] Recebida de {msg.sender} para {cfp_id}: {proposal}"
                    )
                except Exception as e:
                    self.agent.logger.error(f"[DRO][PROPOSAL] Erro ao processar proposta: {e}")

    class CFPBehaviour(OneShotBehaviour):
        """Comportamento que envia um CFP e espera propostas."""

        def __init__(self, timeout_wait, task_type, required_resources, priority):
            super().__init__()
            self.timeout_wait = timeout_wait
            self.task_type = task_type
            self.required_resources = required_resources
            self.priority = priority
            self.task_id = f"cfp_{time.time()}"

        async def run(self):
            self.agent.logger.info(f"[DRO][CFP] Enviando CFP {self.task_id} para {self.task_type}")

            body = {
                "sender_id": str(self.agent.jid),
                "receiver_id": self.agent.logistics_jid,
                "cfp_id": self.task_id,
                "task_type": self.task_type,  # battery | pesticides
                "required_resources": self.required_resources,
                "priority": self.priority,
            }
            msg = make_message(self.agent.logistics_jid, "cfp_recharge", body)
            await self.send(msg)

            self.agent.awaiting_proposals.setdefault(self.task_id, [])

            wait_until = time.time() + self.timeout_wait
            while time.time() < wait_until:
                await asyncio.sleep(0.5)

            proposals = self.agent.awaiting_proposals.pop(self.task_id, [])
            if not proposals:
                self.agent.logger.warning(f"[DRO][CFP] Nenhuma proposta recebida ({self.task_id}).")
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
                    self.agent.status = "idle" # O agente volta a idle para que o PatrolBehaviour possa continuar
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
                        protocol="fipa-contract-net",
                    )
                    await self.send(rej_msg)

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
            
            self.agent.logger.info(f"Solicitando dados de drone para ({row},{col}) ao Environment Agent.")
            
            # Envia a mensagem e espera pela resposta (inform)
            await self.send(msg)
            
            # Espera pela resposta com timeout
            reply = await self.receive(timeout=5)
            
            if reply:
                try:
                    content = json.loads(reply.body)
                    if content.get("status") == "success" and content.get("action") == "get_drone":
                        data = content.get("data")
                        self.agent.logger.info(f"Dados de drone recebidos para ({row},{col}): {data}")
                        # Retorna (crop_stage, crop_type, pest_level)
                        return (data.get("crop_stage"), data.get("crop_type"), data.get("pest_level"))
                    else:
                        self.agent.logger.error(f"Resposta de erro do Environment Agent: {content.get('message')}")
                        return None, None, None
                except json.JSONDecodeError:
                    self.agent.logger.error(f"Erro ao descodificar JSON da resposta: {reply.body}")
                    return None, None, None
            else:
                self.agent.logger.error("Timeout ao esperar por resposta do Environment Agent.")
                return None, None, None

        async def _inform_crop(self, row, col, state):
            """Envia uma mensagem inform_crop ao Logistics."""
            body = {
                "sender_id": str(self.agent.jid),
                "receiver_id": self.agent.logistics_jid,
                "inform_id": f"inform_crop_{time.time()}",
                "zone": [row, col],
                "state": state,  # "0 -> not planted" ou "1 -> Ready for harvesting"
                "checked_at": time.time(),
            }
            msg = make_message(self.agent.logistics_jid, "inform_crop", body)
            await self.send(msg)
            self.agent.logger.info(f"Mensagem enviada para {self.agent.logistics_jid} (inform_crop).")

        async def _apply_pesticide(self, row, col):
            """Envia uma mensagem 'act' ao Environment Agent para aplicar pesticida."""
            if self.agent.pesticide_amount < 0.5:
                self.agent.logger.warning("Pesticida insuficiente para aplicação.")
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

            self.agent.logger.info(f"Solicitando aplicação de pesticida em ({row},{col}) ao Environment Agent.")

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
                        self.agent.energy -= 3.0  # Gasto de energia
                        self.agent.logger.info(
                            f"Pesticida aplicado em ({row},{col}) com sucesso. Restante: {self.agent.pesticide_amount:.2f} kg. Energia: {self.agent.energy:.2f}%"
                        )
                        return True
                    else:
                        self.agent.logger.error(f"Resposta de erro do Environment Agent ao aplicar pesticida: {content.get('message')}")
                        return False
                except json.JSONDecodeError:
                    self.agent.logger.error(f"Erro ao descodificar JSON da resposta: {reply.body}")
                    return False
            else:
                self.agent.logger.error("Timeout ao esperar por resposta do Environment Agent para aplicação de pesticida.")
                return False

        async def run(self):
            # 1. Verificar recursos
            if self.agent.status == "charging":
                # Se já estiver a carregar, não faz mais nada
                return

            if self.agent.energy < BATTERY_LOW_THRESHOLD:
                self.agent.logger.warning(f"Bateria baixa ({self.agent.energy:.2f}%). Solicitando recarga.")
                # Adiciona o comportamento CFP para solicitar recarga
                self.agent.add_behaviour(
                    self.agent.CFPBehaviour(
                        timeout_wait=10,
                        task_type="battery",
                        required_resources={"energy": 100.0 - self.agent.energy},
                        priority=1,
                    )
                )
                self.agent.status = "handling_task"
                return

            if self.agent.pesticide_amount < PESTICIDE_LOW_THRESHOLD:
                self.agent.logger.warning(f"Pesticida baixo ({self.agent.pesticide_amount:.2f} kg). Solicitando reabastecimento.")
                # Adiciona o comportamento CFP para solicitar reabastecimento
                self.agent.add_behaviour(
                    self.agent.CFPBehaviour(
                        timeout_wait=10,
                        task_type="pesticides",
                        required_resources={"pesticide": self.agent.max_pesticide_amount - self.agent.pesticide_amount},
                        priority=1,
                    )
                )
                self.agent.status = "handling_task"
                return

            # 2. Patrulhar
            self.agent.status = "flying"
            
            # Simula o movimento
            current_zone_index = self.agent.zones.index(self.agent.position)
            next_zone_index = (current_zone_index + 1) % len(self.agent.zones)
            next_zone = self.agent.zones[next_zone_index]
            
            self.agent.position = next_zone
            self.agent.energy -= 1.0  # Gasto de energia por movimento
            
            row, col = self.agent.position
            self.agent.logger.info(f"Patrulhando zona ({row},{col}). Energia: {self.agent.energy:.2f}%.")

            # 3. Obter dados da cultura
            try:
                # A chamada foi corrigida para usar o método do Behaviour
                crop_stage, crop_type, pest_level = await self._get_drone_data(row, col)
            except Exception as e:
                self.agent.logger.error(f"Erro ao obter dados da cultura: {e}")
                return

            # 4. Analisar dados e agir
            if pest_level and pest_level > 0.5:
                self.agent.logger.warning(f"Alto nível de pragas ({pest_level:.2f}) em ({row},{col}). Aplicando pesticida.")
                # A chamada foi corrigida para usar o método do Behaviour
                await self._apply_pesticide(row, col)
            
            if crop_stage == "mature":
                self.agent.logger.info(f"Cultura madura em ({row},{col}). Informando Logistics.")
                # A chamada foi corrigida para usar o método do Behaviour
                await self._inform_crop(row, col, "1 -> Ready for harvesting")
            
            if crop_stage == "not_planted":
                self.agent.logger.info(f"Zona ({row},{col}) não plantada. Informando Logistics.")
                # A chamada foi corrigida para usar o método do Behaviour
                await self._inform_crop(row, col, "0 -> not planted")

            self.agent.status = "idle"
            
            # 5. Log de recursos
            self.agent.logger.info(
                f"Recursos: Energia={self.agent.energy:.2f}%, Pesticida={self.agent.pesticide_amount:.2f}kg."
            )



async def main():
    # Configurar logging para ver o output
    logging.basicConfig(level=logging.INFO)
    
    # Definições do Agente
    DRONE_JID = "drone@localhost"
    DRONE_PASS = "dronepass"

    # Inicializar e iniciar o agente
    env_agent = DroneAgent(DRONE_JID, DRONE_PASS,[(0,0),(0,1),(0,2),(0,3)],0,0)
    await env_agent.start()
    
    logger.info("Agente Drone em execução. Pressione Ctrl+C para parar.")
    
    # Manter o agente a correr
    try:
        while env_agent.is_alive():
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if env_agent.is_alive():
            await env_agent.stop()
        logger.info("Agente Ambiente parado.")


if __name__ == "__main__":
    asyncio.run(main())