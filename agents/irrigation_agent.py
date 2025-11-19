"""
Módulo do Agente de Irrigação.

Este módulo implementa um agente de irrigação autónomo que utiliza o framework SPADE
para comunicação multi-agente. O agente é responsável por receber pedidos de irrigação,
gerir os seus recursos (água e energia) e coordenar com agentes logísticos para recargas.
"""

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
    """Calcula a distância de Manhattan entre duas posições.
    
    Args:
        pos1 (tuple): Tupla (row, col) representando a primeira posição.
        pos2 (tuple): Tupla (row, col) representando a segunda posição.
    
    Returns:
        int: Distância de Manhattan entre as duas posições.
    """
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

def calculate_energy_cost(distance):
    """Calcula o custo de energia para percorrer uma distância.
    
    O custo é calculado como 1 unidade de energia por cada 2 unidades de distância.
    
    Args:
        distance (int): Distância total a percorrer.
    
    Returns:
        int: Custo de energia necessário.
    """
    return distance // 2

# =================================================================================
#   Comportamentos
# =================================================================================


class CheckRechargeBehaviour(PeriodicBehaviour):
    """Comportamento periódico que verifica a necessidade de recarga de recursos.
    
    Este comportamento é executado periodicamente para monitorizar os níveis de água
    e energia do agente. Quando os recursos estão baixos (água < 15% ou energia < 15),
    inicia o processo de recarga enviando CFPs aos agentes logísticos.
    
    Attributes:
        agent (IrrigationAgent): Referência ao agente de irrigação proprietário.
    """

    async def run(self):
        """Executa a verificação periódica de recursos.
        
        Verifica os níveis de água e energia. Se algum recurso estiver baixo e o agente
        estiver idle, inicia o processo de recarga enviando CFPs aos agentes logísticos.
        """
        # Se o agente estiver ocupado ou já a carregar, não faz nada
        if self.agent.status != "idle":
            return

        low_water = self.agent.water_capacity < 0.15 * self.agent.water_capacity_max
        low_energy = self.agent.energy < 15 # 15% de 100 é 15

        if low_water:
            self.agent.logger.info(f"[IRRI] Água baixa: {self.agent.water_capacity}L. A solicitar recarga de água...")
            self.agent.status = "charging"
            
            # Envia CFP para todos os Logistics e inicia o comportamento de recolha de propostas
            cfp_id, body = await self.agent.send_cfp_recharge_to_all(low_water=True, low_energy=False)
            
            for to_jid in self.agent.log_jid:
                msg = make_message(to_jid, PERFORMATIVE_CFP_RECHARGE, body)
                await self.send(msg)
                self.agent.logger.info(f"CFP_RECHARGE ({cfp_id}) enviado para {to_jid} a pedir {body["task_type"]} ({body["required_resources"]}).")

            # Adiciona o comportamento para receber as propostas
            receive_proposals_b = ReceiveRechargeProposalsBehaviour(cfp_id)
            self.agent.add_behaviour(receive_proposals_b)
            return # Sai para processar apenas uma recarga de cada vez

        if low_energy:
            self.agent.logger.info(f"[IRRI] Energia baixa: {self.agent.energy}. A solicitar recarga de bateria...")
            self.agent.status = "charging"
            
            # Envia CFP para todos os Logistics e inicia o comportamento de recolha de propostas
            cfp_id, body  = await self.agent.send_cfp_recharge_to_all(low_water=False, low_energy=True)
            
            for to_jid in self.agent.log_jid:
                msg = make_message(to_jid, PERFORMATIVE_CFP_RECHARGE, body)
                await self.send(msg)
                self.agent.logger.info(f"CFP_RECHARGE ({cfp_id}) enviado para {to_jid} a pedir {body["task_type"]} ({body["required_resources"]}).")

            # Adiciona o comportamento para receber as propostas
            receive_proposals_b = ReceiveRechargeProposalsBehaviour(cfp_id)
            self.agent.add_behaviour(receive_proposals_b)
            return # Sai para processar apenas uma recarga de cada vez


class ReceiveCFPTaskBehaviour(CyclicBehaviour):
    """Comportamento cíclico que recebe e processa CFPs de tarefas de irrigação.
    
    Este comportamento escuta continuamente por Call For Proposals (CFPs) de agentes
    de solo que necessitam de irrigação. Avalia cada pedido com base na disponibilidade
    de recursos e distância, enviando propostas quando possível.
    """
    async def run(self):
        """Recebe e processa mensagens CFP de irrigação.
        
        Para cada CFP recebido:
        1. Valida se é uma tarefa de irrigação
        2. Calcula distância, custo de energia e tempo estimado
        3. Verifica disponibilidade de água e energia
        4. Envia proposta se os recursos forem suficientes, ou rejeita caso contrário
        """
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
                
                # Apenas processa se for uma tarefa de irrigação
                if content.get("task_type") != "irrigation_application":
                    self.agent.logger.warning(f"[IRRI] CFP recebido não é de irrigação: {content.get('task_type')}")
                    return

                # Encontrar a quantidade de água necessária
                water_needed = 0
                for res in required_resources:
                    if res.get("type") == "water":
                        water_needed = res.get("amount")
                        break
                
                if water_needed == 0:
                    self.agent.logger.warning(f"[IRRI] CFP {cfp_id} não especifica água necessária. A rejeitar.")
                    msg = await self.agent.send_reject_proposal(sender_jid, cfp_id)
                    await self.send(msg)

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
                
                # Se a água necessária for maior que a capacidade atual
                if water_needed > self.agent.water_capacity:
                    self.agent.logger.info(f"[IRRI] CFP {cfp_id} rejeitado: Água insuficiente ({water_needed}L necessários, {self.agent.water_capacity}L disponíveis).")
                    msg = await self.agent.send_reject_proposal(sender_jid, cfp_id)
                    await self.send(msg)
                
                # Se o custo de energia for maior que a energia atual
                if energy_cost > self.agent.energy:
                    self.agent.logger.info(f"[IRRI] CFP {cfp_id} rejeitado: Energia insuficiente ({energy_cost} necessários, {self.agent.energy} disponíveis).")
                    msg = await self.agent.send_reject_proposal(sender_jid, cfp_id)
                    await self.send(msg)
                
                # 3. Aceitar e Propor
                self.agent.logger.info(f"[IRRI] CFP {cfp_id} aceite. A propor tarefa ao {sender_jid}. Custo de energia: {energy_cost}, ETA: {eta_ticks}.")
                
                # Armazenar a proposta para referência futura
                self.agent.awaiting_proposals[cfp_id] = {
                    "sender": sender_jid,
                    "zone": target_pos,
                    "water_needed": water_needed,
                    "energy_cost": energy_cost,
                    "eta_ticks": eta_ticks
                }
                
                # Enviar Proposta
                msg = await self.agent.send_propose_task(sender_jid, cfp_id, eta_ticks, energy_cost)
                await self.send(msg)
            except json.JSONDecodeError:
                self.agent.logger.error(f"[IRRI] Erro ao descodificar JSON do CFP: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[IRRI] Erro ao processar CFP: {e}")
        else:
            # Sem mensagem, espera um pouco
            await asyncio.sleep(0.1)

class ReceiveProposalResponseBehaviour(CyclicBehaviour):
    """Comportamento cíclico que recebe respostas a propostas de tarefas enviadas.
    
    Este comportamento escuta por mensagens de aceitação ou rejeição de propostas
    enviadas aos agentes de solo. Quando uma proposta é aceite, inicia a execução
    da tarefa de irrigação.
    
    """
    async def run(self):
        """Processa respostas (Accept/Reject) às propostas de irrigação.
        
        Para cada resposta:
        - Se ACCEPT: Inicia o comportamento de execução da tarefa
        - Se REJECT: Volta ao estado idle e descarta a proposta
        """
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
                    self.agent.logger.warning(f"[IRRI] Resposta recebida para CFP_ID desconhecido: {cfp_id}")
                    return
                
                proposal_data = self.agent.awaiting_proposals.pop(cfp_id)
                
                if performative == PERFORMATIVE_ACCEPT_PROPOSAL:
                    self.agent.logger.info(f"[IRRI] Proposta {cfp_id} ACEITE pelo {str(msg.sender)}. A iniciar tarefa de irrigação.")
                    
                    # Iniciar o comportamento de execução da tarefa
                    task_exec_b = ExecuteTaskBehaviour(proposal_data, cfp_id)
                    self.agent.add_behaviour(task_exec_b)
                    
                elif performative == PERFORMATIVE_REJECT_PROPOSAL:
                    self.agent.logger.info(f"[IRRI] Proposta {cfp_id} REJEITADA pelo {str(msg.sender)}. Motivo: {content.get('details', 'Não especificado')}")
                    # O agente volta ao estado 'idle'
                    self.agent.status = "idle"
                    
            except json.JSONDecodeError:
                self.agent.logger.error(f"[IRRI] Erro ao descodificar JSON da resposta: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[IRRI] Erro ao processar resposta à proposta: {e}")
        else:
            await asyncio.sleep(0.1)

class ExecuteTaskBehaviour(OneShotBehaviour):
    """Comportamento de execução única para realizar uma tarefa de irrigação.
    
    Este comportamento é responsável por executar todo o processo de irrigação:
    movimentação até ao local, aplicação da água através do EnvironmentAgent,
    retorno à base e notificação de conclusão.
    
    Attributes:
        proposal_data (dict): Dados da proposta aceite incluindo destino e recursos.
        cfp_id (str): Identificador único da tarefa.
        agent (IrrigationAgent): Referência ao agente de irrigação proprietário.
    """

    def __init__(self, proposal_data,cfp_id):
        """Inicializa o comportamento de execução de tarefa.
        
        Args:
            proposal_data (dict): Dicionário contendo:
                - sender: JID do agente solicitante
                - zone: Posição alvo (row, col)
                - water_needed: Quantidade de água necessária
                - energy_cost: Custo energético da tarefa
                - eta_ticks: Tempo estimado total
            cfp_id (str): Identificador único do CFP associado.
        """
        super().__init__()
        self.proposal_data = proposal_data
        self.cfp_id = cfp_id

    async def run(self):
        """Executa a tarefa de irrigação completa.
        
        Processo:
        1. Move-se para a zona alvo
        2. Interage com o EnvironmentAgent para aplicar irrigação
        3. Atualiza recursos (água e energia)
        4. Retorna à base
        5. Notifica conclusão ou falha ao solicitante
        """
        sender_jid = self.proposal_data["sender"]
        cfp_id = self.cfp_id
        target_pos = self.proposal_data["zone"]
        water_needed = self.proposal_data["water_needed"]
        energy_cost = self.proposal_data["energy_cost"]
        eta_ticks = self.proposal_data["eta_ticks"]
        
        self.agent.status = "moving"
        self.agent.logger.info(f"[IRRI] A mover para {target_pos} para irrigar. ETA: {eta_ticks} ticks.")
        
        # 1. Simular Viagem de Ida (metade do ETA)
        travel_time = eta_ticks // 2
        await asyncio.sleep(travel_time)
        self.agent.position = target_pos
        self.agent.logger.info(f"[IRRI] Chegou a {target_pos}. A iniciar irrigação.")
        
        # 2. Simular Irrigação e Interagir com EnvironmentAgent
        self.agent.status = "irrigating"
        
        # Enviar ACT para o EnvironmentAgent
        env_jid = "environment@localhost" # Assumindo que o JID do EnvironmentAgent é este
        
        act_body = {
            "action": "apply_irrigation",
            "row": target_pos[0],
            "col": target_pos[1],
            "flow_rate": water_needed
        }
        
        act_msg = make_message(
            to=env_jid,
            performative=PERFORMATIVE_INFORM,
            body_dict=act_body,
            protocol=None,
            language="json"
        )
        act_msg.set_metadata("performative", "act")
        act_msg.set_metadata("ontology", ONTOLOGY_FARM_ACTION)
        
        await self.send(act_msg)
        
        # Esperar pela resposta do EnvironmentAgent (INFORM)
        reply_template = Template()
        reply_template.set_metadata("performative", PERFORMATIVE_INFORM)
        reply_template.set_metadata("ontology", ONTOLOGY_FARM_ACTION)
        
        env_reply = await self.receive(timeout=20)
        
        if env_reply:
            try:
                reply_content = json.loads(env_reply.body)
                if reply_content.get("status") == "success":
                    self.agent.logger.info(f"[IRRI] Irrigação em {target_pos} concluída com sucesso. Mensagem do ENV: {reply_content.get('message')}")
                    
                    # 3. Atualizar estado e simular viagem de volta
                    self.agent.water_capacity -= water_needed
                    self.agent.energy -= energy_cost
                    self.agent.used_water += water_needed
                    self.agent.logger.info(f"[IRRI] Água restante: {self.agent.water_capacity}L. Energia restante: {self.agent.energy}.")
                    
                    # Simular Viagem de Volta
                    self.agent.logger.info(f"[IRRI] A regressar à base. Tempo de viagem: {travel_time} ticks.")
                    await asyncio.sleep(travel_time)
                    self.agent.position = (self.agent.row, self.agent.col) # Volta à posição inicial (base)
                    self.agent.status = "idle"
                    
                    # 4. Enviar Done
                    done_body = {
                        "cfp_id": cfp_id,
                        "status": "done",
                        "seed_type": 0, # Não se aplica a irrigação, mas mantemos o formato
                        "details": {"water_used": water_needed, "time_taken": eta_ticks}
                    }
                    done_msg = make_message(sender_jid, PERFORMATIVE_DONE, done_body)
                    await self.send(done_msg)
                    self.agent.logger.info(f"[IRRI] Tarefa {cfp_id} concluída e Done enviado para {sender_jid}.")
                    
                else:
                    # Falha na irrigação (EnvironmentAgent reportou erro)
                    self.agent.logger.error(f"[IRRI] Falha na irrigação em {target_pos}. Mensagem do ENV: {reply_content.get('message')}")
                    self.agent.status = "idle"
                    msg = await self.agent.send_failure(sender_jid, cfp_id)
                    await self.send(msg)
                    
            except json.JSONDecodeError:
                self.agent.logger.error(f"[IRRI] Erro ao descodificar JSON da resposta do EnvironmentAgent: {env_reply.body}")
                self.agent.status = "idle"
                msg = await self.agent.send_failure(sender_jid, cfp_id)
                await self.send(msg)
            
        else:
            # Timeout na resposta do EnvironmentAgent
            self.agent.logger.error(f"[IRRI] Timeout ao esperar resposta do EnvironmentAgent para irrigação em {target_pos}.")
            self.agent.status = "idle"
            msg = await self.agent.send_failure(sender_jid, cfp_id)
            await self.send(msg)

class ReceiveRechargeProposalsBehaviour(OneShotBehaviour):
    """Comportamento de execução única que recebe e avalia propostas de recarga.
    
    Este comportamento aguarda por propostas de recarga de múltiplos agentes logísticos,
    seleciona a melhor proposta e aceita-a, rejeitando as restantes.
    
    Attributes:
        cfp_id (str): Identificador único do CFP de recarga.
        proposals (list): Lista de propostas recebidas.
        timeout (int): Tempo de espera por propostas (segundos).
        agent (IrrigationAgent): Referência ao agente de irrigação proprietário.
    """
    def __init__(self, cfp_id):
        """Inicializa o comportamento de receção de propostas de recarga.
        
        Args:
            cfp_id (str): Identificador único do CFP de recarga emitido.
        """
        super().__init__()
        self.cfp_id = cfp_id
        self.proposals = []
        self.timeout = 3 # Tempo para esperar por todas as propostas

    async def run(self):
        """Recebe, avalia e seleciona a melhor proposta de recarga.
        
        Processo:
        1. Aguarda propostas durante o período de timeout
        2. Seleciona a proposta com menor ETA
        3. Aceita a melhor proposta e rejeita as restantes
        4. Inicia o comportamento de execução da recarga
        """
        self.agent.logger.info(f"[IRRI] A aguardar propostas de recarga para CFP {self.cfp_id}...")
        
        # Espera por todas as propostas até ao timeout
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            # Template para receber PROPOSE_RECHARGE
            template = Template()
            template.set_metadata("performative", PERFORMATIVE_PROPOSE_RECHARGE)
            
            msg = await self.receive(timeout=2) # Espera 2 segundos de cada vez
            
            if msg:
                try:
                    content = json.loads(msg.body)
                    if content.get("cfp_id") == self.cfp_id:
                        if content.get("eta_ticks") is None:
                            self.agent.logger.warning(f"[IRRI] Proposta inválida recebida de {str(msg.sender)}: ETA ausente.")
                        else:
                            self.proposals.append({
                                "sender": str(msg.sender),
                                "eta_ticks": content.get("eta_ticks"),
                                "resources": content.get("resources")
                            })
                            self.agent.logger.info(f"[IRRI] Proposta recebida de {str(msg.sender)}. ETA: {content.get('eta_ticks')}.")
                except json.JSONDecodeError:
                    self.agent.logger.error(f"[IRRI] Erro ao descodificar JSON da proposta de recarga: {msg.body}")
            
            await asyncio.sleep(0.1) # Pequena pausa para não bloquear

        # 1. Selecionar a melhor proposta (menor ETA)
        if not self.proposals:
            self.agent.logger.warning(f"[IRRI] Nenhuma proposta de recarga recebida para CFP {self.cfp_id}. A tentar novamente.")
            self.agent.status = "idle" # Volta a idle para o CheckRechargeBehaviour tentar novamente
            return

        best_proposal = min(self.proposals, key=lambda p: p['eta_ticks'])
        
        self.agent.logger.info(f"[IRRI] Melhor proposta selecionada: {best_proposal['sender']} com ETA {best_proposal['eta_ticks']}.")

        # 2. Aceitar a melhor e rejeitar as outras
        for proposal in self.proposals:
            if proposal == best_proposal:
                # Aceitar
                msg = await self.agent.send_accept_proposal(proposal['sender'], self.cfp_id)
                await self.send(msg)
                self.agent.logger.info(f"[IRRI] Proposta de {proposal['sender']} ACEITE.")
                
                # Iniciar o comportamento de execução da recarga
                template = Template()
                template.set_metadata("performative", PERFORMATIVE_DONE)
                execute_recharge_b = ExecuteRechargeBehaviour(best_proposal,self.cfp_id)
                self.agent.add_behaviour(execute_recharge_b,template=template)
                
            else:
                # Rejeitar
                msg = await self.agent.send_reject_proposal(proposal['sender'], self.cfp_id)
                await self.send(msg)
                self.agent.logger.info(f"[IRRI] Proposta de {proposal['sender']} REJEITADA.")

class ExecuteRechargeBehaviour(CyclicBehaviour):
    """Comportamento cíclico que aguarda e processa a conclusão da recarga.
    
    Este comportamento aguarda a chegada do LogisticAgent e a mensagem DONE que
    confirma a entrega dos recursos. Após receber a confirmação, atualiza os
    recursos do agente.
    
    Attributes:
        proposal_data (dict): Dados da proposta de recarga aceite.
        logistic_jid (str): JID do agente logístico selecionado.
        cfp_id (str): Identificador único do CFP de recarga.
        eta_ticks (int): Tempo estimado de chegada.
        start_time (float): Timestamp do início da espera.
        awaiting_done (bool): Flag indicando se ainda aguarda a mensagem DONE.
        agent (IrrigationAgent): Referência ao agente de irrigação proprietário.
    """
    def __init__(self, proposal_data,cfp_id):
        """Inicializa o comportamento de execução de recarga.
        
        Args:
            proposal_data (dict): Dicionário contendo:
                - sender: JID do agente logístico
                - eta_ticks: Tempo estimado de chegada
                - resources: Recursos a serem entregues
            cfp_id (str): Identificador único do CFP de recarga.
        """
        super().__init__()
        self.proposal_data = proposal_data
        self.logistic_jid = proposal_data["sender"]
        self.cfp_id = cfp_id
        self.eta_ticks = proposal_data["eta_ticks"]
        self.start_time = time.time()
        self.awaiting_done = True

    async def on_start(self):
        """Simula o tempo de espera pela chegada do agente logístico.
        
        Este método é executado quando o comportamento é iniciado e simula
        o tempo de viagem do agente logístico até à posição do agente de irrigação.
        """
        self.agent.logger.info(f"[IRRI] A aguardar a chegada do LogisticAgent ({self.logistic_jid}). ETA: {self.eta_ticks} ticks.")
        # Simular o tempo de espera pela chegada do LogisticAgent
        await asyncio.sleep(self.eta_ticks)
        self.agent.logger.info(f"[IRRI] Tempo de espera pela chegada do LogisticAgent ({self.logistic_jid}) concluído. A aguardar mensagem DONE.")

    async def run(self):
        """Aguarda e processa a mensagem DONE de conclusão da recarga.
        
        Verifica continuamente por mensagens DONE do agente logístico.
        Quando recebida, atualiza os recursos (água ou energia) e volta
        ao estado idle. Inclui timeout para evitar espera infinita.
        """
        if not self.awaiting_done:
            self.kill()
            return

        # Template para receber DONE do LogisticAgent

        msg = await self.receive(timeout=5)
        
        if msg:
            performative = msg.get_metadata("performative")
            sender = str(msg.sender)
            
            if performative == PERFORMATIVE_DONE and sender == self.logistic_jid:
                try:
                    content = json.loads(msg.body)
                    if content.get("cfp_id") == self.cfp_id:
                        self.agent.logger.info(f"[IRRI] Mensagem DONE recebida de {self.logistic_jid}. Recarga concluída.")
                        
                        # Repor Recursos com base nos detalhes da mensagem DONE
                        details = content.get("details", {})
                        energy_replenished = 0
                        water_replenished = 0
                        # O utilizador forneceu um exemplo com "water_used" e "time_taken".
                        # Assumindo que "water_used" é a quantidade de água recarregada.
                        if (details["resource_type"] == "battery"): energy_replenished = details.get("amount_delivered", 0)
                        # Para a bateria, o LogisticAgent deve enviar a quantidade recarregada.
                        # Vamos assumir a chave "energy_used" para consistência.
                        else: water_replenished = details.get("amount_delivered", 0)
                        
                        if water_replenished > 0:
                            self.agent.water_capacity = min(self.agent.water_capacity + water_replenished, self.agent.water_capacity_max)
                            self.agent.logger.info(f"[IRRI] Recarga de ÁGUA concluída. Reposto: {water_replenished}L. Água atual: {self.agent.water_capacity}L.")
                            
                        if energy_replenished > 0:
                            self.agent.energy = min(self.agent.energy + energy_replenished, 100)
                            self.agent.logger.info(f"[IRRI] Recarga de ENERGIA concluída. Reposto: {energy_replenished}. Energia atual: {self.agent.energy}.")
                            
                            
                        self.agent.status = "idle"
                        self.agent.logger.info("[IRRI] Agente de Irrigação de volta ao estado 'idle'.")
                        self.awaiting_done = False
                        self.kill()
                        return
                    else:
                        self.agent.logger.warning(f"[IRRI] Mensagem DONE recebida com CFP_ID incorreto: {content.get('cfp_id')}")
                except json.JSONDecodeError:
                    self.agent.logger.error(f"[IRRI] Erro ao descodificar JSON do DONE de recarga: {msg.body}")
            else:
                self.agent.logger.warning(f"[IRRI] Mensagem inesperada recebida durante a recarga: {performative} de {sender}")
        
        # Timeout para o DONE (se for muito longo, pode ser um problema)
        if time.time() - self.start_time > self.eta_ticks + 60: # 60 segundos extra de tolerância
            self.agent.logger.error(f"[IRRI] Timeout ao esperar mensagem DONE de recarga de {self.logistic_jid}. Assumindo falha e voltando a 'idle'.")
            self.agent.status = "idle"
            self.awaiting_done = False
            self.kill()


# =================================================================================
#   Agente Principal
# =================================================================================

class IrrigationAgent(Agent):
    """Agente autónomo de irrigação para gestão de recursos hídricos.
    
    Este agente é responsável por responder a pedidos de irrigação, gerir recursos
    (água e energia) e coordenar com agentes logísticos para recargas.
    
    Attributes:
        position (tuple): Posição atual (row, col) do agente.
        row (int): Linha da posição base.
        col (int): Coluna da posição base.
        status (str): Estado atual ('idle', 'charging', 'irrigating', 'moving').
        soil_jid (list): Lista de JIDs dos agentes de solo.
        log_jid (list): Lista de JIDs dos agentes logísticos.
        flow_rate (int): Taxa de fluxo de água.
        energy (float): Energia disponível (0-100).
        water_capacity (float): Quantidade atual de água disponível.
        water_capacity_max (int): Capacidade máxima de água.
        used_water (int): Total de água utilizada.
        awaiting_proposals (dict): Propostas pendentes indexadas por cfp_id.
        recharge_cfp_id (str): ID do CFP de recarga atual.
    """
    def __init__(self,jid,password,log_jid,soil_jid,row,col):
        """Inicializa o agente de irrigação.
        
        Args:
            jid (str): Jabber ID do agente.
            password (str): Password para autenticação.
            log_jid (list): Lista de JIDs dos agentes logísticos.
            soil_jid (list): Lista de JIDs dos agentes de solo.
            row (int): Linha da posição inicial.
            col (int): Coluna da posição inicial.
        """
        super().__init__(jid,password)
        
        # Configuração de Logging
        self.logger = logging.getLogger(f"[IRRI] {jid}")
        self.logger.setLevel(logging.INFO)

        self.position = (row, col)
        self.row = row
        self.col = col
        self.status = "idle"  # idle, charging, irrigating, moving
        self.soil_jid = soil_jid
        self.log_jid = log_jid

        self.flow_rate = 4
        self.energy = 100.0
        self.water_capacity = 100.0 # capacidade 
        self.water_capacity_max = 100 
        self.used_water = 0

        # Estrutura para armazenar propostas enviadas e aguardando resposta (por cfp_id)
        self.awaiting_proposals = {}
        
        # ID para o CFP de recarga (para rastrear a recarga)
        self.recharge_cfp_id = None 

    # =====================
    #   SETUP
    # =====================
    async def setup(self):
        """Configura e inicia os comportamentos do agente.
        
        Inicializa três comportamentos principais:
        - CheckRechargeBehaviour: Verificação periódica de necessidade de recarga
        - ReceiveCFPTaskBehaviour: Receção de CFPs de tarefas de irrigação
        - ReceiveProposalResponseBehaviour: Receção de respostas a propostas enviadas


        O comportamento de recarga (ReceiveRechargeProposalsBehaviour e ExecuteRechargeBehaviour)
        é adicionado dinamicamente pelo CheckRechargeBehaviour.
        """
        self.logger.info(f"[IRRI] IrrigationAgent {self.jid} iniciado.")
        
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

    async def stop(self):
        """Para o agente e regista a quantidade de agua usada na simulação."""
        self.logger.info(f"{'=' * 35} IRRI {'=' * 35}")
        self.logger.info(f"{self.jid} usou {self.used_water} L de água")
        self.logger.info(f"{'=' * 35} IRRI {'=' * 35}")
        await super().stop()

    # =====================
    #   Funções de Comunicação
    # =====================
    
    async def send_propose_task(self, to_jid, cfp_id, eta_ticks, energy_cost):
        """Envia proposta de execução de tarefa de irrigação.
        
        Args:
            to_jid (str): JID do destinatário.
            cfp_id (str): ID do CFP a que responde.
            eta_ticks (int): Tempo estimado de conclusão.
            energy_cost (int): Custo energético da tarefa.
            
        Returns:
            Message: Mensagem SPADE preparada para envio.
        """
        body = {
            "cfp_id": cfp_id,
            "eta_ticks": eta_ticks,
            "battery_lost": energy_cost,
        }
        msg = make_message(to_jid, PERFORMATIVE_PROPOSE_TASK, body)
        return msg

    async def send_reject_proposal(self, to_jid, cfp_id):
        """Envia rejeição de proposta.
        
        Args:
            to_jid (str): JID do destinatário.
            cfp_id (str): ID do CFP rejeitado.
            
        Returns:
            Message: Mensagem SPADE de rejeição.
        """
        body = {
            "cfp_id": cfp_id,
            "decision": "reject",
        }
        msg = make_message(to_jid, PERFORMATIVE_REJECT_PROPOSAL, body)
        return msg

    async def send_failure(self, to_jid, cfp_id):
        """Envia notificação de falha na execução.
        
        Args:
            to_jid (str): JID do destinatário.
            cfp_id (str): ID da tarefa que falhou.
            
        Returns:
            Message: Mensagem SPADE de falha.
        """
        body = {
            "cfp_id": cfp_id,
            "status": "failed",
        }
        msg = make_message(to_jid, PERFORMATIVE_FAILURE, body)
        return msg

    async def send_cfp_recharge_to_all(self, low_water, low_energy):
        """Cria CFP de recarga para broadcast aos agentes logísticos.
        
        Args:
            low_water (bool): Se True, solicita recarga de água.
            low_energy (bool): Se True, solicita recarga de energia.
            
        Returns:
            tuple: (cfp_id, body) onde cfp_id é o identificador único e body 
                   contém os dados do CFP, ou None se ambos os parâmetros forem False.
        """
        
        # Gera um ID único para o CFP de recarga
        cfp_id = f"recharge_{self.jid}_{time.time()}"
        
        # Determina o tipo de recurso necessário e a quantidade (inteiro)
        if low_water:
            task_type = "water"
            required_resources = int(self.water_capacity_max - self.water_capacity)
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
    
            
        return cfp_id,body

    async def send_accept_proposal(self, to_jid, cfp_id):
        """Envia aceitação de proposta de recarga.
        
        Args:
            to_jid (str): JID do agente logístico selecionado.
            cfp_id (str): ID do CFP aceite.
            
        Returns:
            Message: Mensagem SPADE de aceitação.
        """
        body = {
            "cfp_id": cfp_id,
            "decision": "accept",
        }
        msg = make_message(to_jid, PERFORMATIVE_ACCEPT_PROPOSAL, body)
        return msg
