"""
Módulo DroneAgent para monitorização e gestão aérea de culturas agrícolas.

Este módulo implementa um agente autónomo tipo drone que patrulha zonas agrícolas,
monitorizando o estado das culturas, aplicando pesticidas quando necessário e
coordenando-se com agentes de logística para reabastecimento de recursos.
"""

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
    """
    Comportamento para processar confirmações e falhas de tarefas de reabastecimento.
    
    Este comportamento aguarda mensagens de confirmação (Done) ou falha (failure)
    dos agentes de logística após solicitações de recarga de bateria ou
    reabastecimento de pesticida.
    
    Attributes:
        timeout_wait (float): Tempo máximo de espera por mensagens em segundos.
    """

    def __init__(self, timeout_wait):
        """
        Inicializa o comportamento de processamento de confirmações.
        
        Args:
            timeout_wait (float): Tempo de espera por mensagens em segundos.
        """
        super().__init__()
        self.timeout_wait = timeout_wait

    async def run(self):
        """
        Processa mensagens de confirmação ou falha de reabastecimento.
        
        Atualiza os recursos do drone (bateria ou pesticida) em caso de sucesso,
        ou regista o erro em caso de falha. Em ambos os casos, retorna o drone
        ao estado 'idle'.
        
        Note:
            - Confirmações (Done) atualizam os recursos do drone
            - Falhas (failure) apenas registam o erro
            - Performativas desconhecidas geram warnings
        """
        # Aceder ao logger do agente para consistência
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
        elif msg.get_metadata("performative") == "failure":
            self.agent.logger.error(f"[DRO] Falha na tarefa de {details.get('resource_type', 'desconhecido')}: {content.get('message', 'Sem detalhes')}")
            self.agent.status = "idle"
        else:
            self.agent.logger.warning(f"[DRO][DoneFailure] Recebida performativa inesperada: {msg.metadata.get('performative')}")


class CFPBehaviour(OneShotBehaviour):
    """
    Comportamento para enviar Call For Proposals (CFP) e selecionar a melhor proposta.
    
    Este comportamento implementa o protocolo FIPA Contract Net simplificado:
    1. Envia CFP para todos os agentes de logística
    2. Aguarda propostas durante timeout_wait
    3. Seleciona a melhor proposta (menor ETA)
    4. Envia accept à proposta escolhida e reject às restantes
    
    Attributes:
        timeout_wait (float): Tempo de espera por propostas em segundos.
        task_type (str): Tipo de tarefa ('battery' ou 'pesticide').
        required_resources (float): Quantidade de recursos necessária.
        priority (str): Prioridade da tarefa.
        task_id (str): Identificador único da tarefa.
        position (tuple): Posição atual do drone (row, col).
    """

    def __init__(self, timeout_wait, task_type, required_resources, priority,position):
        """
        Inicializa o comportamento de CFP.
        
        Args:
            timeout_wait (float): Tempo de espera por propostas em segundos.
            task_type (str): Tipo de recurso solicitado ('battery' ou 'pesticide').
            required_resources (float): Quantidade de recursos necessária.
            priority (str): Prioridade da tarefa (ex: 'High', 'Medium', 'Low').
            position (tuple): Posição do drone para reabastecimento (row, col).
        """
        super().__init__()
        self.timeout_wait = timeout_wait
        self.task_type = task_type
        self.required_resources = required_resources
        self.priority = priority
        self.task_id = f"cfp_{time.time()}"
        self.position = position

    async def run(self):
        """
        Executa o protocolo Contract Net para solicitar reabastecimento.
        
        O processo segue estas etapas:
        1. Envia CFP para todos os agentes de logística
        2. Aguarda propostas durante timeout_wait
        3. Se não houver propostas, retorna ao estado idle
        4. Ordena propostas por ETA (menor primeiro)
        5. Envia accept à melhor proposta e reject às restantes
        
        Note:
            - As propostas são armazenadas em agent.awaiting_proposals
            - Ausência de propostas retorna o agente ao estado idle
        """

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
    """
    Comportamento para receber e armazenar propostas em resposta a CFPs.
    
    Este comportamento aguarda continuamente por mensagens de proposta (propose)
    e armazena-as na estrutura awaiting_proposals do agente, organizadas por cfp_id.
    """
    
    async def run(self):
        """
        Recebe e armazena propostas de agentes de logística.
        
        Propostas são organizadas por cfp_id para posterior seleção pelo
        CFPBehaviour. Propostas para CFPs desconhecidos geram warnings.
        
        Note:
            - Timeout de 2 segundos para evitar bloqueio
            - Propostas inválidas (JSON mal formado) são registadas como erro
            - Propostas para CFPs desconhecidos podem indicar timing issues
        """
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
        

class PatrolBehaviour(PeriodicBehaviour):
    """
    Comportamento periódico de patrulha, monitorização e atuação do drone.
    
    Este é o comportamento principal do drone, responsável por:
    - Gestão de recursos (bateria e pesticida)
    - Patrulha de zonas atribuídas
    - Monitorização do estado das culturas
    - Aplicação de pesticidas quando necessário
    - Comunicação com agentes de logística e ambiente
    
    O comportamento segue uma máquina de estados:
    - idle: Disponível para patrulha
    - flying: Em movimento de patrulha
    - charging: A aguardar reabastecimento
    - handling_task: A executar tarefa (aplicação de pesticida)
    """

    # =====================
    #   FUNÇÕES AUXILIARES DE COMUNICAÇÃO (MOVIDAS DO AGENT)
    # =====================
    async def _get_drone_data(self, row, col):
        """
        Solicita dados de observação aérea ao Environment Agent.
        
        Obtém informações visíveis da célula especificada através de sensores
        de drone (câmara/sensores ópticos).
        
        Args:
            row (int): Índice da linha a observar.
            col (int): Índice da coluna a observar.
            
        Returns:
            tuple: (crop_stage, crop_type, pest_level) ou (None, None, None) em caso de erro.
                - crop_stage (int): Estágio da cultura (0-4)
                - crop_type (int): Tipo de cultura (0-5)
                - pest_level (int): Nível de pragas (0 ou 1)
                
        Note:
            - Timeout de 5 segundos para resposta do Environment Agent
            - Erros de comunicação retornam (None, None, None)
        """
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
        reply = await self.receive(timeout=10)
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
        """
        Informa um agente de logística sobre o estado de uma cultura.
        
        Envia notificação sobre culturas maduras para colheita ou zonas não
        plantadas que necessitam de plantação.
        
        Args:
            row (int): Índice da linha da cultura.
            col (int): Índice da coluna da cultura.
            state (int): Estado da cultura (0=não plantada, 4=madura).
            crop_type (int): Tipo de cultura (0-5), ou None se não plantada.
            
        Note:
            - Seleciona aleatoriamente um agente de logística para informar
            - Timestamp incluído para rastreabilidade
        """
        log_jid = np.random.choice(self.agent.logistics_jid)
        """Envia uma mensagem inform_crop ao Logistics."""
        body = {
            "sender_id": str(self.agent.jid),
            "receiver_id": log_jid,
            "inform_id": f"inform_crop_{time.time()}",
            "zone": [row, col],
            "crop_type": crop_type,
            "state": state,  # "0 -> not planted" ou "1 -> Ready for harvesting"
            "checked_at": time.time(),
        }
        msg = make_message(log_jid, "inform_crop", body)
        await self.send(msg)
        self.agent.logger.info(f"[DRO] Mensagem enviada para {log_jid} (inform_crop).")

    async def _apply_pesticide(self, row, col):
        """
        Aplica pesticida numa célula específica através do Environment Agent.
        
        Verifica disponibilidade de pesticida, solicita aplicação ao ambiente
        e atualiza os recursos do drone em caso de sucesso.
        
        Args:
            row (int): Índice da linha onde aplicar pesticida.
            col (int): Índice da coluna onde aplicar pesticida.
            
        Returns:
            bool: True se a aplicação foi bem-sucedida, False caso contrário.
            
        Note:
            - Requer mínimo de 0.5 kg de pesticida
            - Consome 0.5 kg de pesticida por aplicação
            - Consome 1-3% de bateria por aplicação
            - Timeout de 5 segundos para resposta do Environment Agent
        """
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
        reply = await self.receive(timeout=10)
        if reply:
            try:
                content = json.loads(reply.body)
                if content.get("status") == "success" and content.get("action") == "apply_pesticide":
                    # Se a aplicação for bem-sucedida no ambiente, gasta os recursos do drone
                    self.agent.used_pesticed += 0.5
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
        """
        Executa um ciclo de patrulha, monitorização e atuação.
        
        O comportamento segue esta lógica:
        1. Verifica se já está a recarregar (charging) - se sim, aguarda
        2. Verifica nível de bateria - se baixo, solicita recarga via CFP
        3. Verifica nível de pesticida - se baixo, solicita reabastecimento via CFP
        4. Move-se para a próxima zona de patrulha (consome 0.1-1% bateria)
        5. Obtém dados da cultura na zona atual via drone
        6. Analisa os dados e age conforme necessário:
           - Pragas detetadas → aplica pesticida
           - Cultura madura → informa logística
           - Zona não plantada → informa logística
        7. Retorna ao estado idle e regista recursos
        
        Note:
            - Bateria baixa: < 20%
            - Pesticida baixo: < 3 kg
            - Movimento cíclico através das zonas atribuídas
            - Prioridade: recursos > patrulha
        """
        # 1. Verificar recursos
        if self.agent.status == "charging":
            # Se já estiver a carregar, não faz mais nada
            return
        #self.agent.logger.info(f"{'=' * 35} DRONE {'=' * 35}")
        if self.agent.energy < BATTERY_LOW_THRESHOLD:
            self.agent.logger.warning(f"Bateria baixa ({self.agent.energy:.2f}%). Solicitando recarga.")
            self.agent.status = "charging"
            #self.agent.logger.info(f"{'=' * 35} DRONE {'=' * 35}")
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
            #self.agent.logger.info(f"{'=' * 35} DRONE {'=' * 35}")
            self.agent.add_behaviour(
                CFPBehaviour(
                    timeout_wait=3,
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
            #self.agent.logger.info(f"{'=' * 35} DRONE {'=' * 35}")
            await self._apply_pesticide(row, col)
        
        if crop_stage == 4:
            self.agent.logger.info(f"Cultura madura em ({row},{col}). Informando Logistics.")
            # A chamada foi corrigida para usar o método do Behaviour
            #self.agent.logger.info(f"{'=' * 35} DRONE {'=' * 35}")
            await self._inform_crop(row, col, 4, crop_type)
        
        if crop_stage == 0:
            self.agent.logger.info(f"Zona ({row},{col}) não plantada. Informando Logistics.")
            # A chamada foi corrigida para usar o método do Behaviour
            #self.agent.logger.info(f"{'=' * 35} DRONE {'=' * 35}")
            await self._inform_crop(row, col, 0, None)

        self.agent.status = "idle"
        
        # 5. Log de recursos
        self.agent.logger.info(
            f"Recursos: Energia={self.agent.energy:.2f}%, Pesticida={self.agent.pesticide_amount:.2f}."
        )
        #self.agent.logger.info(f"{'=' * 35} DRONE {'=' * 35}")



class DroneAgent(Agent):
    """
    Agente autónomo tipo drone para monitorização e gestão aérea de culturas.
    
    Este agente patrulha zonas agrícolas atribuídas, monitorizando o estado das
    culturas através de sensores de drone, aplicando pesticidas quando necessário
    e coordenando-se com agentes de logística para reabastecimento de recursos.
    
    Capacidades:
    - Patrulha autónoma de zonas atribuídas
    - Deteção de pragas e aplicação de pesticidas
    - Identificação de culturas maduras para colheita
    - Identificação de zonas não plantadas
    - Gestão automática de recursos (bateria e pesticida)
    - Coordenação com agentes de logística via Contract Net Protocol
    
    Attributes:
        energy (float): Nível de bateria em percentagem (0-100%).
        position (tuple): Posição atual do drone (row, col).
        zones (list): Lista de tuplos (row, col) das zonas de patrulha.
        status (str): Estado atual ('idle', 'flying', 'charging', 'handling_task').
        pesticide_amount (float): Quantidade de pesticida disponível em kg.
        max_pesticide_amount (float): Capacidade máxima de pesticida em kg.
        environment_jid (str): JID do agente Environment.
        logistics_jid (list): Lista de JIDs dos agentes Logistics.
        used_pesticed (float): Total de pesticida usado (estatística).
        awaiting_proposals (dict): Dicionário de propostas aguardando seleção.
        waiting_informs (dict): Estrutura auxiliar para informações pendentes.
    """

    def __init__(self, jid, password, zones, row, col,env_jid, log_jid):
        """
        Inicializa o DroneAgent.
        
        Args:
            jid (str): Jabber ID do agente.
            password (str): Palavra-passe para autenticação XMPP.
            zones (list): Lista de tuplos (row, col) das zonas a patrulhar.
            row (int): Linha da posição inicial.
            col (int): Coluna da posição inicial.
            env_jid (str): JID do agente Environment.
            log_jid (list): Lista de JIDs dos agentes Logistics.
        """
        super().__init__(jid, password)
        logger = logging.getLogger(f"[DRO] {jid}")
        logger.setLevel(logging.INFO)
        self.logger = logger

        self.energy = 100  # Percentagem de bateria
        self.position = (row, col)
        self.zones = zones  # Lista de tuplos (row, col) que o drone patrulha
        self.status = "idle"  # flying, charging, handling_task
        self.pesticide_amount = 10.0  # Quantidade inicial de pesticida em KG
        self.max_pesticide_amount = 10.0
        self.environment_jid = env_jid  # JID do agente Environment
        self.logistics_jid = log_jid  # JID do agente Logistics

        self.used_pesticed = 0

        # Estrutura para armazenar propostas recebidas (por cfp_id)
        self.awaiting_proposals = {}

        self.waiting_informs = {}

    # =====================
    #   SETUP
    # =====================
    async def setup(self):
        """
        Configura e inicia o DroneAgent.
        
        Adiciona os comportamentos principais:
        1. PatrolBehaviour - Patrulha periódica (a cada 10 segundos)
        2. ReceiveProposalsBehaviour - Receção de propostas de logística
        3. DoneFailure (*2) - Processamento de confirmações e falhas
        
        Os templates filtram mensagens por performativa para routing correto.
        
        Note:
            - PatrolBehaviour gere dinamicamente CFPBehaviour quando necessário
            - Múltiplas instâncias de DoneFailure para diferentes performativas
        """
        self.logger.info(f"DroneAgent {self.jid} iniciado. Posição: {self.position}")

        # Adiciona comportamentos principais
        patrol_b = PatrolBehaviour(period=10)  # patrulha a cada 10 ticks
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
        template_fail.set_metadata("performative", "failure")

        # Adiciona o comportamento DoneFailure para esperar pelo resultado

        self.add_behaviour(DoneFailure(timeout_wait=5), template=template_done)
        self.add_behaviour(DoneFailure(timeout_wait=5), template=template_fail)

        # O DoneFailure e o CFPBehaviour são adicionados dinamicamente pelo PatrolBehaviour
        # quando é necessário solicitar uma recarga/reabastecimento.

    async def stop(self):
        """
        Para o agente e regista estatísticas finais.
        
        Regista o total de pesticida usado durante a operação antes de
        terminar o agente.
        """
        self.logger.info(f"{'=' * 35} DRONE {'=' * 35}")
        self.logger.info(f"{self.jid} usou {self.used_pesticed} KG de pesticada")
        self.logger.info(f"{'=' * 35} DRONE {'=' * 35}")
        await super().stop()