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
PERFORMATIVE_ACT = "act"

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

    def __init__(self, period, stop_beha = None):
        super().__init__(period=period)
        self.stop_beha = stop_beha

    async def run(self):
        if self.agent.status == "idle" or self.stop_beha: # Só pode iniciar a colheita se estiver livre
            harvest_ready = False
            for seed_type, amount in self.agent.yield_seed.items():
                if amount >= 100 or self.stop_beha:
                    harvest_ready = True
                    break
            
            if harvest_ready:
                self.agent.logger.info(f"[YIELD] Limite de colheita atingido. A iniciar processo de entrega.")
                self.agent.status = "delivering_harvest"
                # Escolhe um logístico aleatoriamente
                
                # Inicia o comportamento de entrega
                delivery_behaviour = DeliverHarvestBehaviour(self.agent.sto_jid,self.stop_beha)
                self.agent.add_behaviour(delivery_behaviour)

class DeliverHarvestBehaviour(OneShotBehaviour):
    """Simula a viagem e envia a colheita para um agente logístico."""
    def __init__(self, sto_jid,stop_beha):
        super().__init__()
        self.sto_jid = sto_jid
        self.stop_beha = stop_beha

    async def run(self):
        self.agent.logger.info(f"[DELIVERY] A viajar para entregar a colheita ao logístico {self.sto_jid}.")
        
        # Simula o tempo de viagem (ida e volta)
        await asyncio.sleep(5)
        
        # Prepara a mensagem com os dados da colheita
        amount_type_list = []
        for seed_type, amount in self.agent.yield_seed.items():
            if amount >= 100 or self.stop_beha:
                amount_type_list.append({"seed_type": seed_type, "amount": amount})

        # Envia a mensagem `inform_harvest`
        msg = await self.agent.send_inform_harvest(self.sto_jid, amount_type_list)
        await self.send(msg)
        self.agent.logger.info(f"[DELIVERY] Mensagem 'inform_harvest' enviada para {self.sto_jid}.")
        if self.stop_beha: self.kill()

class InformReceivedReceiver(CyclicBehaviour):
    """Recebe a confirmação 'inform_received' do agente Storage."""
    async def run(self):
        msg = await self.receive(timeout=5)

        if msg:
            try:
                content = json.loads(msg.body)
                self.agent.logger.info(f"[DELIVERY] Confirmação 'inform_received' recebida de {msg.sender}.")
                
                # Extrai os detalhes do que foi recebido
                details = content.get("details")
                if details:

                    for detail in details:
                        seed_type = detail.get("seed_type")
                        amount_received = detail.get("amount")

                        # Atualiza o yield_seed, subtraindo a quantidade entregue
                        if seed_type in self.agent.yield_seed:
                            self.agent.yield_seed[seed_type] -= amount_received
                            self.agent.machine_inventory -= amount_received
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
            self.agent.status = "refueling"
            self.recharge_proposals = {}

            # Envia CFP para todos os Logistics e inicia o comportamento de recolha de propostas
            cfp_id, body = await self.agent.send_cfp_recharge_to_all(low_fuel=True, low_seeds=False)

            for to_jid in self.agent.log_jids:
                msg = make_message(to_jid, PERFORMATIVE_CFP_RECHARGE, body)
                await self.send(msg)
                self.agent.logger.info(f"CFP_RECHARGE ({cfp_id}) enviado para {to_jid} a pedir {body["task_type"]} ({body["required_resources"]}).")

            template = Template()
            template.set_metadata("performative", PERFORMATIVE_PROPOSE_RECHARGE)
            # Adiciona o comportamento para receber as propostas
            receive_proposals_b = ReceiveRechargeProposalsBehaviour(cfp_id)
            self.agent.add_behaviour(receive_proposals_b, template=template)
            return # Sai para processar apenas uma recarga de cada vez

        # 2. Verificar Sementes (se alguma semente estiver abaixo de 10)
        for seed_type, amount in self.agent.seeds.items():
            if amount < 10 and self.agent.status != "refueling":
                self.recharge_proposals = {}
                self.agent.logger.warning(f"Nível de semente {seed_type} baixo ({amount}). Solicitando reabastecimento.")
                self.agent.status = "refueling"
                # Envia CFP para todos os Logistics e inicia o comportamento de recolha de propostas
                cfp_id, body = await self.agent.send_cfp_recharge_to_all(low_fuel=False, low_seeds=True, seed_type=seed_type, required_resources= 100 - amount)

                for to_jid in self.agent.log_jids:
                    msg = make_message(to_jid, PERFORMATIVE_CFP_RECHARGE, body)
                    await self.send(msg)
                    self.agent.logger.info(f"CFP_RECHARGE ({cfp_id}) enviado para {to_jid} a pedir {body["task_type"]} ({body["required_resources"]}).")
                
                template = Template()
                template.set_metadata("performative", PERFORMATIVE_PROPOSE_RECHARGE)

                # Adiciona o comportamento para receber as propostas
                receive_proposals_b = ReceiveRechargeProposalsBehaviour(cfp_id)
                self.agent.add_behaviour(receive_proposals_b, template = template)
                break # Apenas um pedido de recarga de cada vez

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
                    msg = await self.agent.send_reject_proposal(msg.sender, cfp_id)
                    await self.send(msg)
                    self.agent.logger.info(f"[REJECT] Proposta rejeitada para CFP {cfp_id}.")
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
                    msg = await self.agent.send_reject_proposal(msg.sender, cfp_id)
                    await self.send(msg)
                    self.agent.logger.info(f"[REJECT] Proposta rejeitada para CFP {cfp_id}.")
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
                    msg = await self.agent.send_propose_task(msg.sender, cfp_id, distance, fuel_needed)
                    await self.send(msg)
                    self.agent.logger.info(f"[ACCEPT] Proposta aceite para CFP {cfp_id}.")
                else:
                    msg = await self.agent.send_reject_proposal(msg.sender, cfp_id)
                    await self.send(msg)
                    self.agent.logger.info(f"[REJECT] Proposta rejeitada para CFP {cfp_id}.")

            except json.JSONDecodeError:
                self.agent.logger.error(f"[CFP] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[CFP] Erro ao processar CFP: {e}")
        else:
            await asyncio.sleep(0.1)


class ReceiveRechargeProposalsBehaviour(OneShotBehaviour):
    """Recebe propostas de recarga de todos os LogisticAgents, seleciona a melhor e aceita/rejeita."""
    def __init__(self, cfp_id):
        super().__init__()
        self.cfp_id = cfp_id
        self.proposals = []
        self.timeout = 3 # Tempo para esperar por todas as propostas

    async def run(self):
        self.agent.logger.info(f"[RECHARGE] A aguardar propostas de recarga para CFP {self.cfp_id}...")

        # Espera por todas as propostas até ao timeout
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            # Template para receber PROPOSE_RECHARGE
            
            msg = await self.receive(timeout=1) # Espera 1 segundo de cada vez
            
            if msg:
                try:
                    content = json.loads(msg.body)
                    if content.get("cfp_id") == self.cfp_id:
                        self.proposals.append({
                            "sender": str(msg.sender),
                            "eta_ticks": content.get("eta_ticks"),
                            "resources": content.get("resources")
                        })
                        self.agent.logger.info(f"[RECHARGE] Proposta recebida de {str(msg.sender)}. ETA: {content.get('eta_ticks')}.")
                except json.JSONDecodeError:
                    self.agent.logger.error(f"[RECHARGE] Erro ao descodificar JSON da proposta de recarga: {msg.body}")

            await asyncio.sleep(0.1) # Pequena pausa para não bloquear

        # 1. Selecionar a melhor proposta (menor ETA)
        if not self.proposals:
            self.agent.logger.warning(f"[RECHARGE] Nenhuma proposta de recarga recebida para CFP {self.cfp_id}. A tentar novamente.")
            self.agent.status = "idle" # Volta a idle para o CheckResourcesBehaviour tentar novamente
            return

        best_proposal = min(self.proposals, key=lambda p: p['eta_ticks'])

        self.agent.logger.info(f"[RECHARGE] Melhor proposta selecionada: {best_proposal['sender']} com ETA {best_proposal['eta_ticks']}.")

        # 2. Aceitar a melhor e rejeitar as outras
        for proposal in self.proposals:
            if proposal == best_proposal:
                # Aceitar
                msg = await self.agent.send_accept_proposal(proposal['sender'], self.cfp_id)
                await self.send(msg)
                self.agent.logger.info(f"[RECHARGE] Proposta de {proposal['sender']} ACEITE.")

                # Iniciar o comportamento de execução da recarga
                template = Template()
                template.set_metadata("performative", PERFORMATIVE_DONE)
                execute_recharge_b = ExecuteRechargeBehaviour(best_proposal,self.cfp_id)
                self.agent.add_behaviour(execute_recharge_b, template = template)
                
            else:
                # Rejeitar
                msg = await self.agent.send_reject_proposal(proposal['sender'], self.cfp_id)
                await self.send(msg)
                self.agent.logger.info(f"[RECHARGE] Proposta de {proposal['sender']} REJEITADA.")

class ExecuteRechargeBehaviour(CyclicBehaviour):
    """Aguarda a mensagem DONE do LogisticAgent após a proposta ser aceite e repõe os recursos."""
    def __init__(self, proposal_data,cfp_id):
        super().__init__()
        self.proposal_data = proposal_data
        self.logistic_jid = proposal_data["sender"]
        self.cfp_id = cfp_id
        self.eta_ticks = proposal_data["eta_ticks"]
        self.start_time = time.time()
        self.awaiting_done = True

    async def on_start(self):
        self.agent.logger.info(f"[RECHARGE] A aguardar a chegada do LogisticAgent ({self.logistic_jid}). ETA: {self.eta_ticks} ticks.")
        # Simular o tempo de espera pela chegada do LogisticAgent
        await asyncio.sleep(self.eta_ticks)
        self.agent.logger.info(f"[RECHARGE] Tempo de espera pela chegada do LogisticAgent ({self.logistic_jid}) concluído. A aguardar mensagem DONE.")

    async def run(self):
        if not self.awaiting_done:
            self.kill()
            return

        msg = await self.receive(timeout=5)
        
        if msg:
            performative = msg.get_metadata("performative")
            sender = str(msg.sender)
            
            if performative == PERFORMATIVE_DONE and sender == self.logistic_jid:
                try:
                    content = json.loads(msg.body)
                    if content.get("cfp_id") == self.cfp_id:
                        self.agent.logger.info(f"[RECHARGE] Mensagem DONE recebida de {self.logistic_jid}. Recarga concluída.")
                        
                        # Repor Recursos com base nos detalhes da mensagem DONE
                        details = content.get("details", {})
                        fuel_replenished = 0
                        seeds_replenished = {}
                        
                        resource_type = details.get("resource_type")
                        amount_delivered = details.get("amount_delivered", 0)
                        
                        if resource_type == "fuel":
                            fuel_replenished = amount_delivered
                        elif resource_type == "seeds":
                            # Assumimos que o LogisticAgent envia o tipo de semente e a quantidade
                            seed_type = details.get("seed_type")
                            seeds_replenished[seed_type] = amount_delivered
                        
                        
                        if fuel_replenished > 0:
                            self.agent.fuel_level = min(self.agent.fuel_level + fuel_replenished, 100) 
                            self.agent.logger.info(f"[RECHARGE] Recarga de COMBUSTÍVEL concluída. Reposto: {fuel_replenished}. Nível atual: {self.agent.fuel_level:.2f}.")

                        for seed_type, amount in seeds_replenished.items():
                            self.agent.seeds[seed_type] = min(self.agent.seeds.get(seed_type, 0) + amount,100)
                            self.agent.logger.info(f"[RECHARGE] Recarga de SEMENTES ({seed_type}) concluída. Reposto: {amount}. Nível atual: {self.agent.seeds[seed_type]}.")

                            
                        self.agent.status = "idle"
                        self.agent.logger.info("[RECHARGE] Agente de Colheita de volta ao estado 'idle'.")
                        self.awaiting_done = False
                        self.kill()
                        return
                    else:
                        self.agent.logger.warning(f"[RECHARGE] Mensagem DONE recebida com CFP_ID incorreto: {content.get('cfp_id')}")
                except json.JSONDecodeError:
                    self.agent.logger.error(f"[RECHARGE] Erro ao descodificar JSON do DONE de recarga: {msg.body}")
            else:
                self.agent.logger.warning(f"[RECHARGE] Mensagem inesperada recebida durante a recarga: {performative} de {sender}")

        # Timeout para o DONE (se for muito longo, pode ser um problema)
        await asyncio.sleep(0.1)


class ProposalResponseReceiver(CyclicBehaviour):
    """Recebe e processa a resposta (Accept/Reject) à proposta enviada."""

    async def run(self):
        # Espera por mensagens Accept ou Reject do Logistic Agent
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
                        b = HarvestExecutionBehaviour(proposal_data,cfp_id)
                    elif proposal_data["task_type"] == "plant_application":
                        b = PlantExecutionBehaviour(proposal_data,cfp_id)
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


class HarvestExecutionBehaviour(OneShotBehaviour):
    """Executa a tarefa de colheita após a aceitação da proposta."""
    
    def __init__(self, proposal_data,cfp_id):
        super().__init__()
        self.proposal_data = proposal_data
        self.cfp_id = cfp_id
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
            
            msg_env = make_message(self.agent.env_jid, PERFORMATIVE_ACT, harvest_body)
            msg_env.set_metadata("ontology",ONTOLOGY_FARM_ACTION)
            await self.send(msg_env)
            
            # Esperar pela resposta do Environment Agent
            msg_reply = await self.receive(timeout=10)
            
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
                    msg = await self.agent.send_done(self.logistic_agent, self.cfp_id, details)
                    await self.send(msg)
                    self.agent.logger.info(f"[DONE] Tarefa {self.cfp_id} concluída.")
                    
                else:
                    # Falha na interação com o Environment Agent
                    self.agent.logger.error(f"[HARVEST] Falha na colheita no Environment Agent: {reply_content.get('message')}")
                    msg = await self.agent.send_failure(self.logistic_agent, self.cfp_id)
                    await self.send(msg)
                    self.agent.logger.warning(f"[FAILURE] Tarefa {self.cfp_id} falhou.")
            else:
                # Timeout ou mensagem inesperada do Environment Agent
                self.agent.logger.error("[HARVEST] Timeout ou resposta inesperada do Environment Agent.")
                msg = await self.agent.send_failure(self.logistic_agent, self.cfp_id)
                await self.send(msg)
                self.agent.logger.warning(f"[FAILURE] Tarefa {self.cfp_id} falhou.")
                
        except Exception as e:
            self.agent.logger.exception(f"[HARVEST] Erro inesperado durante a colheita: {e}")
            msg = await self.agent.send_failure(self.logistic_agent, self.cfp_id)
            await self.send(msg)
            self.agent.logger.warning(f"[FAILURE] Tarefa {self.cfp_id} falhou.")
            
        finally:
            self.agent.status = "idle"
            self.agent.logger.info(f"[HARVEST] Tarefa {self.cfp_id} concluída. Agente IDLE.")


class PlantExecutionBehaviour(OneShotBehaviour):
    """Executa a tarefa de plantação após a aceitação da proposta."""
    
    def __init__(self, proposal_data,cfp_id):
        super().__init__()
        self.proposal_data = proposal_data
        self.cfp_id = cfp_id
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
            
            msg_env = make_message(self.agent.env_jid, PERFORMATIVE_ACT, plant_body)
            msg_env.set_metadata("ontology",ONTOLOGY_FARM_ACTION)
            await self.send(msg_env)
            
            # Esperar pela resposta do Environment Agent
            msg_reply = await self.receive(timeout=10)
            
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
                    msg = await self.agent.send_done(self.logistic_agent, self.cfp_id, details)
                    await self.send(msg)
                    self.agent.logger.info(f"[DONE] Tarefa {self.cfp_id} concluída.")
                    
                else:
                    # Falha na interação com o Environment Agent
                    self.agent.logger.error(f"[PLANT] Falha na plantação no Environment Agent: {reply_content.get('message')}")
                    msg = await self.agent.send_failure(self.logistic_agent, self.cfp_id)
                    await self.send(msg)
                    self.agent.logger.warning(f"[FAILURE] Tarefa {self.cfp_id} falhou.")
            else:
                # Timeout ou mensagem inesperada do Environment Agent
                self.agent.logger.error("[PLANT] Timeout ou resposta inesperada do Environment Agent.")
                msg = await self.agent.send_failure(self.logistic_agent, self.cfp_id)
                await self.send(msg)
                self.agent.logger.warning(f"[FAILURE] Tarefa {self.cfp_id} falhou.")
                
        except Exception as e:
            self.agent.logger.exception(f"[PLANT] Erro inesperado durante a plantação: {e}")
            msg = await self.agent.send_failure(self.logistic_agent, self.cfp_id)
            await self.send(msg)
            self.agent.logger.warning(f"[FAILURE] Tarefa {self.cfp_id} falhou.")
        finally:
            self.agent.status = "idle"
            self.agent.logger.info(f"[PLANT] Tarefa {self.cfp_id} concluída. Agente IDLE.")


# =====================
#   AGENTE
# =====================

class HarvesterAgent(Agent):
    
    async def send_cfp_recharge_to_all(self, low_fuel=False, low_seeds=False, seed_type=None, required_resources=None):
        """Função auxiliar para enviar CFP de recarga a todos os agentes logísticos."""
        
        cfp_id = f"cfp_recharge_{time.time()}"
        
        if low_fuel:
            task_type = "fuel"
            required_resources = 100 - self.fuel_level
        elif low_seeds:
            task_type = "seeds"
            # required_resources já deve vir preenchido
        else:
            self.logger.error("Chamada inválida a send_cfp_recharge_to_all.")
            return None, None

        body = {
            "sender_id": str(self.jid),
            "receiver_id": "all", # O destinatário será preenchido no comportamento
            "cfp_id": cfp_id,
            "task_type": task_type, 
            "required_resources": required_resources,
            "position": self.pos_initial,
            "seed_type": seed_type,
            "priority": "Urgent"
        }
        
        return cfp_id, body
    def __init__(self, jid, password, row, col, env_jid, log_jid,sto_jid):
        super().__init__(jid, password)
        
        # Configuração de Logging
        logger = logging.getLogger(f"[HAR] {jid}")
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
            0: 100, # 0: Tomate 
            1: 100, # 1: Pimento
            2: 100, # 2: Trigo
            3: 100, # 3: Couve
            4: 100, # 4: Alface
            5: 100  # 5: Cenoura
        }
        self.fuel_level = 100  # Nível inicial de combustível
        self.status = "idle"  # harvesting, planting, refueling, idle, delivering_harvest
        self.env_jid = env_jid
        self.log_jids = log_jid
        self.sto_jid = sto_jid
        
        # Estrutura para armazenar propostas de reabastecimento recebidas
        self.recharge_proposals = {}

        # Estrutura para armazenar propostas recebidas (por cfp_id)
        self.awaiting_proposals = {}
        
    # =====================
    # MÉTODOS DE COMUNICAÇÃO
    # =====================

    async def stop(self):
        self.add_behaviour(HarvestYieldBehaviour(period=15,stop_beha=1))
        self.logger.info(f"{self.jid} guardou o resto da colheita no agente storage")
        await super().stop()
    
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
        return msg

    async def send_reject_proposal(self, to, cfp_id):
        """Envia uma rejeição de proposta ao Logistic Agent."""
        body = {
            "sender_id": str(self.jid),
            "receiver_id": str(to),
            "cfp_id": cfp_id,
            "decision": "reject"
        }
        msg = make_message(to, PERFORMATIVE_REJECT_PROPOSAL, body)
        return msg

    async def send_accept_proposal(self, to, cfp_id):
        """Envia uma aceitação de proposta ao Logistic Agent (usado para reabastecimento)."""
        body = {
            "sender_id": str(self.jid),
            "receiver_id": str(to),
            "cfp_id": cfp_id,
            "decision": "accept"
        }
        msg = make_message(to, PERFORMATIVE_ACCEPT_PROPOSAL, body)
        return msg

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
        return msg
    

    async def send_failure(self, to, cfp_id):
        """Envia mensagem de falha de tarefa ao Logistic Agent."""
        body = {
            "sender_id": str(self.jid),
            "receiver_id": str(to),
            "cfp_id": cfp_id,
            "status": "failed"
        }
        msg = make_message(to, PERFORMATIVE_FAILURE, body)
        return msg

    async def send_inform_harvest(self, to, amount_type_list):
        """Envia uma mensagem inform_harvest para o agente storage."""
        body = {
            "sender_id": str(self.jid),
            "receiver_id": str(to),
            "inform_id": f"inform_harvest_{time.time()}",
            "amount_type": amount_type_list,
            "checked_at": time.time()
        }
        msg = make_message(to, PERFORMATIVE_INFORM_HARVEST, body)
        return msg
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
        template_task_accept = Template()
        template_task_accept.set_metadata("performative", PERFORMATIVE_ACCEPT_PROPOSAL)
        self.add_behaviour(ProposalResponseReceiver(), template=template_task_accept)

        template_task_reject = Template()
        template_task_reject.set_metadata("performative", PERFORMATIVE_REJECT_PROPOSAL)
        self.add_behaviour(ProposalResponseReceiver(), template=template_task_reject)

        # 4. Comportamento para verificar o rendimento da colheita
        self.add_behaviour(HarvestYieldBehaviour(period=15))

        # 5. Comportamento para receber confirmações de entrega da colheita
        template_inform_received = Template()
        template_inform_received.set_metadata("performative", PERFORMATIVE_INFORM_RECEIVED)
        self.add_behaviour(InformReceivedReceiver(), template=template_inform_received)
