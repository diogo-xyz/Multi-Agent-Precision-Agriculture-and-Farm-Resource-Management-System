import asyncio
import json
import logging
import random
import time
from math import ceil

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.template import Template
from agents.message import make_message


# Constantes
PERFORMATIVE_CFP_RECHARGE = "cfp_recharge"
PERFORMATIVE_PROPOSE_RECHARGE = "propose_recharge"
PERFORMATIVE_INFORM_HARVEST = "inform_harvest"
PERFORMATIVE_INFORM_RECEIVED = "inform_received"
PERFORMATIVE_INFORM_CROP = "inform_crop"
PERFORMATIVE_ACCEPT_PROPOSAL = "accept-proposal"
PERFORMATIVE_REJECT_PROPOSAL = "reject-proposal"
PERFORMATIVE_DONE = "Done"
ONTOLOGY_FARM_ACTION = "farm_action"

MAX_CAPACITY = 1000
# =====================
#   FUNÇÕES AUXILIARES
# =====================

def calculate_distance(pos1, pos2):
    """Calcula a distância de Manhattan entre duas posições (row, col)."""
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

def calculate_eta(distance):
    """Calcula o tempo estimado de chegada (ETA) em segundos.
    Assumindo uma velocidade de 1 unidade/segundo.
    O tempo é de ida e volta (2 * distance).
    """
    # 1 unidade de distância = 1 segundo de viagem
    # Tempo total = 2 * distância (ida e volta)
    return ceil(2 * distance)


# =====================
#   BEHAVIOURS
# =====================

class AutoRechargeBehaviour(CyclicBehaviour):
    """Recarrega automaticamente os recursos (água, combustível, etc.) quando o agente está ocioso."""

    async def run(self):
        # Espera um período para o próximo ciclo de recarga
        await asyncio.sleep(5) # Recarrega a cada 5 segundos (ajustado conforme o pedido)

        if self.agent.status == "idle":
            
            # Recursos que não são sementes
            resources_to_recharge = ["water", "fertilizer", "battery", "pesticide", "fuel"]
            recharge_amount = 10 # Valor fixo de recarga (conforme o pedido)
            
            # 1. Recarregar recursos não-sementes
            for resource in resources_to_recharge:
                storage_attr = f"{resource}_storage"
                current_storage = getattr(self.agent, storage_attr)
                
                if current_storage < MAX_CAPACITY:
                    new_storage = min(MAX_CAPACITY, current_storage + recharge_amount)
                    setattr(self.agent, storage_attr, new_storage)
                    self.agent.logger.info(f"[AUTO_RECHARGE] Recarregado {resource}. Novo stock: {new_storage}/{MAX_CAPACITY}")
            
            # 2. Recarregar sementes (que é um dicionário)
            seed_storage = self.agent.seed_storage
            for seed_type, current_amount in seed_storage.items():
                # Assumindo que a capacidade máxima de sementes é a mesma MAX_CAPACITY
                if current_amount < MAX_CAPACITY:
                    new_amount = min(MAX_CAPACITY, current_amount + recharge_amount)
                    seed_storage[seed_type] = new_amount
                    self.agent.logger.info(f"[AUTO_RECHARGE] Recarregado semente {seed_type}. Novo stock: {new_amount}/{MAX_CAPACITY}")
                
        else:
            self.agent.logger.debug(f"[AUTO_RECHARGE] Agente ocupado ({self.agent.status}). Recarga adiada.")
                



class CFPRechargeReceiver(CyclicBehaviour):
    """Recebe e processa mensagens CFP (Call For Proposal) de reabastecimento."""

    async def run(self):
        msg = await self.receive(timeout=5)

        if msg:
            try:
                content = json.loads(msg.body)
                cfp_id = content.get("cfp_id")
                task_type = content.get("task_type")
                required_resources = content.get("required_resources")
                position = tuple(content.get("position"))
                seed_type = content.get("seed_type")
                sender_jid = str(msg.sender)

                self.agent.logger.info(f"[CFP_RECHARGE] Recebido CFP {cfp_id} para {task_type} de {sender_jid} em {position}.")
                # 1. Verificar se o agente está ocupado
                if self.agent.status != "idle":
                    self.agent.logger.info(f"[CFP_RECHARGE] Agente ocupado ({self.agent.status}). Rejeitando proposta.")
                    msg = await self.agent.send_reject_proposal(sender_jid, cfp_id)
                    await self.send(msg)
                    return

                # 2. Verificar se tem recursos suficientes
                has_resources = False
                resource_amount = 0
                if task_type == "seeds":
                    if seed_type is not None and self.agent.seed_storage.get(seed_type, 0) > 0:
                        # O agente pode reabastecer uma percentagem do que tem
                        available_seed = self.agent.seed_storage.get(seed_type, 0)
                    
                        if available_seed >= required_resources:
                            resource_amount = required_resources
                            has_resources = True
                
                elif task_type in ["water", "fertilizer", "battery", "pesticide", "fuel"]:
                    storage_attr = f"{task_type}_storage"
                    current_storage = getattr(self.agent, storage_attr, 0)
                    if current_storage >= required_resources:
                            resource_amount = required_resources
                            has_resources = True
                
                if not has_resources:
                    self.agent.logger.warning(f"[CFP_RECHARGE] Recursos insuficientes para {task_type} (Recursos disponíveis: {getattr(self.agent, f'{task_type}_storage', 0)}). Rejeitando.")
                    msg = await self.agent.send_reject_proposal(sender_jid, cfp_id)
                    await self.send(msg)
                    return

                # 3. Calcular ETA
                distance = calculate_distance(self.agent.position, position)
                eta_ticks = calculate_eta(distance)
                # 4. Enviar Proposta
                self.agent.pending_recharge_proposals[cfp_id] = {
                    "position": position,
                    "task_type": task_type,
                    "seed_type": seed_type,
                    "resource_amount": resource_amount,
                    "eta_ticks": eta_ticks,
                    "cfp_id": cfp_id
                }
                msg = await self.agent.send_propose_recharge(sender_jid, cfp_id, eta_ticks, resource_amount)
                await self.send(msg)
                self.agent.logger.info(f"[CFP_RECHARGE] Proposta enviada para {sender_jid}. ETA: {eta_ticks}s, Recursos: {resource_amount}.")
        
            except json.JSONDecodeError:
                self.agent.logger.error(f"[CFP_RECHARGE] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[CFP_RECHARGE] Erro ao processar CFP: {e}")


class AcceptRejectRechargeReceiver(CyclicBehaviour):
    """Recebe a aceitação de uma proposta de reabastecimento e inicia a tarefa."""

    async def run(self):
        msg = await self.receive(timeout=5)

        if msg:
            try:
                content = json.loads(msg.body)
                cfp_id = content.get("cfp_id")
                sender_jid = str(msg.sender)

                if cfp_id in self.agent.pending_recharge_proposals:
                    if msg.metadata["performative"] == PERFORMATIVE_REJECT_PROPOSAL:
                        self.agent.logger.info(f"[REJECT_RECHARGE] Proposta {cfp_id} rejeitada por {sender_jid}.")
                        # Remover a proposta pendente
                        if cfp_id in self.agent.pending_recharge_proposals:
                            del self.agent.pending_recharge_proposals[cfp_id]
                        return
                    proposal = self.agent.pending_recharge_proposals.pop(cfp_id)
                    self.agent.logger.info(f"[ACCEPT_RECHARGE] Proposta {cfp_id} aceite por {sender_jid}. A iniciar reabastecimento.")
                    
                    # Iniciar o comportamento de reabastecimento
                    recharge_task = RechargeTaskBehaviour(sender_jid, proposal)
                    self.agent.add_behaviour(recharge_task)
                    self.agent.status = "handling_task"
                else:
                    self.agent.logger.warning(f"[ACCEPT_RECHARGE] Recebido ACCEPT para CFP {cfp_id} desconhecido.")

            except json.JSONDecodeError:
                self.agent.logger.error(f"[ACCEPT_RECHARGE] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[ACCEPT_RECHARGE] Erro ao processar ACCEPT: {e}")


class RechargeTaskBehaviour(OneShotBehaviour):
    """Simula a viagem, entrega os recursos e retorna à base."""

    def __init__(self, receiver_jid, proposal):
        super().__init__()
        self.receiver_jid = receiver_jid
        self.proposal = proposal
        self.target_pos = proposal["position"]
        self.eta_ticks = proposal["eta_ticks"]
        self.task_type = proposal["task_type"]
        self.resource_amount = proposal["resource_amount"]
        self.seed_type = proposal["seed_type"]
        self.cfp_id = proposal["cfp_id"]

    async def run(self):
        self.agent.logger.info(f"[RECHARGE_TASK] A mover-se para {self.target_pos} para reabastecer {self.receiver_jid}.")
        
        # 1. Simular a viagem (ida e volta)
        # O ETA já é o tempo total de ida e volta
        await asyncio.sleep(self.eta_ticks)

        self.agent.logger.info(f"[RECHARGE_TASK] Chegou a {self.target_pos}. A entregar {self.resource_amount} a {self.receiver_jid}")

        # 2. Atualizar o armazenamento do Logistic Agent
        if self.task_type == "seeds":
            self.agent.seed_storage[self.seed_type] -= self.resource_amount
        else:
            storage_attr = f"{self.task_type}_storage"
            current_storage = getattr(self.agent, storage_attr)
            setattr(self.agent, storage_attr, current_storage - self.resource_amount)

        # 3. Enviar mensagem DONE para o agente reabastecido
        details = {
            "resource_type": self.task_type,
            "amount_delivered": self.resource_amount,
            "seed_type": self.seed_type if self.task_type == "seeds" else None
        }
        msg = await self.agent.send_done(self.receiver_jid, self.cfp_id, details)
        await self.send(msg)
        self.agent.logger.info(f"[RECHARGE_TASK] DONE enviado para {self.receiver_jid}.")

        # 4. Retornar à base (já incluído no ETA, mas para clareza no log)
        self.agent.logger.info(f"[RECHARGE_TASK] A regressar à base {self.agent.position}.")
        # O tempo de retorno já foi consumido no sleep inicial
        
        # 5. Voltar ao estado idle
        self.agent.status = "idle"
        self.agent.logger.info("[STATUS] Agente voltou ao estado 'idle'.")


class InformHarvestReceiver(CyclicBehaviour):
    """Recebe a colheita do Harvester Agent e atualiza o yield_storage."""

    async def run(self):

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
                        # Aumenta o yield_storage, arredondando para baixo (parte inteira)
                        amount_int = int(amount)
                        self.agent.yield_storage[seed_type] += amount
                        self.agent.seed_storage[seed_type] += amount_int
                        
                        details_received.append({"seed_type": seed_type, "amount": amount_int})
                        self.agent.logger.info(f"[INFORM_HARVEST] Yield de semente {seed_type} atualizado. Adicionado: {amount_int}. Total: {self.agent.yield_storage[seed_type]}.")

                print(self.agent.yield_storage)
                print(self.agent.seed_storage)
                # Enviar confirmação `inform_received`
                if details_received:
                    msg = await self.agent.send_inform_received(sender_jid, details_received)
                    await self.send(msg)
                    self.agent.logger.info(f"[INFORM_HARVEST] Confirmação 'inform_received' enviada para {sender_jid}.")

            except json.JSONDecodeError:
                self.agent.logger.error(f"[INFORM_HARVEST] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[INFORM_HARVEST] Erro ao processar INFORM_HARVEST: {e}")


class InformCropReceiver(CyclicBehaviour):
    """Recebe pedidos de plantio/colheita do Drone Agent e gere as tarefas."""

    async def run(self):
        msg = await self.receive(timeout=5)
        
        if msg:
            try:
                content = json.loads(msg.body)
                zone = tuple(content.get("zone"))
                crop_type = content.get("crop_type")
                state = content.get("state")
                sender_jid = str(msg.sender)
                self.agent.logger.info(f"[INFORM_CROP] Recebido inform de {sender_jid} para zona {zone}. Estado: {state}.")

                # 1. Verificar se a zona já está a ser tratada
                if zone in self.agent.pending_crop_tasks:
                    self.agent.logger.info(f"[INFORM_CROP] Zona {zone} já tem tarefa pendente. Ignorando pedido repetido.")
                    return

                # 2. Adicionar a zona à lista de tarefas pendentes
                self.agent.pending_crop_tasks[zone] = {"crop_type": crop_type, "state": state, "harvester_jid": None}
                
                # 3. Decidir a ação e iniciar o processo de CFP
                if state == 0: # not planted -> Plantar
                    task_type = "plant_application"
                    # Escolher semente aleatoriamente
                    seed_type = random.choice(list(self.agent.seed_storage.keys()))
                    self.agent.logger.info(f"[INFORM_CROP] Ação: Plantar semente {seed_type} em {zone}.")
                    
                    # Iniciar CFP para Harvester Agents
                    cfp_task = CFPTaskInitiator(zone, task_type, seed_type)
                    self.agent.add_behaviour(cfp_task)

                elif state == 4: # Ready for harvesting -> Colher
                    task_type = "harvest_application"
                    self.agent.logger.info(f"[INFORM_CROP] Ação: Colher em {zone}.")
                    
                    # Iniciar CFP para Harvester Agents
                    cfp_task = CFPTaskInitiator(zone, task_type, crop_type)
                    self.agent.add_behaviour(cfp_task)
                
                else:
                    self.agent.logger.warning(f"[INFORM_CROP] Estado desconhecido ({state}). Ignorando.")
                    del self.agent.pending_crop_tasks[zone] # Remover se for um estado inválido

            except json.JSONDecodeError:
                self.agent.logger.error(f"[INFORM_CROP] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[INFORM_CROP] Erro ao processar INFORM_CROP: {e}")


class CFPTaskInitiator(OneShotBehaviour):
    """Inicia o processo de CFP para uma tarefa de plantio ou colheita."""

    def __init__(self, zone, task_type, seed_or_crop_type):
        super().__init__()
        self.zone = zone
        self.task_type = task_type
        self.seed_or_crop_type = seed_or_crop_type
        self.cfp_id = f"cfp_task_{time.time()}"

    async def run(self):
        self.agent.logger.info(f"[CFP_INIT] A iniciar CFP {self.cfp_id} para {self.task_type} em {self.zone}.")
        
        # Recursos necessários (simplificado para o CFP inicial)
        required_resources = []
        if self.task_type == "plant_application":
            required_resources.append({"type": "seed", "amount": 5}) # Exemplo: 5 unidades de semente
        elif self.task_type == "harvest_application":
            required_resources.append({"type": "storage", "amount": 1}) # Exemplo: 1 unidade de armazenamento

        # Enviar CFP para todos os Harvester Agents
        for harv_jid in self.agent.harv_jid :
            msg = make_message(
                to=harv_jid,
                performative="cfp_task",
                body_dict={
                    "cfp_id": self.cfp_id,
                    "task_type": self.task_type,
                    "seed_type": self.seed_or_crop_type if self.task_type == "plant_application" else None,
                    "zone": list(self.zone),
                    "required_resources": required_resources,
                    "priority": "Medium"
                },
                protocol=ONTOLOGY_FARM_ACTION
            )
            await self.send(msg)
            self.agent.logger.info(f"[CFP_INIT] CFP enviado para {harv_jid}.")

        # Esperar pelas propostas
        self.agent.add_behaviour(CFPTaskReceiver(self.cfp_id, self.zone, self.task_type, self.seed_or_crop_type), template=Template(metadata={"performative": "propose_task"}))


class CFPTaskReceiver(CyclicBehaviour):
    """Recebe e avalia as propostas dos Harvester Agents."""

    def __init__(self, cfp_id, zone, task_type, seed_or_crop_type):
        super().__init__()
        self.cfp_id = cfp_id
        self.zone = zone
        self.task_type = task_type
        self.seed_or_crop_type = seed_or_crop_type
        self.proposals = {}
        self.timeout = time.time() + 20 # Tempo limite para receber propostas

    async def run(self):
        # 1. Receber propostas
        msg = await self.receive(timeout=1)

        if msg:
            try:
                content = json.loads(msg.body)
                cfp_id = content.get("cfp_id")
                eta_ticks = content.get("eta_ticks")
                fuel_cost = content.get("battery_lost") # Usando battery_lost como fuel_cost
                sender_jid = str(msg.sender)

                if cfp_id == self.cfp_id:
                    self.agent.logger.info(f"[CFP_TASK_RECV] Proposta recebida de {sender_jid}. ETA: {eta_ticks}, Custo: {fuel_cost}.")
                    self.proposals[sender_jid] = {"eta": eta_ticks, "cost": fuel_cost}
            
            except json.JSONDecodeError:
                self.agent.logger.error(f"[CFP_TASK_RECV] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[CFP_TASK_RECV] Erro ao processar PROPOSE_TASK: {e}")

        # 2. Avaliar propostas após o timeout ou se todas as propostas foram recebidas (simplificado, apenas por timeout)
        if time.time() > self.timeout:
            self.agent.logger.info(f"[CFP_TASK_RECV] Tempo limite atingido para CFP {self.cfp_id}. A avaliar propostas.")
            
            if not self.proposals:
                self.agent.logger.warning(f"[CFP_TASK_RECV] Nenhuma proposta recebida para CFP {self.cfp_id}. Tarefa falhada.")
                # Remover a tarefa pendente
                if self.zone in self.agent.pending_crop_tasks:
                    del self.agent.pending_crop_tasks[self.zone]
                self.kill()
                return

            # Critério de seleção: Menor ETA
            best_harvester = min(self.proposals.items(), key=lambda item: item[1]["eta"])
            best_jid = best_harvester[0]
            
            self.agent.logger.info(f"[CFP_TASK_RECV] Harvester selecionado: {best_jid} com ETA {best_harvester[1]['eta']}.")

            # 3. Enviar ACCEPT para o melhor e REJECT para os outros
            for jid in self.proposals:
                if jid == best_jid:
                    msg = await self.agent.send_accept_proposal(jid, self.cfp_id)
                    await self.send(msg)
                    # Atualizar a tarefa pendente com o Harvester selecionado
                    if self.zone in self.agent.pending_crop_tasks:
                        self.agent.pending_crop_tasks[self.zone]["harvester_jid"] = jid
                else:
                    msg = await self.agent.send_reject_proposal(jid, self.cfp_id)
                    await self.send(msg)
            
            # 4. Adicionar o comportamento para receber o DONE
            self.agent.add_behaviour(TaskDoneReceiver(self.cfp_id, self.zone), template=Template(metadata={"performative": "Done"}))
            
            self.kill()


class TaskDoneReceiver(CyclicBehaviour):
    """Recebe a mensagem DONE do Harvester Agent após a conclusão da tarefa."""

    def __init__(self, cfp_id, zone):
        super().__init__()
        self.cfp_id = cfp_id
        self.zone = zone

    async def run(self):
        template = Template()
        template.set_metadata("performative", PERFORMATIVE_DONE)
        msg = await self.receive(timeout=5)

        if msg:
            try:
                content = json.loads(msg.body)
                cfp_id = content.get("cfp_id")
                sender_jid = str(msg.sender)

                if cfp_id == self.cfp_id:
                    self.agent.logger.info(f"[TASK_DONE] Recebido DONE de {sender_jid} para CFP {cfp_id} na zona {self.zone}.")
                    
                    # Remover a tarefa da lista de pendentes
                    if self.zone in self.agent.pending_crop_tasks:
                        del self.agent.pending_crop_tasks[self.zone]
                        self.agent.logger.info(f"[TASK_DONE] Tarefa da zona {self.zone} removida da lista de pendentes.")
                    
                    self.kill()

            except json.JSONDecodeError:
                self.agent.logger.error(f"[TASK_DONE] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[TASK_DONE] Erro ao processar DONE: {e}")


# =====================
#   AGENT
# =====================

class LogisticsAgent(Agent):

    def __init__(self, jid, password, harv_jid, row, col):
        super().__init__(jid, password)

        self.logger = logging.getLogger(f"[LOG] {jid}")
        self.logger.setLevel(logging.INFO)
        
        self.harv_jid = harv_jid
        self.position = (row, col)
        self.status = "idle"  # idle, moving, handling_task

        # Armazenamento de Recursos
        self.water_storage = 1000  # initial water storage
        self.fertilizer_storage = 1000  # initial fertilizer storage
        self.battery_storage = 1000  # initial battery storage
        self.pesticide_storage = 1000  # initial pesticide storage
        self.fuel_storage = 1000  # initial fuel storage

        self.seed_storage =  {
            0: 1000, # 0: Tomate 
            1: 1000, # 1: Pimento
            2: 1000, # 2: Trigo
            3: 1000, # 3: Couve
            4: 1000, # 4: Alface
            5: 1000  # 5: Cenoura
        }

        self.yield_storage = {
            0: 0, # 0: Tomate
            1: 0, # 1: Pimento
            2: 0, # 2: Trigo
            3: 0, # 3: Couve
            4: 0, # 4: Alface
            5: 0  # 5: Cenoura
        }
        
        # Estado de gestão de tarefas
        self.pending_recharge_proposals = {} # {cfp_id: proposal_details}
        self.pending_crop_tasks = {} # {zone: {"crop_type": ..., "state": ..., "harvester_jid": ...}}


    async def setup(self):
        self.logger.info("LogisticsAgent started")
        
        # Adicionar Behaviours

        self.add_behaviour(AutoRechargeBehaviour())

        template = Template()
        template.set_metadata("performative", PERFORMATIVE_CFP_RECHARGE)
        self.add_behaviour(CFPRechargeReceiver(),template=template)

        template_accept = Template()
        template_accept.set_metadata("performative", PERFORMATIVE_ACCEPT_PROPOSAL)

        template_reject = Template()
        template_reject.set_metadata("performative", PERFORMATIVE_REJECT_PROPOSAL)    

        self.add_behaviour(AcceptRejectRechargeReceiver(),template=template_accept)
        self.add_behaviour(AcceptRejectRechargeReceiver(),template=template_reject)

        template = Template()
        template.set_metadata("performative", PERFORMATIVE_INFORM_HARVEST)

        self.add_behaviour(InformHarvestReceiver(),template=template)

        template = Template()
        template.set_metadata("performative", PERFORMATIVE_INFORM_CROP)
        self.add_behaviour(InformCropReceiver(), template=template)


    # =====================
    #   FUNÇÕES DE ENVIO DE MENSAGENS
    # =====================

    async def send_propose_recharge(self, to, cfp_id, eta_ticks, resources):
        msg = make_message(
            to=to,
            performative=PERFORMATIVE_PROPOSE_RECHARGE,
            body_dict={
                "cfp_id": cfp_id,
                "eta_ticks": eta_ticks,
                "resources": resources,
                "priority": "High"
            }
        )
        
        
        # Armazenar a proposta pendente
        proposal_details = {
            "position": self.pending_recharge_proposals.get(cfp_id, {}).get("position"), # Será preenchido no CFPRechargeReceiver
            "task_type": self.pending_recharge_proposals.get(cfp_id, {}).get("task_type"),
            "seed_type": self.pending_recharge_proposals.get(cfp_id, {}).get("seed_type"),
            "resource_amount": resources,
            "eta_ticks": eta_ticks,
            "cfp_id": cfp_id
        }
        self.pending_recharge_proposals[cfp_id] = proposal_details
        
        return msg

    async def send_accept_proposal(self, to, cfp_id):
        msg = make_message(
            to=to,
            performative=PERFORMATIVE_ACCEPT_PROPOSAL,
            body_dict={
                "cfp_id": cfp_id,
                "decision": "accept"
            }
        )
        return msg


    async def send_reject_proposal(self, to, cfp_id):
        msg = make_message(
            to=to,
            performative=PERFORMATIVE_REJECT_PROPOSAL,
            body_dict={
                "cfp_id": cfp_id,
                "decision": "reject"
            }
        )
        return msg


    async def send_done(self, to, cfp_id, details):
        msg = make_message(
            to=to,
            performative=PERFORMATIVE_DONE,
            body_dict={
                "cfp_id": cfp_id,
                "status": "done",
                "details": details
            }
        )
        return msg


    async def send_inform_received(self, to, details):
        msg = make_message(
            to=to,
            performative=PERFORMATIVE_INFORM_RECEIVED,
            body_dict={
                "inform_id": f"inform_received_{time.time()}",
                "details": details
            }
        )
        return msg