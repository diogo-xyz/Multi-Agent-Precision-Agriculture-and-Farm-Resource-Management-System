from spade.agent import Agent
from spade.behaviour import PeriodicBehaviour, OneShotBehaviour, CyclicBehaviour
from spade.template import Template
from spade.message import Message
import time
import asyncio
import json
import logging

from agents.message import make_message

# Constantes
PERFORMATIVE_CFP_TASK = "cfp_task"
PERFORMATIVE_PROPOSE_TASK = "propose_task"
PERFORMATIVE_ACCEPT_PROPOSAL = "accept-proposal"
PERFORMATIVE_REJECT_PROPOSAL = "reject-proposal"
PERFORMATIVE_DONE = "Done"
PERFORMATIVE_FAILURE = "failure"
PERFORMATIVE_CFP_RECHARGE = "cfp_recharge"
PERFORMATIVE_PROPOSE_RECHARGE = "propose_recharge"
PERFORMATIVE_INFORM = "inform"

ONTOLOGY_FARM_ACTION = "farm_action"

# =====================
#   FUNÇÕES AUXILIARES
# =====================

def calculate_distance(pos1, pos2):
    """Calcula a distância de Manhattan entre duas posições (row, col)."""
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

def calculate_fuel_cost(distance):
    """Calcula o custo de combustível (ida e volta) com base na distância de Manhattan."""
    # Cada 2 valores de distância é -0.5 de combustível.
    # Custo de ida: (distance / 2) * 0.5
    # Custo de ida e volta: 2 * (distance / 2) * 0.5 = distance * 0.5
    return distance * 0.5

# =====================
#   BEHAVIOURS
# =====================

class CheckResourcesBehaviour(PeriodicBehaviour):
    """Verifica periodicamente o nível de combustível e sementes e solicita reabastecimento se necessário."""
    
    def __init__(self, period, agent):
        super().__init__(period)
        self.agent = agent

    async def run(self):
        # 1. Verificar Combustível
        if self.agent.fuel_level < 10 and self.agent.status != "refueling":
            self.agent.logger.warning(f"Nível de combustível baixo ({self.agent.fuel_level:.2f}). Solicitando reabastecimento.")
            await self.agent.send_recharge_cfp("fuel", 100 - self.agent.fuel_level)
            self.agent.status = "refueling" # Bloqueia novas tarefas até reabastecer

        # 2. Verificar Sementes (se alguma semente estiver abaixo de 10)
        for seed_type, amount in self.agent.seeds.items():
            if amount < 10 and self.agent.status != "refueling":
                self.agent.logger.warning(f"Nível de semente {seed_type} baixo ({amount}). Solicitando reabastecimento.")
                # Pede para reabastecer até 500 (capacidade inicial)
                await self.agent.send_recharge_cfp("seeds", 500 - amount, seed_type)
                self.agent.status = "refueling" # Bloqueia novas tarefas até reabastecer
                break # Apenas um pedido de reabastecimento de sementes de cada vez

class CFPTaskReceiver(CyclicBehaviour):
    """Recebe e processa mensagens CFP (Call For Proposal) do Logistic Agent."""

    async def run(self):
        # Espera por mensagens CFP do Logistic Agent
        template = Template()
        template.set_metadata("performative", PERFORMATIVE_CFP_TASK)
        msg = await self.receive(timeout=5)

        if msg:
            try:
                content = json.loads(msg.body)
                cfp_id = content.get("cfp_id")
                task_type = content.get("task_type")
                zone = content.get("zone")
                seed_type = content.get("seed_type")
                required_resources = content.get("required_resources", [])
                
                self.agent.logger.info(f"[CFP] Recebido CFP {cfp_id} para {task_type} em {zone}.")

                # 1. Verificar se o agente está ocupado ou a reabastecer
                if self.agent.status != "idle":
                    self.agent.logger.info(f"[CFP] Agente ocupado ({self.agent.status}). Rejeitando proposta.")
                    await self.agent.send_reject_proposal(msg.sender, cfp_id)
                    return

                # 2. Calcular a distância e o custo de combustível
                target_pos = tuple(zone)
                distance = calculate_distance(self.agent.pos_initial, target_pos)
                fuel_needed = calculate_fuel_cost(distance)
                
                # 3. Verificar Capacidade e Recursos
                can_accept = False
                
                if task_type == "harvest_application":
                    # Colheita: Verificar capacidade de armazenamento e combustível
                    required_storage = next((res["amount"] for res in required_resources if res["type"] == "storage"), 0)
                    
                    if self.agent.machine_inventory + required_storage <= self.agent.machine_capacity:
                        if self.agent.fuel_level >= fuel_needed:
                            can_accept = True
                            self.agent.logger.info(f"[CFP] Colheita: Capacidade e Combustível OK. Inventário: {self.agent.machine_inventory}/{self.agent.machine_capacity}, Combustível: {self.agent.fuel_level:.2f}/{fuel_needed:.2f}.")
                        else:
                            self.agent.logger.warning(f"[CFP] Colheita: Combustível insuficiente ({self.agent.fuel_level:.2f} < {fuel_needed:.2f}).")
                    else:
                        self.agent.logger.warning(f"[CFP] Colheita: Capacidade insuficiente ({self.agent.machine_inventory + required_storage} > {self.agent.machine_capacity}).")

                elif task_type == "plant_application":
                    # Plantação: Verificar sementes e combustível
                    required_seeds = next((res["amount"] for res in required_resources if res["type"] == "seed"), 0)
                    
                    if seed_type is not None and self.agent.seeds.get(seed_type, 0) >= required_seeds:
                        if self.agent.fuel_level >= fuel_needed:
                            can_accept = True
                            self.agent.logger.info(f"[CFP] Plantação: Sementes e Combustível OK. Sementes {seed_type}: {self.agent.seeds.get(seed_type)}, Combustível: {self.agent.fuel_level:.2f}/{fuel_needed:.2f}.")
                        else:
                            self.agent.logger.warning(f"[CFP] Plantação: Combustível insuficiente ({self.agent.fuel_level:.2f} < {fuel_needed:.2f}).")
                    else:
                        self.agent.logger.warning(f"[CFP] Plantação: Sementes {seed_type} insuficientes ({self.agent.seeds.get(seed_type, 0)} < {required_seeds}).")
                
                else:
                    self.agent.logger.warning(f"[CFP] Tipo de tarefa desconhecido: {task_type}. Rejeitando.")
                    await self.agent.send_reject_proposal(msg.sender, cfp_id)
                    return

                # 4. Responder ao CFP
                if can_accept:
                    # Armazenar a proposta à espera de aceitação
                    self.agent.awaiting_proposals[cfp_id] = {
                        "task_type": task_type,
                        "zone": target_pos,
                        "seed_type": seed_type,
                        "required_resources": required_resources,
                        "fuel_cost": fuel_needed,
                        "sender": str(msg.sender)
                    }
                    
                    # Enviar Proposta
                    await self.agent.send_propose_task(msg.sender, cfp_id, distance, fuel_needed)
                else:
                    await self.agent.send_reject_proposal(msg.sender, cfp_id)

            except json.JSONDecodeError:
                self.agent.logger.error(f"[CFP] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[CFP] Erro ao processar CFP: {e}")
        else:
            await asyncio.sleep(0.1)


class ProposalResponseReceiver(CyclicBehaviour):
    """Recebe e processa a resposta (Accept/Reject) à proposta enviada."""

    async def run(self):
        # Espera por mensagens Accept ou Reject do Logistic Agent
        template = Template()
        template.set_metadata("performative", PERFORMATIVE_ACCEPT_PROPOSAL)
        template.set_metadata("performative", PERFORMATIVE_REJECT_PROPOSAL)
        msg = await self.receive(timeout=5)

        if msg:
            try:
                content = json.loads(msg.body)
                cfp_id = content.get("cfp_id")
                decision = content.get("decision")
                
                if cfp_id not in self.agent.awaiting_proposals:
                    self.agent.logger.warning(f"[PROPOSAL] Resposta recebida para CFP desconhecido: {cfp_id}. Ignorando.")
                    return

                proposal_data = self.agent.awaiting_proposals.pop(cfp_id)
                
                if decision == "accept":
                    self.agent.logger.info(f"[PROPOSAL] Proposta {cfp_id} ACEITE para {proposal_data['task_type']} em {proposal_data['zone']}.")
                    
                    # Iniciar o comportamento de execução da tarefa
                    if proposal_data["task_type"] == "harvest_application":
                        b = HarvestExecutionBehaviour(proposal_data)
                    elif proposal_data["task_type"] == "plant_application":
                        b = PlantExecutionBehaviour(proposal_data)
                    else:
                        self.agent.logger.error(f"[PROPOSAL] Tipo de tarefa desconhecido após aceitação: {proposal_data['task_type']}")
                        return
                        
                    self.agent.add_behaviour(b)
                    self.agent.status = proposal_data["task_type"].split('_')[0] # harvesting ou planting
                    
                elif decision == "reject":
                    self.agent.logger.info(f"[PROPOSAL] Proposta {cfp_id} REJEITADA para {proposal_data['task_type']}.")
                    # O agente volta a ficar idle
                    self.agent.status = "idle"
                    
                else:
                    self.agent.logger.warning(f"[PROPOSAL] Decisão desconhecida: {decision}.")

            except json.JSONDecodeError:
                self.agent.logger.error(f"[PROPOSAL] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[PROPOSAL] Erro ao processar resposta à proposta: {e}")
        else:
            await asyncio.sleep(0.1)


class RechargeResponseReceiver(CyclicBehaviour):
    """Recebe e processa a resposta (Propose/Accept/Reject) ao CFP de reabastecimento."""

    async def run(self):
        # Espera por mensagens Propose, Accept/Reject ou Done do Logistic Agent
        template = Template()
        template.set_metadata("performative", PERFORMATIVE_ACCEPT_PROPOSAL)
        template.set_metadata("performative", PERFORMATIVE_REJECT_PROPOSAL)
        template.set_metadata("performative", PERFORMATIVE_DONE)
        msg = await self.receive(timeout=5)

        if msg:
            try:
                content = json.loads(msg.body)
                cfp_id = content.get("cfp_id")
            
                if msg.get_metadata("performative") == PERFORMATIVE_ACCEPT_PROPOSAL:
                    # O Logistic Agent aceitou o nosso CFP. O HarvesterAgent espera agora pelo DONE.
                    self.agent.logger.info(f"[RECHARGE] Proposta de reabastecimento {cfp_id} ACEITE. A aguardar conclusão do reabastecimento pelo Logistic Agent.")
                    # O agente permanece em 'refueling'
                    
                elif msg.get_metadata("performative") == PERFORMATIVE_DONE:
                    # O Logistic Agent informa que o reabastecimento foi concluído.
                    details = content.get("details", {})
                    
                    if "fuel_used" in details:
                        # O Logistic Agent reabasteceu o combustível. O 'fuel_used' é a quantidade reabastecida.
                        recharged_amount = details["fuel_used"]
                        self.agent.fuel_level += recharged_amount
                        # Limitar ao máximo de 100
                        self.agent.fuel_level = min(self.agent.fuel_level, 100)
                        self.agent.logger.info(f"[RECHARGE] Combustível reabastecido em {recharged_amount:.2f}. Nível atual: {self.agent.fuel_level:.2f}.")
                        
                    if "seed_type" in details:
                        # O Logistic Agent reabasteceu as sementes. O 'seeds_type' é a quantidade reabastecida.
                        recharged_amount = details["seeds_type"]
                        seed_type = details.get("seed_type")
                        
                        if seed_type is not None:
                            # O CheckResourcesBehaviour pede para reabastecer até 500, então vamos assumir que é esse o limite.
                            self.agent.seeds[seed_type] += recharged_amount
                            self.agent.seeds[seed_type] = min(self.agent.seeds[seed_type], 500)
                            self.agent.logger.info(f"[RECHARGE] Semente {seed_type} reabastecida em {recharged_amount}. Nível atual: {self.agent.seeds[seed_type]}.")
                        else:
                            self.agent.logger.warning("[RECHARGE] Mensagem DONE de sementes sem 'seed_type'. Ignorando atualização de sementes.")
                            
                    self.agent.status = "idle"
                    self.agent.logger.info(f"[RECHARGE] Reabastecimento {cfp_id} concluído. Agente IDLE.")
                    
                elif msg.get_metadata("performative") == PERFORMATIVE_REJECT_PROPOSAL:
                    self.agent.logger.warning(f"[RECHARGE] Proposta de reabastecimento {cfp_id} REJEITADA. O agente permanece em 'refueling'.")
                    # O agente permanece em 'refueling' e o CheckResourcesBehaviour irá tentar novamente.

                    
            except json.JSONDecodeError:
                self.agent.logger.error(f"[RECHARGE] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[RECHARGE] Erro ao processar resposta de reabastecimento: {e}")
        else:
            await asyncio.sleep(0.1)


class HarvestExecutionBehaviour(OneShotBehaviour):
    """Executa a tarefa de colheita após a aceitação da proposta."""
    
    def __init__(self, proposal_data):
        super().__init__()
        self.proposal_data = proposal_data
        self.cfp_id = self.proposal_data["cfp_id"]
        self.logistic_agent = self.proposal_data["sender"]
        self.zone = self.proposal_data["zone"]
        self.fuel_cost = self.proposal_data["fuel_cost"]
        self.required_storage = next((res["amount"] for res in self.proposal_data["required_resources"] if res["type"] == "storage"), 0)

    async def run(self):
        self.agent.logger.info(f"[HARVEST] A iniciar colheita para CFP {self.cfp_id} em {self.zone}.")
        
        try:
            # 1. Simular ida ao local
            self.agent.logger.info(f"[HARVEST] A viajar para {self.zone}. Custo de combustível (ida e volta): {self.fuel_cost:.2f}.")
            await asyncio.sleep(5) # Simular tempo de viagem
            
            # 2. Realizar a colheita (interagir com o Environment Agent)
            harvest_body = {
                "action": "harvest",
                "row": self.zone[0],
                "col": self.zone[1]
            }
            
            msg_env = make_message(self.agent.env_jid, PERFORMATIVE_INFORM, harvest_body, {"ontology": ONTOLOGY_FARM_ACTION})
            await self.agent.send(msg_env)
            
            # Esperar pela resposta do Environment Agent
            msg_reply = await self.agent.receive(timeout=10)
            
            if msg_reply and msg_reply.get_metadata("performative") == PERFORMATIVE_INFORM:
                reply_content = json.loads(msg_reply.body)
                if reply_content.get("status") == "success":
                    yield_amount = reply_content.get("yield", 0)
                    
                    # 3. Atualizar o estado do agente
                    self.agent.machine_inventory += yield_amount
                    self.agent.fuel_level -= self.fuel_cost
                    
                    self.agent.logger.info(f"[HARVEST] Colheita concluída. Rendimento: {yield_amount:.2f}. Inventário: {self.agent.machine_inventory:.2f}. Combustível restante: {self.agent.fuel_level:.2f}.")
                    
                    # 4. Simular volta ao local inicial (já incluído no fuel_cost)
                    await asyncio.sleep(5) # Simular tempo de viagem de volta
                    
                    # 5. Enviar Done ao Logistic Agent
                    details = {
                        "harvested_amount": yield_amount,
                        "fuel_used": self.fuel_cost
                    }
                    await self.agent.send_done(self.logistic_agent, self.cfp_id, details)
                    
                else:
                    # Falha na interação com o Environment Agent
                    self.agent.logger.error(f"[HARVEST] Falha na colheita no Environment Agent: {reply_content.get('message')}")
                    await self.agent.send_failure(self.logistic_agent, self.cfp_id)
            else:
                # Timeout ou mensagem inesperada do Environment Agent
                self.agent.logger.error("[HARVEST] Timeout ou resposta inesperada do Environment Agent.")
                await self.agent.send_failure(self.logistic_agent, self.cfp_id)
                
        except Exception as e:
            self.agent.logger.exception(f"[HARVEST] Erro inesperado durante a colheita: {e}")
            await self.agent.send_failure(self.logistic_agent, self.cfp_id)
            
        finally:
            self.agent.status = "idle"
            self.agent.logger.info(f"[HARVEST] Tarefa {self.cfp_id} concluída. Agente IDLE.")


class PlantExecutionBehaviour(OneShotBehaviour):
    """Executa a tarefa de plantação após a aceitação da proposta."""
    
    def __init__(self, proposal_data):
        super().__init__()
        self.proposal_data = proposal_data
        self.cfp_id = self.proposal_data["cfp_id"]
        self.logistic_agent = self.proposal_data["sender"]
        self.zone = self.proposal_data["zone"]
        self.fuel_cost = self.proposal_data["fuel_cost"]
        self.seed_type = self.proposal_data["seed_type"]
        self.required_seeds = next((res["amount"] for res in self.proposal_data["required_resources"] if res["type"] == "seed"), 0)

    async def run(self):
        self.agent.logger.info(f"[PLANT] A iniciar plantação para CFP {self.cfp_id} em {self.zone} (Semente: {self.seed_type}).")
        
        try:
            # 1. Simular ida ao local
            self.agent.logger.info(f"[PLANT] A viajar para {self.zone}. Custo de combustível (ida e volta): {self.fuel_cost:.2f}.")
            await asyncio.sleep(5) # Simular tempo de viagem
            
            # 2. Realizar a plantação (interagir com o Environment Agent)
            plant_body = {
                "action": "plant_seed",
                "row": self.zone[0],
                "col": self.zone[1],
                "plant_type": self.seed_type
            }
            
            msg_env = make_message(self.agent.env_jid, PERFORMATIVE_INFORM, plant_body, {"ontology": ONTOLOGY_FARM_ACTION})
            await self.agent.send(msg_env)
            
            # Esperar pela resposta do Environment Agent
            msg_reply = await self.agent.receive(timeout=10)
            
            if msg_reply and msg_reply.get_metadata("performative") == PERFORMATIVE_INFORM:
                reply_content = json.loads(msg_reply.body)
                if reply_content.get("status") == "success":
                    
                    # 3. Atualizar o estado do agente
                    self.agent.seeds[self.seed_type] -= self.required_seeds
                    self.agent.fuel_level -= self.fuel_cost
                    
                    self.agent.logger.info(f"[PLANT] Plantação concluída. Sementes {self.seed_type} restantes: {self.agent.seeds[self.seed_type]}. Combustível restante: {self.agent.fuel_level:.2f}.")
                    
                    # 4. Simular volta ao local inicial (já incluído no fuel_cost)
                    await asyncio.sleep(5) # Simular tempo de viagem de volta
                    
                    # 5. Enviar Done ao Logistic Agent
                    details = {
                        "seeds_used": self.required_seeds,
                        "fuel_used": self.fuel_cost
                    }
                    await self.agent.send_done(self.logistic_agent, self.cfp_id, details)
                    
                else:
                    # Falha na interação com o Environment Agent
                    self.agent.logger.error(f"[PLANT] Falha na plantação no Environment Agent: {reply_content.get('message')}")
                    await self.agent.send_failure(self.logistic_agent, self.cfp_id)
            else:
                # Timeout ou mensagem inesperada do Environment Agent
                self.agent.logger.error("[PLANT] Timeout ou resposta inesperada do Environment Agent.")
                await self.agent.send_failure(self.logistic_agent, self.cfp_id)
                
        except Exception as e:
            self.agent.logger.exception(f"[PLANT] Erro inesperado durante a plantação: {e}")
            await self.agent.send_failure(self.logistic_agent, self.cfp_id)
            
        finally:
            self.agent.status = "idle"
            self.agent.logger.info(f"[PLANT] Tarefa {self.cfp_id} concluída. Agente IDLE.")


# =====================
#   AGENTE
# =====================

class HarvesterAgent(Agent):
    def __init__(self, jid, password, row, col, env_jid, log_jid):
        super().__init__(jid, password)
        
        # Configuração de Logging
        logger = logging.getLogger("jid")
        logger.setLevel(logging.INFO)


        self.logger = logger

        self.pos_initial = (row, col)
        self.row = row
        self.col = col
        self.machine_capacity = 100  # Capacidade da máquina de colheita
        self.machine_inventory = 0  # Inventário inicial da máquina (total_harvested)
        self.seeds = {
            0: 500, # 0: Tomate 
            1: 500, # 1: Pimento
            2: 500, # 2: Trigo
            3: 500, # 3: Couve
            4: 500, # 4: Alface
            5: 500  # 5: Cenoura
        }
        self.fuel_level = 100  # Nível inicial de combustível
        self.status = "idle"  # harvesting, planting, refueling, idle
        self.env_jid = env_jid
        self.log_jid = log_jid

        # Estrutura para armazenar propostas recebidas (por cfp_id)
        self.awaiting_proposals = {}
        
    # =====================
    #   MÉTODOS DE COMUNICAÇÃO
    # =====================
    
    async def send_propose_task(self, to, cfp_id, distance, fuel_cost):
        """Envia uma proposta de tarefa ao Logistic Agent."""
        eta_ticks = int(distance * 2 * 5 / 10) # 5 segundos por viagem de ida/volta, dividido por 10 (simulação de tick)
        
        body = {
            "sender_id": str(self.jid),
            "receiver_id": str(to),
            "cfp_id": cfp_id,
            "eta_ticks": max(1, eta_ticks), # Mínimo de 1 tick
            
            "fuel_cost": fuel_cost,
        }
        msg = make_message(to, PERFORMATIVE_PROPOSE_TASK, body)
        await self.send(msg)
        self.logger.info(f"[PROPOSE] Proposta enviada para CFP {cfp_id}. Custo: {fuel_cost:.2f} Combustível.")

    async def send_reject_proposal(self, to, cfp_id):
        """Envia uma rejeição de proposta ao Logistic Agent."""
        body = {
            "sender_id": str(self.jid),
            "receiver_id": str(to),
            "cfp_id": cfp_id,
            "decision": "reject"
        }
        msg = make_message(to, PERFORMATIVE_REJECT_PROPOSAL, body)
        await self.send(msg)
        self.logger.info(f"[REJECT] Proposta rejeitada para CFP {cfp_id}.")

    async def send_accept_proposal(self, to, cfp_id):
        """Envia uma aceitação de proposta ao Logistic Agent (usado para reabastecimento)."""
        body = {
            "sender_id": str(self.jid),
            "receiver_id": str(to),
            "cfp_id": cfp_id,
            "decision": "accept"
        }
        msg = make_message(to, PERFORMATIVE_ACCEPT_PROPOSAL, body)
        await self.send(msg)
        self.logger.info(f"[ACCEPT] Proposta aceite para CFP {cfp_id}.")

    async def send_done(self, to, cfp_id, details):
        """Envia mensagem de conclusão de tarefa ao Logistic Agent."""
        body = {
            "sender_id": str(self.jid),
            "receiver_id": str(to),
            "cfp_id": cfp_id,
            "status": "done",
            "details": details
        }
        msg = make_message(to, PERFORMATIVE_DONE, body)
        await self.send(msg)
        self.logger.info(f"[DONE] Tarefa {cfp_id} concluída.")

    async def send_failure(self, to, cfp_id):
        """Envia mensagem de falha de tarefa ao Logistic Agent."""
        body = {
            "sender_id": str(self.jid),
            "receiver_id": str(to),
            "cfp_id": cfp_id,
            "status": "failed"
        }
        msg = make_message(to, PERFORMATIVE_FAILURE, body)
        await self.send(msg)
        self.logger.warning(f"[FAILURE] Tarefa {cfp_id} falhou.")

    async def send_recharge_cfp(self, resource_type, amount, seed_type=None):
        """Envia um CFP de reabastecimento ao Logistic Agent."""
        cfp_id = f"cfp_recharge_{time.time()}"
        body = {
            "sender_id": str(self.jid),
            "receiver_id": str(self.log_jid),
            "cfp_id": cfp_id,
            "task_type": resource_type, # fuel ou seeds
            "required_resources": amount,
            "seed_type": seed_type,
            "priority": "Urgent"
        }
        msg = make_message(self.log_jid, PERFORMATIVE_CFP_RECHARGE, body)
        await self.send(msg)
        self.logger.info(f"[RECHARGE] CFP de reabastecimento ({resource_type}, {amount}) enviado: {cfp_id}.")

    # =====================
    #   SETUP
    # =====================

    def setup(self):
        self.logger.info(f"[HAR] HarvesterAgent {self.jid} iniciado. Posição: {self.pos_initial}")
        
        # 1. Comportamento para verificar recursos (combustível/sementes)
        self.add_behaviour(CheckResourcesBehaviour(period=10, agent=self))
        
        # 2. Comportamento para receber CFPs de Tarefas (Colheita/Plantação)
        template_cfp_task = Template()
        template_cfp_task.set_metadata("performative", PERFORMATIVE_CFP_TASK)
        self.add_behaviour(CFPTaskReceiver(), template=template_cfp_task)
        
        # 3. Comportamento para receber respostas às propostas de Tarefas
        template_task_response = Template()
        template_task_response.set_metadata("performative", PERFORMATIVE_ACCEPT_PROPOSAL)
        template_task_response.set_metadata("performative", PERFORMATIVE_REJECT_PROPOSAL)
        self.add_behaviour(ProposalResponseReceiver(), template=template_task_response)
        
        # 4. Comportamento para receber respostas ao CFP de Reabastecimento
        template_recharge_response = Template()
        template_recharge_response.set_metadata("performative", PERFORMATIVE_PROPOSE_RECHARGE)
        template_recharge_response.set_metadata("performative", PERFORMATIVE_ACCEPT_PROPOSAL)
        template_recharge_response.set_metadata("performative", PERFORMATIVE_REJECT_PROPOSAL)
        self.add_behaviour(RechargeResponseReceiver(), template=template_recharge_response)
