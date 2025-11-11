from spade.agent import Agent
from spade.behaviour import PeriodicBehaviour, OneShotBehaviour, CyclicBehaviour
from spade.template import Template
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

# =================================================================================
#   Funções Auxiliares
# =================================================================================

def calculate_manhattan_distance(pos1, pos2):
    """Calcula a distância de Manhattan entre duas posições (row, col)."""
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

def calculate_energy_cost(distance):
    """Calcula o custo de energia: 1 de energia por cada 2 unidades de distância."""
    return distance // 2

# =================================================================================
#   Comportamentos
# =================================================================================


class CheckRechargeBehaviour(PeriodicBehaviour):
    """Verifica periodicamente se é necessário recarregar água ou energia."""
    async def run(self):
        # Se o agente estiver ocupado ou já a carregar, não faz nada
        if self.agent.status != "idle":
            return

        low_fertilize = self.agent.fertilize_capacity < 0.15 * self.agent.fertilize_capacity_max
        low_energy = self.agent.energy < 15 # 15% de 100 é 15

        if low_fertilize:
            self.agent.logger.info(f"[FERT] Fertilizante baixo: {self.agent.fertilize_capacity}L. A solicitar recarga de fertilizante...")
            self.agent.status = "charging"
            
            # Envia CFP para todos os Logistics e inicia o comportamento de recolha de propostas
            cfp_id, body = await self.agent.send_cfp_recharge_to_all(low_fertilize=True, low_energy=False)

            for to_jid in self.agent.log_jid:
                msg = make_message(to_jid, PERFORMATIVE_CFP_RECHARGE, body)
                await self.send(msg)
                self.agent.logger.info(f"CFP_RECHARGE ({cfp_id}) enviado para {to_jid} a pedir {body["task_type"]} ({body["required_resources"]}).")

            # Adiciona o comportamento para receber as propostas
            receive_proposals_b = ReceiveRechargeProposalsBehaviour(cfp_id)
            self.agent.add_behaviour(receive_proposals_b)
            return # Sai para processar apenas uma recarga de cada vez

        if low_energy:
            self.agent.logger.info(f"[FERT] Energia baixa: {self.agent.energy}. A solicitar recarga de bateria...")
            self.agent.status = "charging"
            
            # Envia CFP para todos os Logistics e inicia o comportamento de recolha de propostas
            cfp_id, body = await self.agent.send_cfp_recharge_to_all(low_fertilize=False, low_energy=True)

            for to_jid in self.agent.log_jid:
                msg = make_message(to_jid, PERFORMATIVE_CFP_RECHARGE, body)
                await self.send(msg)
                self.agent.logger.info(f"CFP_RECHARGE ({cfp_id}) enviado para {to_jid} a pedir {body["task_type"]} ({body["required_resources"]}).")

            # Adiciona o comportamento para receber as propostas
            receive_proposals_b = ReceiveRechargeProposalsBehaviour(cfp_id)
            self.agent.add_behaviour(receive_proposals_b)
            return # Sai para processar apenas uma recarga de cada vez


class ReceiveCFPTaskBehaviour(CyclicBehaviour):
    """Recebe e processa mensagens CFP (Call For Proposal) para fertilização."""
    async def run(self):
        # Template para receber CFP de qualquer SoilAgent
        template = Template()
        template.set_metadata("performative", PERFORMATIVE_CFP_TASK)
        
        msg = await self.receive(timeout=5)
        if msg:
            try:
                content = json.loads(msg.body)
                sender_jid = str(msg.sender)
                cfp_id = content.get("cfp_id")
                zone = content.get("zone")
                required_resources = content.get("required_resources", [])

                # Apenas processa se for uma tarefa de fertilização
                if content.get("task_type") != "fertilize_application":
                    self.agent.logger.warning(f"[FERT] CFP recebido não é de fertilização: {content.get('task_type')}")
                    return

                # Encontrar a quantidade de fertilizante necessária
                fertilizer_needed = 0
                for res in required_resources:
                    if res.get("type") == "fertilizer":
                        fertilizer_needed = res.get("amount")
                        break

                if fertilizer_needed == 0:
                    self.agent.logger.warning(f"[FERT] CFP {cfp_id} não especifica fertilizante necessário. A rejeitar.")
                    msg = await self.agent.send_reject_proposal(sender_jid, cfp_id)
                    await self.send(msg)
                    return

                # 1. Calcular Distância e Custo
                target_pos = tuple(zone)
                current_pos = self.agent.position
                distance = calculate_manhattan_distance(current_pos, target_pos)
                
                # O agente tem de ir e voltar
                total_distance = distance * 2 
                energy_cost = calculate_energy_cost(total_distance)
                
                # Tempo estimado (simples: 1 tick por unidade de distância)
                eta_ticks = total_distance 
                
                # 2. Verificar Capacidade e Energia

                # Se o fertilizante necessário for maior que a capacidade atual
                if fertilizer_needed > self.agent.fertilize_capacity:
                    self.agent.logger.info(f"[FERT] CFP {cfp_id} rejeitado: Fertilizante insuficiente ({fertilizer_needed}L necessários, {self.agent.fertilizer_capacity}L disponíveis).")
                    msg = await self.agent.send_reject_proposal(sender_jid, cfp_id)
                    await self.send(msg)
                    return
                
                # Se o custo de energia for maior que a energia atual
                if energy_cost > self.agent.energy:
                    self.agent.logger.info(f"[FERT] CFP {cfp_id} rejeitado: Energia insuficiente ({energy_cost} necessários, {self.agent.energy} disponíveis).")
                    msg = await self.agent.send_reject_proposal(sender_jid, cfp_id)
                    await self.send(msg)
                    return
                
                # 3. Aceitar e Propor
                self.agent.logger.info(f"[FERT] CFP {cfp_id} aceite. A propor tarefa ao {sender_jid}. Custo de energia: {energy_cost}, ETA: {eta_ticks}.")
                
                # Armazenar a proposta para referência futura
                self.agent.awaiting_proposals[cfp_id] = {
                    "sender": sender_jid,
                    "zone": target_pos,
                    "fertilizer_needed": fertilizer_needed,
                    "energy_cost": energy_cost,
                    "eta_ticks": eta_ticks
                }
                
                # Enviar Proposta
                msg = await self.agent.send_propose_task(sender_jid, cfp_id, eta_ticks, energy_cost)
                await self.send(msg)

            except json.JSONDecodeError:
                self.agent.logger.error(f"[FERT] Erro ao descodificar JSON do CFP: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[FERT] Erro ao processar CFP: {e}")
        else:
            # Sem mensagem, espera um pouco
            await asyncio.sleep(0.1)

class ReceiveProposalResponseBehaviour(CyclicBehaviour):
    """Recebe a resposta (Accept/Reject) à proposta enviada."""
    async def run(self):
        # Template para receber Accept ou Reject de qualquer SoilAgent
        template = Template()
        template.set_metadata("performative", PERFORMATIVE_ACCEPT_PROPOSAL)
        template_reject = Template()
        template_reject.set_metadata("performative", PERFORMATIVE_REJECT_PROPOSAL)
        
        # Receber qualquer uma das performatives
        msg = await self.receive(timeout=5)
        if msg:
            performative = msg.get_metadata("performative")
            try:
                content = json.loads(msg.body)
                cfp_id = content.get("cfp_id")
                
                if cfp_id not in self.agent.awaiting_proposals:
                    self.agent.logger.warning(f"[FERT] Resposta recebida para CFP_ID desconhecido: {cfp_id}")
                    return
                
                proposal_data = self.agent.awaiting_proposals.pop(cfp_id)
                
                if performative == PERFORMATIVE_ACCEPT_PROPOSAL:
                    self.agent.logger.info(f"[FERT] Proposta {cfp_id} ACEITE pelo {str(msg.sender)}. A iniciar tarefa de fertilização.")
                    #
                    #  Iniciar o comportamento de execução da tarefa
                    task_exec_b = ExecuteTaskBehaviour(proposal_data,cfp_id)
                    self.agent.add_behaviour(task_exec_b)
                    
                elif performative == PERFORMATIVE_REJECT_PROPOSAL:
                    self.agent.logger.info(f"[FERT] Proposta {cfp_id} REJEITADA pelo {str(msg.sender)}. Motivo: {content.get('details', 'Não especificado')}")
                    # O agente volta ao estado 'idle'
                    self.agent.status = "idle"
                    
            except json.JSONDecodeError:
                self.agent.logger.error(f"[FERT] Erro ao descodificar JSON da resposta: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[FERT] Erro ao processar resposta à proposta: {e}")
        else:
            await asyncio.sleep(0.1)

class ExecuteTaskBehaviour(OneShotBehaviour):
    """Executa a tarefa de fertilização após a proposta ser aceite."""
    def __init__(self, proposal_data,cfp_id):
        super().__init__()
        self.proposal_data = proposal_data
        self.cfp_id = cfp_id

    async def run(self):
        sender_jid = self.proposal_data["sender"]
        cfp_id = self.cfp_id
        target_pos = self.proposal_data["zone"]
        fertilizer_needed = self.proposal_data["fertilizer_needed"]
        energy_cost = self.proposal_data["energy_cost"]
        eta_ticks = self.proposal_data["eta_ticks"]
        
        self.agent.status = "moving"
        self.agent.logger.info(f"[FERT] A mover para {target_pos} para fertilizar. ETA: {eta_ticks} ticks.")
        
        # 1. Simular Viagem de Ida (metade do ETA)
        travel_time = eta_ticks // 2
        await asyncio.sleep(travel_time)
        self.agent.position = target_pos
        self.agent.logger.info(f"[FERT] Chegou a {target_pos}. A iniciar fertilização.")

        # 2. Simular Fertilização e Interagir com EnvironmentAgent
        self.agent.status = "fertilizing"

        # Enviar ACT para o EnvironmentAgent
        env_jid = "environment@localhost" # Assumindo que o JID do EnvironmentAgent é este
        
        act_body = {
            "action": "apply_fertilize",
            "row": target_pos[0],
            "col": target_pos[1],
            "fertilizer": fertilizer_needed
        }
        act_msg = make_message(
            to=env_jid,
            body_dict=act_body,
            performative= "act",
            protocol=None,
            language="json"
        )
        act_msg.set_metadata("ontology", ONTOLOGY_FARM_ACTION)
        
        await self.send(act_msg)
        
        # Esperar pela resposta do EnvironmentAgent (INFORM)
        reply_template = Template()
        reply_template.set_metadata("performative", PERFORMATIVE_INFORM)
        reply_template.set_metadata("ontology", ONTOLOGY_FARM_ACTION)
        
        env_reply = await self.receive(timeout=10)
        if env_reply:
            try:
                reply_content = json.loads(env_reply.body)
                if reply_content.get("status") == "success":
                    self.agent.logger.info(f"[FERT] Fertilização em {target_pos} concluída com sucesso. Mensagem do ENV: {reply_content.get('message')}")
                    
                    # 3. Atualizar estado e simular viagem de volta

                    self.agent.fertilize_capacity -= fertilizer_needed
                    self.agent.energy -= energy_cost

                    self.agent.logger.info(f"[FERT] Fertilizante restante: {self.agent.fertilize_capacity}kg. Energia restante: {self.agent.energy}.")
                    
                    # Simular Viagem de Volta
                    self.agent.logger.info(f"[FERT] A regressar à base. Tempo de viagem: {travel_time} ticks.")
                    await asyncio.sleep(travel_time)
                    self.agent.position = (self.agent.row, self.agent.col) # Volta à posição inicial (base)
                    self.agent.status = "idle"
                    
                    # 4. Enviar Done
                    done_body = {
                        "cfp_id": cfp_id,
                        "status": "done",
                        "seed_type": 0, # Não se aplica a irrigação, mas mantemos o formato
                        "details": {"fertilizer_used": fertilizer_needed, "time_taken": eta_ticks}
                    }
                    done_msg = make_message(sender_jid, PERFORMATIVE_DONE, done_body)
                    await self.send(done_msg)
                    self.agent.logger.info(f"[FERT] Tarefa {cfp_id} concluída e Done enviado para {sender_jid}.")
                    
                else:
                    # Falha na fertilização (EnvironmentAgent reportou erro)
                    self.agent.logger.error(f"[FERT] Falha na fertilização em {target_pos}. Mensagem do ENV: {reply_content.get('message')}")
                    self.agent.status = "idle"
                    msg = await self.agent.send_failure(sender_jid, cfp_id)
                    await self.send(msg)
                    
            except json.JSONDecodeError:
                self.agent.logger.error(f"[FERT] Erro ao descodificar JSON da resposta do EnvironmentAgent: {env_reply.body}")
                self.agent.status = "idle"
                msg = await self.agent.send_failure(sender_jid, cfp_id)
                await self.send(msg)
            
        else:
            # Timeout na resposta do EnvironmentAgent
            self.agent.logger.error(f"[FERT] Timeout ao esperar resposta do EnvironmentAgent para fertilização em {target_pos}.")
            self.agent.status = "idle"
            msg = await self.agent.send_failure(sender_jid, cfp_id)
            await self.send(msg)

class ReceiveRechargeProposalsBehaviour(OneShotBehaviour):
    """Recebe propostas de recarga de todos os LogisticAgents, seleciona a melhor e aceita/rejeita."""
    def __init__(self, cfp_id):
        super().__init__()
        self.cfp_id = cfp_id
        self.proposals = []
        self.timeout = 5 # Tempo para esperar por todas as propostas

    async def run(self):
        self.agent.logger.info(f"[FERT] A aguardar propostas de recarga para CFP {self.cfp_id}...")

        # Espera por todas as propostas até ao timeout
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            # Template para receber PROPOSE_RECHARGE
            template = Template()
            template.set_metadata("performative", PERFORMATIVE_PROPOSE_RECHARGE)
            
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
                        self.agent.logger.info(f"[FERT] Proposta recebida de {str(msg.sender)}. ETA: {content.get('eta_ticks')}.")
                except json.JSONDecodeError:
                    self.agent.logger.error(f"[FERT] Erro ao descodificar JSON da proposta de recarga: {msg.body}")

            await asyncio.sleep(0.1) # Pequena pausa para não bloquear

        # 1. Selecionar a melhor proposta (menor ETA)
        if not self.proposals:
            self.agent.logger.warning(f"[FERT] Nenhuma proposta de recarga recebida para CFP {self.cfp_id}. A tentar novamente.")
            self.agent.status = "idle" # Volta a idle para o CheckRechargeBehaviour tentar novamente
            return

        best_proposal = min(self.proposals, key=lambda p: p['eta_ticks'])

        self.agent.logger.info(f"[FERT] Melhor proposta selecionada: {best_proposal['sender']} com ETA {best_proposal['eta_ticks']}.")

        # 2. Aceitar a melhor e rejeitar as outras
        for proposal in self.proposals:
            if proposal == best_proposal:
                # Aceitar
                msg = await self.agent.send_accept_proposal(proposal['sender'], self.cfp_id)
                await self.send(msg)
                self.agent.logger.info(f"[FERT] Proposta de {proposal['sender']} ACEITE.")

                # Iniciar o comportamento de execução da recarga
                execute_recharge_b = ExecuteRechargeBehaviour(best_proposal,self.cfp_id)
                self.agent.add_behaviour(execute_recharge_b)
                
            else:
                # Rejeitar
                msg = await self.agent.send_reject_proposal(proposal['sender'], self.cfp_id)
                await self.send(msg)
                self.agent.logger.info(f"[FERT] Proposta de {proposal['sender']} REJEITADA.")

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
        self.agent.logger.info(f"[FERT] A aguardar a chegada do LogisticAgent ({self.logistic_jid}). ETA: {self.eta_ticks} ticks.")
        # Simular o tempo de espera pela chegada do LogisticAgent
        await asyncio.sleep(self.eta_ticks)
        self.agent.logger.info(f"[FERT] Tempo de espera pela chegada do LogisticAgent ({self.logistic_jid}) concluído. A aguardar mensagem DONE.")

    async def run(self):
        if not self.awaiting_done:
            self.kill()
            return

        # Template para receber DONE do LogisticAgent
        template = Template()
        template.set_metadata("performative", PERFORMATIVE_DONE)

        msg = await self.receive(timeout=5)
        
        if msg:
            performative = msg.get_metadata("performative")
            sender = str(msg.sender)
            
            if performative == PERFORMATIVE_DONE and sender == self.logistic_jid:
                try:
                    content = json.loads(msg.body)
                    if content.get("cfp_id") == self.cfp_id:
                        self.agent.logger.info(f"[FERT] Mensagem DONE recebida de {self.logistic_jid}. Recarga concluída.")
                        
                        # Repor Recursos com base nos detalhes da mensagem DONE
                        details = content.get("details", {})
                        energy_used = 0
                        fertilizer_replenished = 0
                        # O utilizador forneceu um exemplo com "fertilizer_used" e "time_taken".
                        # Assumindo que "fertilizer_used" é a quantidade de fertilizante recarregada.
                        if (details["resource_type"] == "battery"): energy_used = details.get("amount_delivered", 0) 
                        # Para a bateria, o LogisticAgent deve enviar a quantidade recarregada.
                        # Vamos assumir a chave "energy_used" para consistência.
                        else: fertilizer_replenished = details.get("amount_delivered", 0)
                        
                        if fertilizer_replenished > 0:
                            self.agent.fertilize_capacity = min(self.agent.fertilize_capacity + fertilizer_replenished, self.agent.fertilize_capacity_max)
                            self.agent.logger.info(f"[FERT] Recarga de FERTILIZANTE concluída. Reposto: {fertilizer_replenished}kg. Fertilizante atual: {self.agent.fertilize_capacity}kg.")

                        if energy_used > 0:
                            self.agent.energy = min(self.agent.energy + energy_used, 100)
                            self.agent.logger.info(f"[FERT] Recarga de ENERGIA concluída. Reposto: {energy_used}. Energia atual: {self.agent.energy}.")

                            
                        self.agent.status = "idle"
                        self.agent.logger.info("[FERT] Agente de Fertilização de volta ao estado 'idle'.")
                        self.awaiting_done = False
                        self.kill()
                        return
                    else:
                        self.agent.logger.warning(f"[FERT] Mensagem DONE recebida com CFP_ID incorreto: {content.get('cfp_id')}")
                except json.JSONDecodeError:
                    self.agent.logger.error(f"[FERT] Erro ao descodificar JSON do DONE de recarga: {msg.body}")
            else:
                self.agent.logger.warning(f"[FERT] Mensagem inesperada recebida durante a recarga: {performative} de {sender}")

        # Timeout para o DONE (se for muito longo, pode ser um problema)
        if time.time() - self.start_time > self.eta_ticks + 60: # 60 segundos extra de tolerância
            self.agent.logger.error(f"[FERT] Timeout ao esperar mensagem DONE de recarga de {self.logistic_jid}. Assumindo falha e voltando a 'idle'.")
            self.agent.status = "idle"
            self.awaiting_done = False
            self.kill()


# =================================================================================
#   Agente Principal
# =================================================================================

class FertilizerAgent(Agent):

    def __init__(self,jid,password,log_jid,soil_jid,row,col):
        super().__init__(jid,password)
        
        # Configuração de Logging
        self.logger = logging.getLogger(f"[FERT] {jid}")
        self.logger.setLevel(logging.INFO)

        self.position = (row, col)
        self.row = row
        self.col = col
        self.status = "idle"  # idle, charging, fertilizing, moving
        self.soil_jid = soil_jid
        self.log_jid = log_jid

        self.fertilize = 1
        self.energy = 100.0
        self.fertilize_capacity = 100.0
        self.fertilize_capacity_max = 100.0

        # Estrutura para armazenar propostas enviadas e aguardando resposta (por cfp_id)
        self.awaiting_proposals = {}
        
        # ID para o CFP de recarga (para rastrear a recarga)
        self.recharge_cfp_id = None 

    # =====================
    #   SETUP
    # =====================
    async def setup(self):
        self.logger.info(f"[FERT] FertilizerAgent {self.jid} iniciado.")
        
        # 1. Comportamento para verificar necessidade de recarga
        check_recharge_b = CheckRechargeBehaviour(period=10) # Verifica a cada 10 segundos
        self.add_behaviour(check_recharge_b)
        
        # 2. Comportamento para receber CFP de tarefa
        receive_cfp_b = ReceiveCFPTaskBehaviour()
        template_cfp = Template()
        template_cfp.set_metadata("performative", PERFORMATIVE_CFP_TASK)
        # O agente deve ouvir todos os SoilAgents
        self.add_behaviour(receive_cfp_b, template_cfp)
        
        # 3. Comportamento para receber resposta à proposta de tarefa

        template_accept = Template()
        template_accept.set_metadata("performative", PERFORMATIVE_ACCEPT_PROPOSAL)
        template_reject = Template()
        template_reject.set_metadata("performative", PERFORMATIVE_REJECT_PROPOSAL)
        # Adicionar o mesmo comportamento para ambos os templates
        self.add_behaviour(ReceiveProposalResponseBehaviour(), template_accept)
        self.add_behaviour(ReceiveProposalResponseBehaviour(), template_reject)
        
        # O comportamento de recarga (ReceiveRechargeProposalsBehaviour e ExecuteRechargeBehaviour)
        # é adicionado dinamicamente pelo CheckRechargeBehaviour.


    # =====================
    #   Funções de Comunicação
    # =====================
    
    async def send_propose_task(self, to_jid, cfp_id, eta_ticks, energy_cost):
        """Envia uma proposta de tarefa (fertilização)."""
        body = {
            "cfp_id": cfp_id,
            "eta_ticks": eta_ticks,
            "battery_lost": energy_cost,
        }
        msg = make_message(to_jid, PERFORMATIVE_PROPOSE_TASK, body)
        return msg

    async def send_reject_proposal(self, to_jid, cfp_id):
        """Envia uma rejeição de proposta de tarefa ou recarga."""
        body = {
            "cfp_id": cfp_id,
            "decision": "reject",
        }
        msg = make_message(to_jid, PERFORMATIVE_REJECT_PROPOSAL, body)
        return msg

    async def send_failure(self, to_jid, cfp_id):
        """Envia uma mensagem de falha na execução da tarefa."""
        body = {
            "cfp_id": cfp_id,
            "status": "failed",
        }
        msg = make_message(to_jid, PERFORMATIVE_FAILURE, body)
        return msg

    async def send_cfp_recharge_to_all(self, low_fertilize, low_energy):
        """Envia um CFP (Call For Proposal) para recarga de água ou energia a TODOS os LogisticAgents."""
        
        # Gera um ID único para o CFP de recarga
        cfp_id = f"recharge_{self.jid}_{time.time()}"
        
        # Determina o tipo de recurso necessário e a quantidade (inteiro)
        if low_fertilize:
            task_type = "fertilizer"
            required_resources = int(self.fertilize_capacity_max - self.fertilize_capacity)
        elif low_energy:
            task_type = "battery"
            required_resources = int(100 - self.energy)
        else:
            # Não deve acontecer, mas por segurança
            return None

        body = {
            "cfp_id": cfp_id,
            "task_type": task_type,
            "required_resources": required_resources,
            "position": self.position,
            "priority": "High",
        }
            
        return cfp_id, body

    async def send_accept_proposal(self, to_jid, cfp_id):
        """Envia uma aceitação de proposta (usado para aceitar proposta de recarga)."""
        body = {
            "cfp_id": cfp_id,
            "decision": "accept",
        }
        msg = make_message(to_jid, PERFORMATIVE_ACCEPT_PROPOSAL, body)
        return msg
