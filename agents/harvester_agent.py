"""
Módulo do Agente Harvester (Colheitadeira/Plantadora).

Este módulo implementa um agente autónomo para um sistema multi-agente de gestão agrícola.
O agente é responsável por realizar tarefas de colheita e plantação, gerenciar recursos
(combustível e sementes), e comunicar com agentes logísticos e de armazenamento.
"""

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
    """Calcula a distância de Manhattan entre duas posições.
    
    Args:
        pos1 (tuple): Primeira posição no formato (row, col).
        pos2 (tuple): Segunda posição no formato (row, col).
        
    Returns:
        int: Distância de Manhattan entre as duas posições.
    """
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

def calculate_fuel_cost(distance):
    """Calcula o custo de combustível para ida e volta.
    
    O custo é calculado considerando que cada 2 valores de distância
    consomem 0.5 unidades de combustível, para ida e volta.
    
    Args:
        distance (int): Distância de Manhattan até o destino.
        
    Returns:
        float: Custo total de combustível para ida e volta.
    """
    # Cada 2 valores de distância é -0.5 de combustível.
    # Custo de ida: (distance / 2) * 0.5
    # Custo de ida e volta: 2 * (distance / 2) * 0.5 = distance * 0.5
    return distance * 0.5

# =====================
#   BEHAVIOURS
# =====================

class HarvestYieldBehaviour(PeriodicBehaviour):
    """Comportamento periódico que verifica o rendimento das colheitas.
    
    Monitora os níveis de colheita armazenados e inicia o processo de entrega
    quando qualquer tipo de semente atinge 100 unidades ou quando o agente
    está a ser terminado.
    
    Attributes:
        stop_beha (bool, optional): Flag para forçar entrega durante o shutdown.
    """


    def __init__(self, period, stop_beha = None):
        """Inicializa o comportamento de verificação de rendimento.
        
        Args:
            period (float): Período em segundos entre verificações.
            stop_beha (bool, optional): Se True, força a entrega imediata. Defaults to None.
        """
        super().__init__(period=period)
        self.stop_beha = stop_beha

    async def run(self):
        """Executa a verificação periódica do rendimento de colheita.
        
        Verifica se algum tipo de semente atingiu o limite de 100 unidades
        ou se o agente está a ser terminado. Se sim, inicia o processo de entrega.
        """
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
    """Comportamento de entrega de colheita ao agente de armazenamento.
    
    Simula a viagem até ao armazém e envia a colheita acumulada para
    o agente Storage através de uma mensagem inform_harvest.
    
    Attributes:
        sto_jid (str): JID do agente Storage destinatário.
        stop_beha (bool): Flag indicando se é uma entrega de shutdown.
    """
    def __init__(self, sto_jid,stop_beha):
        """Inicializa o comportamento de entrega.
        
        Args:
            sto_jid (str): JID do agente Storage.
            stop_beha (bool): True se for uma entrega durante o shutdown.
        """
        super().__init__()
        self.sto_jid = sto_jid
        self.stop_beha = stop_beha

    async def run(self):
        """Executa o processo de entrega da colheita.
        
        Simula a viagem, prepara os dados da colheita e
        envia uma mensagem inform_harvest ao agente Storage.
        """
        self.agent.logger.info(f"[DELIVERY] A viajar para entregar a colheita ao logístico {self.sto_jid}.")
        # Simula o tempo de viagem (ida e volta)
        if not self.stop_beha: await asyncio.sleep(5)
        # Prepara a mensagem com os dados da colheita
        amount_type_list = []
        for seed_type, amount in self.agent.yield_seed.items():
            if amount >= 100 or self.stop_beha:
                amount_type_list.append({"seed_type": seed_type, "amount": amount})

        # Envia a mensagem `inform_harvest`
        msg = await self.agent.send_inform_harvest(self.sto_jid, amount_type_list)
        await self.send(msg)
        self.agent.logger.info(f"[DELIVERY] Mensagem 'inform_harvest' enviada para {self.sto_jid}.")

class InformReceivedReceiver(CyclicBehaviour):
    """Comportamento que recebe confirmações de entrega do agente Storage.
    
    Processa mensagens inform_received que confirmam a receção da colheita
    pelo agente Storage e atualiza o inventário do Harvester em conformidade.
    """

    async def run(self):
        """Aguarda e processa confirmações de entrega.
        
        Recebe mensagens inform_received, extrai os detalhes da entrega confirmada,
        atualiza o yield_seed e o inventário da máquina, e retorna o agente ao
        estado idle.
        """
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
                self.agent.status = "idle" # Garante que o agente não fica bloqueado
            except Exception as e:
                self.agent.logger.exception(f"[DELIVERY] Erro ao processar 'inform_received': {e}")
                self.agent.status = "idle" # Garante que o agente não fica bloqueado


class CheckResourcesBehaviour(PeriodicBehaviour):
    """Comportamento periódico que monitoriza níveis de recursos.
    
    Verifica periodicamente os níveis de combustível e sementes do agente.
    Quando algum recurso está baixo (< 10), inicia um processo de negociação
    com agentes logísticos para reabastecimento.
    
    Attributes:
        agent (HarvesterAgent): Referência ao agente pai.
    """
    
    def __init__(self, period, agent):
        """Inicializa o comportamento de verificação de recursos.
        
        Args:
            period (float): Período em segundos entre verificações.
            agent (HarvesterAgent): Referência ao agente Harvester.
        """
        super().__init__(period)
        self.agent = agent

    async def run(self):
        """Verifica níveis de combustível e sementes.
        
        Se o combustível estiver abaixo de 10 ou qualquer tipo de semente
        estiver abaixo de 10 unidades, envia CFPs (Call for Proposals) para
        todos os agentes logísticos e inicia o processo de negociação.
        """
        
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
    """Comportamento que recebe e processa CFPs de tarefas agrícolas.
    
    Recebe Call for Proposals do agente Logistic para tarefas de colheita
    ou plantação. Avalia a viabilidade da tarefa com base em recursos disponíveis
    e responde com proposta ou rejeição.
    """

    async def run(self):
        """Processa mensagens CFP_TASK recebidas.
        
        Avalia cada CFP considerando:
        - Status atual do agente (deve estar idle)
        - Distância até a zona alvo
        - Combustível necessário vs disponível
        - Capacidade de armazenamento (para colheita)
        - Sementes disponíveis (para plantação)
        
        Responde com PROPOSE_TASK se puder aceitar ou REJECT_PROPOSAL caso contrário.
        """
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
    """Comportamento que recebe e seleciona propostas de reabastecimento.
    
    Aguarda propostas de múltiplos agentes logísticos durante um período de timeout,
    seleciona a melhor proposta (menor ETA) e aceita/rejeita as propostas recebidas.
    
    Attributes:
        cfp_id (str): Identificador do Call for Proposal de reabastecimento.
        proposals (list): Lista de propostas recebidas.
        timeout (int): Tempo de espera em segundos para receber propostas.
    """

    def __init__(self, cfp_id):
        """Inicializa o comportamento de receção de propostas.
        
        Args:
            cfp_id (str): Identificador único do CFP de reabastecimento.
        """
        super().__init__()
        self.cfp_id = cfp_id
        self.proposals = []
        self.timeout = 3 # Tempo para esperar por todas as propostas

    async def run(self):
        """Recebe, avalia e seleciona propostas de reabastecimento.
        
        Aguarda propostas durante o timeout, seleciona a proposta com menor ETA
        (tempo estimado de chegada), aceita a melhor proposta e rejeita as restantes.
        Inicia o comportamento de execução da recarga para a proposta aceite.
        """

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
    """Comportamento que executa o processo de reabastecimento.
    
    Aguarda a chegada do agente logístico (simulando o ETA) e processa
    a mensagem DONE para reabastecer os recursos do Harvester.
    
    Attributes:
        proposal_data (dict): Dados da proposta aceite.
        logistic_jid (str): JID do agente logístico selecionado.
        cfp_id (str): Identificador do CFP de reabastecimento.
        eta_ticks (int): Tempo estimado de chegada em ticks.
        start_time (float): Timestamp de início da espera.
        awaiting_done (bool): Flag indicando se está a aguardar mensagem DONE.
    """

    def __init__(self, proposal_data,cfp_id):
        """Inicializa o comportamento de execução de recarga.
        
        Args:
            proposal_data (dict): Dicionário com sender, eta_ticks e resources.
            cfp_id (str): Identificador único do CFP.
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
        
        Aguarda o tempo correspondente ao ETA antes de começar a processar
        a mensagem DONE.
        """
        self.agent.logger.info(f"[RECHARGE] A aguardar a chegada do LogisticAgent ({self.logistic_jid}). ETA: {self.eta_ticks} ticks.")
        # Simular o tempo de espera pela chegada do LogisticAgent
        await asyncio.sleep(self.eta_ticks)
        self.agent.logger.info(f"[RECHARGE] Tempo de espera pela chegada do LogisticAgent ({self.logistic_jid}) concluído. A aguardar mensagem DONE.")

    async def run(self):
        """Processa a mensagem DONE e reabastece os recursos.
        
        Recebe a mensagem DONE do agente logístico, extrai os detalhes dos
        recursos entregues (combustível ou sementes) e atualiza o estado
        do Harvester. Retorna o agente ao estado idle após conclusão.
        """
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
    """Recebe e processa respostas (Accept/Reject) às propostas de tarefas enviadas.
    
    Este comportamento cíclico aguarda mensagens de aceitação ou rejeição do
    Logistic Agent em resposta às propostas de tarefas (colheita/plantação)
    previamente enviadas pelo Harvester.
    
    Attributes:
        agent (HarvesterAgent): Referência ao agente Harvester pai.
    """


    async def run(self):
        """Processa mensagens de resposta às propostas de tarefas.
        
        Aguarda mensagens do tipo Accept ou Reject do Logistic Agent. Se a proposta
        for aceite e o agente estiver disponível, inicia o comportamento de execução
        correspondente. Se for rejeitada, retorna o agente ao estado idle.
        
        Raises:
            json.JSONDecodeError: Se a mensagem recebida não contiver JSON válido.
            Exception: Para outros erros durante o processamento.
        
        Notes:
            - Valida se o CFP_ID corresponde a uma proposta pendente
            - Verifica o status do agente antes de aceitar tarefas
            - Remove propostas processadas da fila de espera
        """
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
                    
                    if (self.agent.status != "idle"):
                        self.agent.logger.warning(f"[PROPOSAL] Proposta {cfp_id} aceite, mas o agente está ocupado ({self.agent.status}). Ignorando.")
                        msg = await self.agent.send_failure(proposal_data["sender"],cfp_id)
                        await self.send(msg)
                        return

                    self.agent.status = proposal_data["task_type"].split('_')[0] # harvesting ou planting
                    self.agent.logger.info(f"[PROPOSAL] Proposta {cfp_id} ACEITE para {proposal_data['task_type']} em {proposal_data['zone']}.")
                    
                    # Iniciar o comportamento de execução da tarefa
                    if proposal_data["task_type"] == "harvest_application":
                        b = HarvestExecutionBehaviour(proposal_data,cfp_id)
                    elif proposal_data["task_type"] == "plant_application":
                        b = PlantExecutionBehaviour(proposal_data,cfp_id)
                    else:
                        self.agent.logger.error(f"[PROPOSAL] Tipo de tarefa desconhecido após aceitação: {proposal_data['task_type']}")
                        return
                    
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
    """Executa a tarefa de colheita após aceitação da proposta pelo Logistic Agent.
    
    Este comportamento coordena todo o processo de colheita, incluindo viagem,
    interação com o Environment Agent, atualização de recursos e comunicação
    de conclusão ou falha.
    """
    
    def __init__(self, proposal_data,cfp_id):
        """Inicializa o comportamento de execução de colheita.
        
        Args:
            proposal_data (dict): Dicionário contendo:
                - sender (str): JID do Logistic Agent
                - zone (tuple): Coordenadas da zona alvo
                - fuel_cost (float): Custo de combustível
                - seed_type (int): Tipo de semente
                - required_resources (list): Recursos necessários
            cfp_id (str): Identificador único do CFP.
        """
        super().__init__()
        self.proposal_data = proposal_data
        self.cfp_id = cfp_id
        self.logistic_agent = self.proposal_data["sender"]
        self.zone = self.proposal_data["zone"]
        self.fuel_cost = self.proposal_data["fuel_cost"]
        self.seed_type = self.proposal_data["seed_type"]
        self.required_storage = next((res["amount"] for res in self.proposal_data["required_resources"] if res["type"] == "storage"), 0)

    async def run(self):
        """Executa o processo completo de colheita.
        
        O processo inclui:
            1. Viagem até à zona de colheita (simulada)
            2. Interação com Environment Agent para realizar colheita
            3. Atualização do inventário e combustível
            4. Viagem de retorno (simulada)
            5. Envio de mensagem Done ou Failure ao Logistic Agent
        
        Returns:
            None
            
        Raises:
            Exception: Captura e loga qualquer erro durante a execução.
            
        Notes:
            - Consome combustível conforme fuel_cost calculado
            - Atualiza machine_inventory e yield_seed após colheita bem-sucedida
            - Retorna sempre o agente ao estado 'idle' no final
            - Envia mensagem de falha em caso de erro ou timeout
        """

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
    """Executa a tarefa de plantação após aceitação da proposta pelo Logistic Agent.
    
    Este comportamento coordena todo o processo de plantação, incluindo viagem,
    interação com o Environment Agent, consumo de recursos e comunicação
    de conclusão ou falha.
    """
    
    def __init__(self, proposal_data,cfp_id):
        """Inicializa o comportamento de execução de plantação.
        
        Args:
            proposal_data (dict): Dicionário contendo:
                - sender (str): JID do Logistic Agent
                - zone (tuple): Coordenadas da zona alvo
                - fuel_cost (float): Custo de combustível
                - seed_type (int): Tipo de semente
                - required_resources (list): Recursos necessários
            cfp_id (str): Identificador único do CFP.
        """
        super().__init__()
        self.proposal_data = proposal_data
        self.cfp_id = cfp_id
        self.logistic_agent = self.proposal_data["sender"]
        self.zone = self.proposal_data["zone"]
        self.fuel_cost = self.proposal_data["fuel_cost"]
        self.seed_type = self.proposal_data["seed_type"]
        self.required_seeds = next((res["amount"] for res in self.proposal_data["required_resources"] if res["type"] == "seed"), 0)

    async def run(self):
        """Executa o processo completo de plantação.
        
        O processo inclui:
            1. Viagem até à zona de plantação (simulada)
            2. Interação com Environment Agent para realizar plantação
            3. Consumo de sementes e combustível
            4. Viagem de retorno (simulada)
            5. Envio de mensagem Done ou Failure ao Logistic Agent
        
        Returns:
            None
            
        Raises:
            Exception: Captura e loga qualquer erro durante a execução.
            
        Notes:
            - Consome sementes do inventário conforme required_seeds
            - Consome combustível conforme fuel_cost calculado
            - Retorna sempre o agente ao estado 'idle' no final
            - Envia mensagem de falha em caso de erro ou timeout
        """
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
    """Agente autónomo para gestão de colheita e plantação em sistema multi-agente agrícola.
    
    O HarvesterAgent é responsável por executar tarefas de colheita e plantação,
    gerir recursos (combustível e sementes), comunicar com agentes logísticos
    para negociação de tarefas e reabastecimento, e entregar colheitas ao
    agente de armazenamento.
    
    Attributes:
        pos_initial (tuple): Posição inicial (row, col) do agente no ambiente.
        row (int): Coordenada de linha da posição inicial.
        col (int): Coordenada de coluna da posição inicial.
        machine_capacity (int): Capacidade máxima de armazenamento da máquina .
        machine_inventory (int): Quantidade atual de colheita armazenada na máquina.
        yield_seed (dict): Inventário de colheita por tipo de semente {0-5: quantidade}.
        seeds (dict): Inventário de sementes disponíveis {0-5: quantidade}.
        fuel_level (float): Nível atual de combustível (0-100).
        status (str): Estado atual do agente (idle, harvesting, planting, refueling, delivering_harvest).
        env_jid (str): JID do Environment Agent.
        log_jids (list): Lista de JIDs dos Logistic Agents.
        sto_jid (str): JID do Storage Agent.
        recharge_proposals (dict): Propostas de reabastecimento recebidas.
        awaiting_proposals (dict): Propostas de tarefas aguardando resposta.
        logger (logging.Logger): Logger configurado para o agente.
        
    Note:
        Tipos de sementes:
            0: Tomate
            1: Pimento
            2: Trigo
            3: Couve
            4: Alface
            5: Cenoura
    """
    
    async def send_cfp_recharge_to_all(self, low_fuel=False, low_seeds=False, seed_type=None, required_resources=None):
        """Cria e prepara CFP de reabastecimento para envio a todos os Logistic Agents.
        
        Args:
            low_fuel (bool, optional): True se o pedido é para combustível. Defaults to False.
            low_seeds (bool, optional): True se o pedido é para sementes. Defaults to False.
            seed_type (int, optional): Tipo de semente necessária (0-5). Defaults to None.
            required_resources (float, optional): Quantidade de recursos necessária. Defaults to None.
            
        Returns:
            tuple: (cfp_id, body) onde:
                - cfp_id (str): Identificador único do CFP no formato "cfp_recharge_{timestamp}"
                - body (dict): Corpo da mensagem contendo:
                    - sender_id (str): JID do Harvester
                    - receiver_id (str): "all" para broadcast
                    - cfp_id (str): Identificador do CFP
                    - task_type (str): "fuel" ou "seeds"
                    - required_resources (float): Quantidade necessária
                    - position (tuple): Posição atual do Harvester
                    - seed_type (int): Tipo de semente (se aplicável)
                    - priority (str): "Urgent"
                    
        Returns:
            tuple: (None, None) se a chamada for inválida.
            
        Note:
            Para combustível, required_resources é calculado como (100 - fuel_level).
            Para sementes, required_resources deve ser fornecido como argumento.
        """
        
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
        """Inicializa o HarvesterAgent com configuração e recursos iniciais.
        
        Args:
            jid (str): Jabber ID do agente.
            password (str): Password para autenticação XMPP.
            row (int): Coordenada de linha da posição inicial.
            col (int): Coordenada de coluna da posição inicial.
            env_jid (str): JID do Environment Agent.
            log_jid (list): Lista de JIDs dos Logistic Agents.
            sto_jid (str): JID do Storage Agent.
            
        Note:
            Inicializa o agente com:
                - 100 unidades de cada tipo de semente
                - 100% de combustível
                - 600 unidades de capacidade de armazenamento
                - Status "idle"
        """
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
        """Para o agente e força a entrega final da colheita.
        
        Adiciona um comportamento de entrega forçada antes de parar o agente,
        garantindo que toda a colheita acumulada seja entregue ao Storage Agent
        antes do shutdown completo.
        
        Note:
            A flag stop_beha=1 força a entrega imediata independentemente
            da quantidade acumulada.
        """
        self.add_behaviour(DeliverHarvestBehaviour(self.sto_jid,stop_beha=1))
        # espera o comportamento terminar
        await asyncio.sleep(3)
        self.logger.info(f"{self.jid} guardou o resto da colheita no agente storage")
        await super().stop()
    
    async def send_propose_task(self, to, cfp_id, distance, fuel_cost):
        """Envia uma proposta de tarefa ao Logistic Agent.
        
        Prepara e retorna uma mensagem de proposta em resposta a um CFP,
        incluindo estimativa de tempo de execução e custo de combustível.
        
        Args:
            to (str): JID do Logistic Agent destinatário.
            cfp_id (str): Identificador único do Call for Proposal.
            distance (int): Distância de Manhattan até a zona alvo.
            fuel_cost (float): Custo estimado de combustível para a tarefa.
            
        Returns:
            Message: Objeto de mensagem SPADE com performativa PROPOSE_TASK
                contendo:
                - sender_id: JID do Harvester
                - receiver_id: JID do destinatário
                - cfp_id: Identificador do CFP
                - eta_ticks: Tempo estimado em ticks (mínimo 1)
                - fuel_cost: Custo de combustível
                
        Note:
            O ETA é calculado como: (distance * 2 * 5 / 10) ticks
        """

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
        """Envia uma rejeição de proposta ao Logistic Agent.
        
        Cria uma mensagem de rejeição em resposta a um CFP ou proposta,
        indicando que o Harvester não pode aceitar a tarefa.
        
        Args:
            to (str): JID do Logistic Agent destinatário.
            cfp_id (str): Identificador único do CFP a ser rejeitado.
            
        Returns:
            Message: Objeto de mensagem SPADE com performativa REJECT_PROPOSAL
                contendo:
                - sender_id: JID do Harvester
                - receiver_id: JID do destinatário
                - cfp_id: Identificador do CFP
                - decision: "reject"
        """

        body = {
            "sender_id": str(self.jid),
            "receiver_id": str(to),
            "cfp_id": cfp_id,
            "decision": "reject"
        }
        msg = make_message(to, PERFORMATIVE_REJECT_PROPOSAL, body)
        return msg

    async def send_accept_proposal(self, to, cfp_id):
        """Envia uma aceitação de proposta ao Logistic Agent.
        
        Utilizado principalmente no contexto de reabastecimento, esta função
        cria uma mensagem indicando que o Harvester aceita a proposta recebida.
        
        Args:
            to (str): JID do Logistic Agent destinatário.
            cfp_id (str): Identificador único do CFP a ser aceite.
            
        Returns:
            Message: Objeto de mensagem SPADE com performativa ACCEPT_PROPOSAL
                contendo:
                - sender_id: JID do Harvester
                - receiver_id: JID do destinatário
                - cfp_id: Identificador do CFP
                - decision: "accept"
        """
        body = {
            "sender_id": str(self.jid),
            "receiver_id": str(to),
            "cfp_id": cfp_id,
            "decision": "accept"
        }
        msg = make_message(to, PERFORMATIVE_ACCEPT_PROPOSAL, body)
        return msg

    async def send_done(self, to, cfp_id, details):
        """Envia mensagem de conclusão de tarefa ao Logistic Agent.
        
        Notifica o Logistic Agent que a tarefa associada ao CFP foi
        concluída com sucesso, incluindo detalhes sobre a execução.
        
        Args:
            to (str): JID do Logistic Agent destinatário.
            cfp_id (str): Identificador único do CFP concluído.
            details (dict): Dicionário com detalhes da execução, podendo incluir:
                - Para colheita:
                    - harvested_amount (float): Quantidade colhida
                    - fuel_used (float): Combustível consumido
                - Para plantação:
                    - seeds_used (int): Sementes utilizadas
                    - fuel_used (float): Combustível consumido
                    
        Returns:
            Message: Objeto de mensagem SPADE com performativa DONE contendo:
                - sender_id: JID do Harvester
                - receiver_id: JID do destinatário
                - cfp_id: Identificador do CFP
                - status: "done"
                - details: Informações detalhadas da execução
        """

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
        """Envia mensagem de falha de tarefa ao Logistic Agent.
        
        Notifica o Logistic Agent que a tarefa associada ao CFP falhou
        durante a execução ou não pode ser completada.
        
        Args:
            to (str): JID do Logistic Agent destinatário.
            cfp_id (str): Identificador único do CFP que falhou.
            
        Returns:
            Message: Objeto de mensagem SPADE com performativa FAILURE contendo:
                - sender_id: JID do Harvester
                - receiver_id: JID do destinatário
                - cfp_id: Identificador do CFP
                - status: "failed"
        """

        body = {
            "sender_id": str(self.jid),
            "receiver_id": str(to),
            "cfp_id": cfp_id,
            "status": "failed"
        }
        msg = make_message(to, PERFORMATIVE_FAILURE, body)
        return msg

    async def send_inform_harvest(self, to, amount_type_list):
        """Envia uma mensagem inform_harvest para o agente Storage.
        
        Notifica o Storage Agent sobre a colheita a ser entregue, incluindo
        os tipos e quantidades de sementes colhidas.
        
        Args:
            to (str): JID do Storage Agent destinatário.
            amount_type_list (list): Lista de dicionários contendo:
                - seed_type (int): Tipo de semente (0-5)
                - amount (float): Quantidade colhida desse tipo
                
        Returns:
            Message: Objeto de mensagem SPADE com performativa INFORM_HARVEST
                contendo:
                - sender_id: JID do Harvester
                - receiver_id: JID do Storage
                - inform_id: Identificador único da entrega
                - amount_type: Lista de tipos e quantidades
                - checked_at: Timestamp da criação da mensagem
                
        Note:
            Esta mensagem é enviada quando o yield_seed atinge 100 unidades
            de qualquer tipo ou durante o shutdown do agente.
        """
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
        """Configura e inicia todos os comportamentos do HarvesterAgent.
        
        Inicializa e adiciona todos os comportamentos necessários para o
        funcionamento autónomo do agente, incluindo monitorização de recursos,
        receção de CFPs, processamento de propostas e gestão de colheitas.
        
        Comportamentos adicionados:
            1. CheckResourcesBehaviour (período: 10s):
                - Monitoriza combustível e sementes
                - Inicia negociação de reabastecimento quando necessário
                
            2. CFPTaskReceiver:
                - Recebe CFPs de tarefas de colheita/plantação
                - Avalia viabilidade e responde com propostas
                
            3. ProposalResponseReceiver:
                - Processa aceitações/rejeições de propostas
                - Inicia execução de tarefas aceites
                
            4. HarvestYieldBehaviour (período: 15s):
                - Verifica níveis de colheita acumulada
                - Inicia processo de entrega ao Storage
                
            5. InformReceivedReceiver:
                - Recebe confirmações de entrega do Storage
                - Atualiza inventários após confirmação
                
        Note:
            Este método é chamado automaticamente pelo SPADE quando o
            agente é iniciado.
        """
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
