"""Módulo do Agente de Logística para gestão de recursos em fazenda inteligente.

Este módulo implementa um agente SPADE responsável por:
- Reabastecimento automático de recursos
- Gestão de CFPs (Call For Proposals) para reabastecimento
- Coordenação de tarefas de plantio e colheita
- Comunicação com Harvester Agents e Drone Agents
"""

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
PERFORMATIVE_INFORM_LOGS = "inform_logs"
PERFORMATIVE_CFP_RECHARGE = "cfp_recharge"
PERFORMATIVE_PROPOSE_RECHARGE = "propose_recharge"
PERFORMATIVE_INFORM_CROP = "inform_crop"
PERFORMATIVE_ACCEPT_PROPOSAL = "accept-proposal"
PERFORMATIVE_REJECT_PROPOSAL = "reject-proposal"
PERFORMATIVE_DONE = "Done"
PERFORMATIVE_FAILURE = "failure"
ONTOLOGY_FARM_ACTION = "farm_action"

MAX_CAPACITY = 1000
# =====================
#   FUNÇÕES AUXILIARES
# =====================

def calculate_distance(pos1, pos2):
    """Calcula a distância de Manhattan entre duas posições.
    
    Args:
        pos1 (tuple): Posição inicial (row, col).
        pos2 (tuple): Posição final (row, col).
    
    Returns:
        int: Distância de Manhattan entre as duas posições.
    """
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

def calculate_eta(distance):
    """Calcula o tempo estimado de chegada (ETA) em segundos.
    
    Assume uma velocidade de 1 unidade/segundo.
    O tempo calculado inclui ida e volta (2 * distância).
    
    Args:
        distance (int): Distância a percorrer.
    
    Returns:
        int: Tempo estimado em segundos (arredondado para cima).
    """
    # 1 unidade de distância = 1 segundo de viagem
    # Tempo total = 2 * distância (ida e volta)
    return ceil(2 * distance)

def get_seasaon(day):
    """Determina a estação do ano com base no dia.
    
    Args:
        day (int): Dia do ano (0-365).
    
    Returns:
        str: Estação do ano ("Spring", "Summer", "Autumn", "Winter").
    """
    if 80 <= day < 172:
        return "Spring"
    elif 172 <= day < 264:
        return "Summer"
    elif 264 <= day < 355:
        return "Autumn"
    else:
        return "Winter"    

def get_probs(season):
    """Calcula probabilidades de plantio por tipo de planta com base na estação.
    
    As probabilidades são ajustadas conforme a estação:
    - Verão: favorece tomate e pimento
    - Inverno: favorece couve e cenoura
    - Outras estações: distribuição uniforme
    
    Args:
        season (str): Estação do ano ("Spring", "Summer", "Autumn", "Winter").
    
    Returns:
        dict: Dicionário {tipo_planta: probabilidade} onde:
            - 0: Tomate
            - 1: Pimento
            - 2: Trigo
            - 3: Couve
            - 4: Alface
            - 5: Cenoura
    """
    plants = {
        0: "Tomate",
        1: "Pimento",
        2: "Trigo",
        3: "Couve",
        4: "Alface",
        5: "Cenoura"
    }

    
    summer = [0, 1]      # Tomate, Pimento
    winter = [3, 5]    # Couve, Cenoura
    any_season = [4, 2]   # Alface, Trigo

    probs = {i: 0.0 for i in plants.keys()}

    if season == "Summer":
        for i in summer:
            probs[i] = 0.25
        for i in any_season:
            probs[i] = 0.15
        for i in winter:
            probs[i] = 0.10

    elif season == "Winter":
        for i in winter:
            probs[i] = 0.25
        for i in any_season:
            probs[i] = 0.15
        for i in summer:
            probs[i] = 0.10
    
    else:
        p = 1.0 / len(plants)  # igual para todas
        for i in probs:
            probs[i] = p

    return probs

def get_seed(probs):
    """Seleciona um tipo de planta aleatoriamente com base nas probabilidades.
    
    Args:
        probs (dict): Dicionário {tipo_planta: probabilidade}.
    
    Returns:
        int: Índice do tipo de planta selecionado (0-5).
    """
    indices = list(probs.keys())
    pesos = [probs[i] for i in indices]

    chosen = random.choices(indices, weights=pesos, k=1)[0]

    return chosen

# =====================
#   BEHAVIOURS
# =====================

class AutoRechargeBehaviour(CyclicBehaviour):
    """Comportamento cíclico para recarga automática de recursos.
    
    Recarrega automaticamente água, fertilizante, bateria, pesticida, 
    combustível e sementes quando o agente está ocioso.
    """

    async def run(self):
        """Executa um ciclo de recarga automática.
        
        Aguarda 5 segundos e, se o agente estiver ocioso, recarrega
        todos os recursos em 10 unidades até o máximo de 1000.
        """
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
    """Recebe e processa mensagens CFP para reabastecimento.
    
    Avalia CFPs recebidos de outros agentes, verifica disponibilidade
    de recursos e envia propostas com ETA e quantidade disponível.
    """

    async def run(self):
        """Processa um CFP de reabastecimento.
        
        Verifica:
        1. Se o agente está disponível
        2. Se tem recursos suficientes
        3. Calcula ETA e envia proposta
        """
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
                if self.agent.status != "idle" or self.agent.status == "await":
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
                self.agent.status = "await"
                msg = await self.agent.send_propose_recharge(sender_jid, cfp_id, eta_ticks, resource_amount)
                await self.send(msg)
                self.agent.logger.info(f"[CFP_RECHARGE] Proposta enviada para {sender_jid}. ETA: {eta_ticks}s, Recursos: {resource_amount}.")
        
            except json.JSONDecodeError:
                self.agent.logger.error(f"[CFP_RECHARGE] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[CFP_RECHARGE] Erro ao processar CFP: {e}")


class AcceptRejectRechargeReceiver(CyclicBehaviour):
    """Recebe aceitações ou rejeições de propostas de reabastecimento.
    
    Processa mensagens ACCEPT_PROPOSAL e REJECT_PROPOSAL,
    iniciando a tarefa de reabastecimento quando aceite.
    """

    async def run(self):
        """Processa uma resposta a uma proposta de reabastecimento.
        
        Se aceite, inicia o RechargeTaskBehaviour.
        Se rejeitada, volta ao estado idle.
        """
        msg = await self.receive(timeout=5)

        if msg:
            try:
                content = json.loads(msg.body)
                cfp_id = content.get("cfp_id")
                sender_jid = str(msg.sender)

                if cfp_id in self.agent.pending_recharge_proposals:
                    if msg.metadata["performative"] == PERFORMATIVE_REJECT_PROPOSAL:
                        self.agent.logger.info(f"[REJECT_RECHARGE] Proposta {cfp_id} rejeitada por {sender_jid}.")
                        self.agent.status = "idle"
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
    """Executa uma tarefa de reabastecimento completa.
    
    Simula viagem até o destino, entrega recursos e retorno à base.
    
    Attributes:
        receiver_jid (str): JID do agente a reabastecer.
        proposal (dict): Detalhes da proposta aceite.
        target_pos (tuple): Posição de destino.
        eta_ticks (int): Tempo estimado total.
        task_type (str): Tipo de recurso a entregar.
        resource_amount (int): Quantidade a entregar.
        seed_type (int): Tipo de semente (se aplicável).
        cfp_id (str): ID do CFP.
    """

    def __init__(self, receiver_jid, proposal):
        """Inicializa o comportamento de reabastecimento.
        
        Args:
            receiver_jid (str): JID do agente destinatário.
            proposal (dict): Dicionário com detalhes da proposta:
                - position: posição de destino
                - eta_ticks: tempo estimado
                - task_type: tipo de recurso
                - resource_amount: quantidade
                - seed_type: tipo de semente (opcional)
                - cfp_id: ID do CFP
        """
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
        """Executa a tarefa de reabastecimento.
        
        Simula:
        1. Viagem até o destino
        2. Entrega de recursos
        3. Atualização de inventário
        4. Envio de mensagem DONE
        5. Retorno à base
        """
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

class InformOtherLogs(OneShotBehaviour):
    """Informa outros Logistic Agents sobre zonas em processamento.
    
    Evita CFPs duplicados informando outros agentes quando uma zona
    está a ser tratada ou quando o tratamento termina.
    
    Attributes:
        zone (tuple): Coordenadas da zona (row, col).
        add_or_remove (int): 1 para adicionar, 0 para remover.
    """
    
    def __init__(self, zone, add_or_remove):
        """Inicializa o comportamento de informação.
        
        Args:
            zone (tuple): Coordenadas da zona.
            add_or_remove (int): 1 para adicionar zona à lista de pendentes,
                                 0 para remover.
        """
        super().__init__()
        self.zone = tuple(zone)  # guarda a zona
        self.add_or_remove = add_or_remove # 0 -> remove    1 -> add

    async def run(self):
        """Envia mensagem INFORM_LOGS para outros Logistic Agents.
        
        Informa todos os outros agentes logísticos sobre o estado
        de processamento da zona.
        """
        for jid in self.agent.log_jid:
            if str(jid) != str(self.agent.jid):
                msg = make_message(
                    to = str(jid),
                    performative = PERFORMATIVE_INFORM_LOGS,
                    body_dict={
                        "cfp_id": f"cfp_inform_log_{time.time()}",
                        "zone": self.zone,
                        "add_or_remove": self.add_or_remove
                    }
                )
                await self.send(msg)
                self.agent.logger.info(f"[INFORM_LOG] Zona {self.zone} enviada para {jid}.")
        return
        
class ReceiveInformOtherLogs(CyclicBehaviour):
    """Recebe informações sobre zonas em processamento de outros Logistic Agents.
    
    Atualiza a lista local de tarefas pendentes para evitar
    processamento duplicado de zonas.
    """

    async def run(self):
        """Processa mensagens INFORM_LOGS.
        
        Adiciona ou remove zonas da lista de tarefas pendentes
        conforme a informação recebida.
        """
        msg = await self.receive(timeout=5)

        if msg:
            try:
                content = json.loads(msg.body)
                zone = tuple(content.get("zone"))
                add_or_remove = content.get("add_or_remove")
                if add_or_remove:
                    self.agent.pending_crop_tasks[zone] = {}
                    self.agent.logger.info(f"[INFORM_LOG] Zona {zone} adicionada à lista")
                else:
                    del self.agent.pending_crop_tasks[zone] 
                    self.agent.logger.info(f"[INFORM_LOG] Zona {zone} removida da lista")
            except json.JSONDecodeError:
                self.agent.logger.error(f"[INFORM_LOG] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[INFORM_LOG] Erro ao processar INFORM_CROP: {e}")


class InformCropReceiver(CyclicBehaviour):
    """Recebe pedidos de plantio/colheita do Drone Agent.
    
    Processa informações sobre o estado das culturas e inicia
    processos de CFP para Harvester Agents conforme necessário.
    """

    async def run(self):
        """Processa mensagens INFORM_CROP do Drone Agent.
        
        Analisa o estado da zona e:
        - Se não plantada (state=0): inicia CFP para plantio
        - Se pronta para colheita (state=4): inicia CFP para colheita
        - Evita processar zonas já em tratamento
        """

        if self.agent.status == "await": 
            return

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
                
                inform_log = InformOtherLogs(zone,1)
                self.agent.add_behaviour(inform_log)
                
                # 3. Decidir a ação e iniciar o processo de CFP
                if state == 0: # not planted -> Plantar
                    task_type = "plant_application"
                    # Escolher semente aleatoriamente

                    day = self.agent.field.day
                    season = get_seasaon(day)
                    probs = get_probs(season)
                    seed_type = get_seed(probs)
                    #print(f"Estação: {season}, Probabilidades: {probs}, Semente escolhida: {seed_type}")
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

                    inform_log = InformOtherLogs(zone,0)
                    self.agent.add_behaviour(inform_log)

            except json.JSONDecodeError:
                self.agent.logger.error(f"[INFORM_CROP] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[INFORM_CROP] Erro ao processar INFORM_CROP: {e}")


class CFPTaskInitiator(OneShotBehaviour):
    """Inicia processo de CFP para tarefas de plantio ou colheita.
    
    Envia CFPs para todos os Harvester Agents disponíveis e
    inicia o processo de recepção e avaliação de propostas.
    
    Attributes:
        zone (tuple): Coordenadas da zona.
        task_type (str): Tipo de tarefa ("plant_application" ou "harvest_application").
        seed_or_crop_type (int): Tipo de semente ou cultura.
        cfp_id (str): ID único do CFP.
    """

    def __init__(self, zone, task_type, seed_or_crop_type):
        """Inicializa o iniciador de CFP.
        
        Args:
            zone (tuple): Coordenadas da zona a tratar.
            task_type (str): Tipo de tarefa a executar.
            seed_or_crop_type (int): Tipo de semente (plantio) ou cultura (colheita).
        """
        super().__init__()
        self.zone = zone
        self.task_type = task_type
        self.seed_or_crop_type = seed_or_crop_type
        self.cfp_id = f"cfp_task_{time.time()}"

    async def run(self):
        """Envia CFPs para todos os Harvester Agents.
        
        Define recursos necessários e inicia comportamento
        de recepção de propostas (CFPTaskReceiver).
        """
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
                    "seed_type": self.seed_or_crop_type,
                    "zone": list(self.zone),
                    "required_resources": required_resources,
                    "priority": "Medium"
                }
            )
            await self.send(msg)
            self.agent.logger.info(f"[CFP_INIT] CFP enviado para {harv_jid}.")

        # Esperar pelas propostas
        self.agent.add_behaviour(CFPTaskReceiver(self.cfp_id, self.zone, self.task_type, self.seed_or_crop_type), template=Template(metadata={"performative": "propose_task"}))


class CFPTaskReceiver(CyclicBehaviour):
    """Recebe e avalia propostas dos Harvester Agents.
    
    Recebe propostas durante um período de timeout, seleciona
    a melhor com base no ETA e envia aceitação/rejeição.
    
    Attributes:
        cfp_id (str): ID do CFP.
        zone (tuple): Coordenadas da zona.
        task_type (str): Tipo de tarefa.
        seed_or_crop_type (int): Tipo de semente ou cultura.
        proposals (dict): Propostas recebidas {jid: {eta, cost}}.
        timeout (float): Timestamp do timeout.
    """

    def __init__(self, cfp_id, zone, task_type, seed_or_crop_type):
        """Inicializa o receptor de propostas.
        
        Args:
            cfp_id (str): ID do CFP a processar.
            zone (tuple): Coordenadas da zona.
            task_type (str): Tipo de tarefa.
            seed_or_crop_type (int): Tipo de semente ou cultura.
        """
        super().__init__()
        self.cfp_id = cfp_id
        self.zone = zone
        self.task_type = task_type
        self.seed_or_crop_type = seed_or_crop_type
        self.proposals = {}
        self.timeout = time.time() + 2 # Tempo limite para receber propostas

    async def run(self):
        """Recebe propostas e seleciona a melhor após timeout.
        
        Processo:
        1. Recebe propostas durante o período de timeout
        2. Ao atingir timeout, avalia propostas
        3. Seleciona Harvester com menor ETA
        4. Envia ACCEPT ao vencedor e REJECT aos demais
        5. Inicia TaskDoneReceiver para aguardar conclusão
        """
        # 1. Receber propostas
        self.agent.status = "await"
        msg = await self.receive(timeout=1)
        if msg:
            try:
                content = json.loads(msg.body)
                cfp_id = content.get("cfp_id")
                eta_ticks = content.get("eta_ticks")
                fuel_cost = content.get("fuel_cost") 
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
                    self.agent.status = "idle"
                    del self.agent.pending_crop_tasks[self.zone]

                    inform_log = InformOtherLogs(self.zone,0)
                    self.agent.add_behaviour(inform_log)

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
            self.agent.status = "idle"
            template_accept = Template()
            template_accept.set_metadata("performative", PERFORMATIVE_DONE)

            template_failure = Template()
            template_failure.set_metadata("performative", PERFORMATIVE_FAILURE)

            self.agent.add_behaviour(TaskDoneReceiver(self.cfp_id, self.zone), template=template_accept)
            self.agent.add_behaviour(TaskDoneReceiver(self.cfp_id, self.zone), template=template_failure)
            
            self.kill()


class TaskDoneReceiver(CyclicBehaviour):
    """Recebe mensagens DONE do Harvester Agent após conclusão de tarefas.
    
    Attributes:
        cfp_id: ID da Call for Proposals.
        zone: Zona do campo onde a tarefa foi executada.
    """

    def __init__(self, cfp_id, zone):
        """Inicializa o TaskDoneReceiver.
        
        Args:
            cfp_id (str): Identificador único da CFP.
            zone (tuple): Tupla (row, col) representando a zona da tarefa.
        """
        super().__init__()
        self.cfp_id = cfp_id
        self.zone = zone

    async def run(self):
        """Executa o ciclo de recepção de mensagens DONE.
        
        Aguarda mensagens com performative DONE, processa o status da tarefa
        (done ou failure), remove a tarefa da lista de pendentes e notifica
        outros agentes através do InformOtherLogs behaviour.
        
        Returns:
            None
            
        Raises:
            json.JSONDecodeError: Se o corpo da mensagem não for JSON válido.
            Exception: Outros erros durante o processamento da mensagem.
        """
        template = Template()
        template.set_metadata("performative", PERFORMATIVE_DONE)
        msg = await self.receive(timeout=5)

        if msg:
            try:
                content = json.loads(msg.body)
                cfp_id = content.get("cfp_id")
                sender_jid = str(msg.sender)
                status = content.get("status")

                if cfp_id == self.cfp_id:

                    if status == "done":
                        self.agent.logger.info(f"[TASK_DONE] Recebido DONE de {sender_jid} para CFP {cfp_id} na zona {self.zone}.")
                        
                        # Remover a tarefa da lista de pendentes
                        if self.zone in self.agent.pending_crop_tasks:
                            del self.agent.pending_crop_tasks[self.zone]
                            self.agent.logger.info(f"[TASK_DONE] Tarefa da zona {self.zone} removida da lista de pendentes.")
                    
                    else:
                        self.agent.logger.info(f"[TASK_FAILURE] Recebido FAILURE de {sender_jid} para CFP {cfp_id} na zona {self.zone}.")
                        if self.zone in self.agent.pending_crop_tasks:
                            del self.agent.pending_crop_tasks[self.zone]
                            self.agent.logger.info(f"[TASK_FAILURE] Tarefa da zona {self.zone} removida da lista de pendentes.")
                    
                    
                    inform_log = InformOtherLogs(self.zone,0)
                    self.agent.add_behaviour(inform_log)
                    self.kill()

            except json.JSONDecodeError:
                self.agent.logger.error(f"[TASK_FAILURE] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[TASK_FAILURE] Erro ao processar DONE: {e}")


# =====================
#   AGENT
# =====================

class LogisticsAgent(Agent):
    """Agente de logística responsável por gestão de recursos e reabastecimento.
    
    O LogisticsAgent coordena o fornecimento de recursos (água, fertilizantes,
    sementes, etc.) para outros agentes do sistema, processando CFPs de
    reabastecimento e gerindo tarefas de cultivo.
    
    Attributes:
        field (Field): Representação do campo agrícola.
        harv_jid (str): JID do Harvester Agent.
        log_jid (str): JID de outros Logistics Agents.
        position (tuple): Posição atual (row, col) do agente.
        status (str): Estado atual do agente (idle, moving, handling_task, await).
        water_storage (int): Quantidade de água armazenada.
        fertilizer_storage (int): Quantidade de fertilizante armazenada.
        battery_storage (int): Quantidade de bateria armazenada.
        pesticide_storage (int): Quantidade de pesticida armazenada.
        fuel_storage (int): Quantidade de combustível armazenada.
        seed_storage (dict): Dicionário mapeando tipo de semente para quantidade.
        pending_recharge_proposals (dict): Propostas de reabastecimento pendentes.
        pending_crop_tasks (dict): Tarefas de cultivo pendentes por zona.
    """
    def __init__(self, jid, password, harv_jid, log_jid, row, col, field):
        """Inicializa o LogisticsAgent.
        
        Args:
            jid (str): Jabber ID do agente.
            password (str): Password para autenticação.
            harv_jid (str): JID do Harvester Agent.
            log_jid (str): JID de outros Logistics Agents.
            row (int): Coordenada de linha da posição inicial.
            col (int): Coordenada de coluna da posição inicial.
            field (Field): Objeto representando o campo agrícola.
        """

        super().__init__(jid, password)

        self.logger = logging.getLogger(f"[LOG] {jid}")
        self.logger.setLevel(logging.INFO)
        
        self.field = field  # Representação do campo 

        self.harv_jid = harv_jid
        self.log_jid = log_jid
        self.position = (row, col)
        self.status = "idle"  # idle, moving, handling_task, await

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
        
        # Estado de gestão de tarefas
        self.pending_recharge_proposals = {} # {cfp_id: proposal_details}
        self.pending_crop_tasks = {} # {zone: {"crop_type": ..., "state": ..., "harvester_jid": ...}}


    async def setup(self):
        """Configura e inicializa os behaviours do agente.
        
        Adiciona os behaviours necessários para:
        - Reabastecimento automático (AutoRechargeBehaviour)
        - Recepção de CFPs de reabastecimento (CFPRechargeReceiver)
        - Aceitação/rejeição de propostas (AcceptRejectRechargeReceiver)
        - Recepção de informações de cultivo (InformCropReceiver)
        - Recepção de informações de outros logs (ReceiveInformOtherLogs)
        
        Returns:
            None
        """
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
        template.set_metadata("performative", PERFORMATIVE_INFORM_CROP)
        self.add_behaviour(InformCropReceiver(), template=template)


        template = Template()
        template.set_metadata("performative",PERFORMATIVE_INFORM_LOGS)
        self.add_behaviour(ReceiveInformOtherLogs(), template=template)

    # =====================
    #   FUNÇÕES DE ENVIO DE MENSAGENS
    # =====================
    async def stop(self):
        """Para o agente de forma assíncrona.
        
        Returns:
            None
        """
        await super().stop()

    async def send_propose_recharge(self, to, cfp_id, eta_ticks, resources):
        """Envia uma proposta de reabastecimento para outro agente.
        
        Cria e envia uma mensagem PROPOSE_RECHARGE com detalhes sobre
        disponibilidade de recursos, ETA e prioridade. Armazena a proposta
        na lista de propostas pendentes.
        
        Args:
            to (str): JID do agente destinatário.
            cfp_id (str): Identificador único da CFP.
            eta_ticks (int): Tempo estimado de chegada em ticks.
            resources (dict): Dicionário com recursos disponíveis.
            
        Returns:
            Message: Objeto mensagem SPADE preparado para envio.
        """
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
        """Envia uma mensagem de aceitação de proposta.
        
        Args:
            to (str): JID do agente destinatário.
            cfp_id (str): Identificador único da CFP.
            
        Returns:
            Message: Objeto mensagem SPADE de aceitação.
        """
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
        """Envia uma mensagem de rejeição de proposta.
        
        Args:
            to (str): JID do agente destinatário.
            cfp_id (str): Identificador único da CFP.
            
        Returns:
            Message: Objeto mensagem SPADE de rejeição.
        """
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
        """Envia uma mensagem de confirmação de conclusão de tarefa.
        
        Args:
            to (str): JID do agente destinatário.
            cfp_id (str): Identificador único da CFP.
            details (dict): Detalhes adicionais sobre a conclusão da tarefa.
            
        Returns:
            Message: Objeto mensagem SPADE de confirmação.
        """
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