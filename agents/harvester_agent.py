from spade.agent import Agent
from spade.behaviour import PeriodicBehaviour, OneShotBehaviour, CyclicBehaviour
from spade.template import Template
import time
import asyncio
import json
import logging
import random

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

PERFORMATIVE_INFORM_HARVEST = "inform_harvest"
PERFORMATIVE_INFORM_RECEIVED = "inform_received"

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

class HarvestYieldBehaviour(PeriodicBehaviour):
    """Verifica o rendimento e inicia o processo de colheita quando atinge o limite."""

    async def run(self):
        if self.agent.status == "idle": # Só pode iniciar a colheita se estiver livre
            harvest_ready = False
            for seed_type, amount in self.agent.yield_seed.items():
                if amount >= 100:
                    harvest_ready = True
                    break
            
            if harvest_ready:
                self.agent.logger.info(f"[YIELD] Limite de colheita atingido. A iniciar processo de entrega.")
                self.agent.status = "delivering_harvest"
                # Escolhe um logístico aleatoriamente
                logistic_agent_jid = random.choice(self.agent.log_jids)
                
                # Inicia o comportamento de entrega
                delivery_behaviour = DeliverHarvestBehaviour(logistic_agent_jid)
                self.agent.add_behaviour(delivery_behaviour)

class DeliverHarvestBehaviour(OneShotBehaviour):
    """Simula a viagem e envia a colheita para um agente logístico."""
    def __init__(self, logistic_jid):
        super().__init__()
        self.logistic_jid = logistic_jid

    async def run(self):
        self.agent.logger.info(f"[DELIVERY] A viajar para entregar a colheita ao logístico {self.logistic_jid}.")
        
        # Simula o tempo de viagem (ida e volta)
        await asyncio.sleep(5)
        
        # Prepara a mensagem com os dados da colheita
        amount_type_list = []
        for seed_type, amount in self.agent.yield_seed.items():
            if amount >= 100:
                amount_type_list.append({"seed_type": seed_type, "amount": amount})
                break

        # Envia a mensagem `inform_harvest`
        await self.agent.send_inform_harvest(self.logistic_jid, amount_type_list)
        self.agent.logger.info(f"[DELIVERY] Mensagem 'inform_harvest' enviada para {self.logistic_jid}.")

class InformReceivedReceiver(CyclicBehaviour):
    """Recebe a confirmação 'inform_received' do agente logístico."""
    async def run(self):
        template = Template()
        template.set_metadata("performative", PERFORMATIVE_INFORM_RECEIVED)
        msg = await self.receive(timeout=5)

        if msg:
            try:
                content = json.loads(msg.body)
                self.agent.logger.info(f"[DELIVERY] Confirmação 'inform_received' recebida de {msg.sender}.")
                
                # Extrai os detalhes do que foi recebido
                details = content.get("details")
                if details:
                    seed_type = details.get("seed_type")
                    amount_received = details.get("amount")

                    # Atualiza o yield_seed, subtraindo a quantidade entregue
                    if seed_type in self.agent.yield_seed:
                        self.agent.yield_seed[seed_type] -= amount_received
                        self.agent.logger.info(f"[DELIVERY] Yield de semente {seed_type} atualizado. Novo valor: {self.agent.yield_seed[seed_type]}.")

                # O agente volta ao estado 'idle' após a confirmação
                self.agent.status = "idle"
                self.agent.logger.info("[STATUS] Agente voltou ao estado 'idle'.")

            except json.JSONDecodeError:
                self.agent.logger.error(f"[DELIVERY] Erro ao descodificar JSON da confirmação: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[DELIVERY] Erro ao processar 'inform_received': {e}")
                self.agent.status = "idle" # Garante que o agente não fica bloqueado


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

                if self.agent.status != "idle": can_accept = False
                
                elif task_type == "harvest_application":
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
                    
                    self.agent.status = proposal_data["task_type"].split('_')[0] # harvesting ou planting
                    self.agent.add_behaviour(b)
                    
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


class AnalyseRechargeProposalsBehaviour(OneShotBehaviour):
    """Analisa as propostas de reabastecimento recebidas e escolhe a melhor."""
    
    def __init__(self, cfp_id):
        super().__init__()
        self.cfp_id = cfp_id
        
    async def run(self):
        proposals = self.agent.recharge_proposals
        
        if not proposals:
            self.agent.logger.warning(f"[RECHARGE] Nenhuma proposta de reabastecimento recebida para CFP {self.cfp_id}. O agente permanece em 'refueling'.")
            # O CheckResourcesBehaviour irá tentar novamente
            return
            
        # 1. Escolher a melhor proposta (menor eta_ticks)
        best_proposal = min(proposals.values(), key=lambda p: p["eta_ticks"])
        best_agent_jid = best_proposal["sender"]
        
        self.agent.chosen_logistic_agent = best_agent_jid
        self.agent.logger.info(f"[RECHARGE] Proposta escolhida: {best_agent_jid} com ETA: {best_proposal['eta_ticks']}.")
        
        # 2. Enviar ACCEPT para o melhor
        await self.agent.send_accept_proposal(best_agent_jid, self.cfp_id)
        
        # 3. Enviar REJECT para os restantes
        for agent_jid, proposal in proposals.items():
            if agent_jid != best_agent_jid:
                await self.agent.send_reject_proposal(agent_jid, self.cfp_id)
                
        # Limpar propostas
        self.agent.recharge_proposals = {}


class RechargeResponseReceiver(CyclicBehaviour):
    """Recebe e processa as respostas (Failure/Done) ao CFP de reabastecimento."""

    def __init__(self):
        super().__init__()
        self.cfp_id = None
        self.proposals_received = 0
        self.proposals_expected = 0
        self.timeout_task = None

    async def run(self):
        # Espera por mensagens Propose, Accept/Reject ou Done do Logistic Agent
        template = Template()
        template.set_metadata("performative", PERFORMATIVE_FAILURE)
        template.set_metadata("performative", PERFORMATIVE_DONE)
        msg = await self.receive(timeout=5)

        if msg:
            try:
                content = json.loads(msg.body)
                cfp_id = content.get("cfp_id")
                performative = msg.get_metadata("performative")

                    
                if performative == PERFORMATIVE_DONE:
                    # 3. O Logistic Agent informa que o reabastecimento foi concluído.
                    details = content.get("details", {})
                    
                    # Apenas atualiza os recursos se o agente que enviou o DONE for o agente escolhido
                    if str(msg.sender) == self.agent.chosen_logistic_agent:
                        if "fuel_used" in details:
                            # O Logistic Agent reabasteceu o combustível. O 'fuel_used' é a quantidade reabastecida.
                            recharged_amount = details["fuel_used"]
                            self.agent.fuel_level += recharged_amount
                            # Limitar ao máximo de 100
                            self.agent.fuel_level = min(self.agent.fuel_level, 100)
                            self.agent.logger.info(f"[RECHARGE] Combustível reabastecido em {recharged_amount:.2f}. Nível atual: {self.agent.fuel_level:.2f}.")
                            
                        if "seed_used" in details:
                            # O Logistic Agent reabasteceu as sementes. O 'seed_used' é a quantidade reabastecida.
                            recharged_amount = details["seed_used"]
                            seed_type = details.get("seed_type")
                            
                            if seed_type is not None:
                                # O CheckResourcesBehaviour pede para reabastecer até 500, então vamos assumir que é esse o limite.
                                self.agent.seeds[seed_type] += recharged_amount
                                self.agent.seeds[seed_type] = min(self.agent.seeds[seed_type], 500)
                                self.agent.logger.info(f"[RECHARGE] Semente {seed_type} reabastecida em {recharged_amount}. Nível atual: {self.agent.seeds[seed_type]}.")
                            else:
                                self.agent.logger.warning("[RECHARGE] Mensagem DONE de sementes sem 'seed_type'. Ignorando atualização de sementes.")
                                
                        self.agent.status = "idle"
                        self.agent.chosen_logistic_agent = None
                        self.agent.logger.info(f"[RECHARGE] Reabastecimento {cfp_id} concluído. Agente IDLE.")
                    else:
                        self.agent.logger.warning(f"[RECHARGE] Recebido DONE de {msg.sender}, mas o agente escolhido é {self.agent.chosen_logistic_agent}. Ignorando atualização de recursos.")
                        
                elif performative == PERFORMATIVE_FAILURE:
                    # 4. Falha na Proposta (pode ser do agente logístico que rejeitou o nosso CFP)
                    self.agent.logger.warning(f"[RECHARGE] Proposta de reabastecimento {cfp_id} FALHOU por {msg.sender}. O agente permanece em 'refueling'.")
                    # O agente permanece em 'refueling' e o CheckResourcesBehaviour irá tentar novamente se necessário.

                    
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
        self.seed_type = self.proposal_data["seed_type"]
        self.required_storage = next((res["amount"] for res in self.proposal_data["required_resources"] if res["type"] == "storage"), 0)

    async def run(self):
        self.agent.logger.info(f"[HARVEST] A iniciar colheita para CFP {self.cfp_id} em {self.zone}.")
        
        try:
            self.status = "moving"
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
                    self.agent.yield_seed[self.seed_type] += yield_amount
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
        self.machine_capacity = 600  # Capacidade da máquina de colheita
        self.machine_inventory = 0  # Inventário inicial da máquina (total_harvested)

        self.yield_seed = {
            0: 0, # 0: Tomate
            1: 0, # 1: Pimento
            2: 0, # 2: Trigo
            3: 0, # 3: Couve
            4: 0, # 4: Alface
            5: 0  # 5: Cenoura
        }

        self.seeds = {
            0: 500, # 0: Tomate 
            1: 500, # 1: Pimento
            2: 500, # 2: Trigo
            3: 500, # 3: Couve
            4: 500, # 4: Alface
            5: 500  # 5: Cenoura
        }
        self.fuel_level = 100  # Nível inicial de combustível
        self.status = "idle"  # harvesting, planting, refueling, idle, delivering_harvest
        self.env_jid = env_jid
        # Garante que self.log_jids é uma lista, mesmo que apenas um JID seja passado
       
        self.log_jids = log_jid
        
        # Estrutura para armazenar propostas de reabastecimento recebidas
        self.recharge_proposals = {}
        self.chosen_logistic_agent = None # Agente logístico escolhido para o reabastecimento

        # Estrutura para armazenar propostas recebidas (por cfp_id)
        self.awaiting_proposals = {}
        
    # =====================
    # MÉTODOS DE COMUNICAÇÃO
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

    async def send_inform_harvest(self, to, amount_type_list):
        """Envia uma mensagem inform_harvest para o agente logístico."""
        body = {
            "sender_id": str(self.jid),
            "receiver_id": str(to),
            "inform_id": f"inform_harvest_{time.time()}",
            "amount_type": amount_type_list,
            "checked_at": time.time()
        }
        msg = make_message(to, PERFORMATIVE_INFORM_HARVEST, body)
        await self.send(msg)
        self.logger.info(f"[HARVEST] Mensagem 'inform_harvest' enviada para {to}.")

    async def send_recharge_cfp(self, resource_type, amount, seed_type=None):
        """Envia um CFP de reabastecimento a todos os Logistic Agents."""
        cfp_id = f"cfp_recharge_{time.time()}"
        
        # Limpar propostas anteriores antes de enviar um novo CFP
        self.recharge_proposals = {}
        
        for log_jid in self.log_jids:
            body = {
                "sender_id": str(self.jid),
                "receiver_id": str(log_jid),
                "cfp_id": cfp_id,
                "task_type": resource_type, # fuel ou seeds
                "required_resources": amount,
                "position": self.pos_initial,
                "seed_type": seed_type,
                "priority": "Urgent"
            }
            msg = make_message(log_jid, PERFORMATIVE_CFP_RECHARGE, body)
            await self.send(msg)
            self.logger.info(f"[RECHARGE] CFP de reabastecimento ({resource_type}, {amount}) enviado para {log_jid}: {cfp_id}.")

    # =====================
    #   SETUP
    # =====================

    async def setup(self):
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

        # 5. Comportamento para verificar o rendimento da colheita
        self.add_behaviour(HarvestYieldBehaviour(period=15))

        # 6. Comportamento para receber confirmações de entrega da colheita
        template_inform_received = Template()
        template_inform_received.set_metadata("performative", PERFORMATIVE_INFORM_RECEIVED)
        self.add_behaviour(InformReceivedReceiver(), template=template_inform_received)
