import asyncio
import json
import logging
import random
import time

from spade.agent import Agent
from spade.behaviour import PeriodicBehaviour, OneShotBehaviour, CyclicBehaviour
from spade.template import Template
from agents.message import make_message

# --- Constantes ---
# Limiares
MOISTURE_THRESHOLD = 50  # Humidade abaixo deste valor dispara irrigação
NUTRIENTS_THRESHOLD = 70  # Nutrientes abaixo deste valor dispara fertilização
MIN_ENERGY_FOR_SCAN = 2.0 # Energia mínima para iniciar um scan (2% é o máximo de perda)

# Protocolos e Ontologias
PERFORMATIVE_DONE = "Done"
PERFORMATIVE_CFP = "cfp_task"
PROTOCOL_INFORM = "inform"
ONTOLOGY_FARM_DATA = "farm_data"
ONTOLOGY_FARM_ACTION = "farm_action"

# --- Funções Auxiliares ---

def calculate_energy_loss():
    """Calcula a perda de energia aleatória entre 1% e 2%."""
    return random.uniform(0.0, 1.0)

# --- Comportamentos ---

class ScanBehaviour(PeriodicBehaviour):
    """
    Comportamento principal para realizar o scan, verificar o estado e tomar decisões.
    """
    def __init__(self, period, row, col, env_jid):
        super().__init__(period)
        self.row = row
        self.col = col
        self.env_jid = env_jid
        self.task_in_progress = False # Flag para garantir que só faz um scan de cada vez

    async def on_start(self):
        self.agent.logger.info("ScanBehaviour iniciado.")

    async def run(self):
        # 1. Verificar se há tarefa em curso (irrigação/fertilização)
        if self.agent.status != "idle":
            #self.agent.logger.info(f"Tarefa em curso ({self.agent.status}). A aguardar 'done' antes de novo scan.")
            return

        # 2. Verificar Energia
        if self.agent.energy < MIN_ENERGY_FOR_SCAN:
            self.agent.logger.warning(f"Energia baixa ({self.agent.energy:.2f}%). A solicitar recarga.")
            self.agent.status = "charging"
            template = Template()
            template.set_metadata("performative", "propose_recharge")
            self.agent.add_behaviour(RequestRecharge(period=None, template = template))
            return

        # 3. Consumir Energia
        loss = calculate_energy_loss()
        self.agent.energy -= loss
        self.agent.logger.info(f"Energia consumida: {loss:.2f}%. Energia restante: {self.agent.energy:.2f}%.")

        # 4. Realizar Scan (Pedir dados ao Environment Agent)
        self.agent.logger.info(f"A realizar scan na coluna {self.col}...")
        
        # O Field.py implementa get_soil(row, col) para retornar a média da coluna 'col'
        body = {"action": "get_soil", "row": self.row, "col": self.col}
        msg = make_message(
            to=self.env_jid,
            performative="request",
            body_dict=body,
            protocol=PROTOCOL_INFORM,
            language="json"
        )
        msg.set_metadata("ontology", ONTOLOGY_FARM_DATA)
        await self.send(msg)
        
        # 5. Adicionar o comportamento para receber a resposta do Environment Agent
        template = Template()
        template.set_metadata("performative", "inform")
        template.set_metadata("ontology", ONTOLOGY_FARM_DATA)
        self.agent.add_behaviour(ReceiveDataBehaviour(), template = template)


class ReceiveDataBehaviour(OneShotBehaviour):
    """
    Comportamento para receber a resposta do Environment Agent após o scan.
    """
    async def run(self):
        # Espera pela mensagem de resposta do Environment Agent
        template = Template()
        template.set_metadata("performative", "inform")
        template.set_metadata("ontology", ONTOLOGY_FARM_DATA)
        
        msg = await self.receive(timeout=5)
        
        if not msg:
            self.agent.logger.error("Não foi recebida resposta do Environment Agent após o scan.")
            self.agent.status = "idle"
            return

        try:
            content = json.loads(msg.body)
            if content.get("status") == "error":
                self.agent.logger.error(f"Erro no scan: {content.get('message')}")
                self.agent.status = "idle"
                return

            data = content.get("data")
            temp = data.get("temperature")
            nutr = data.get("nutrients")
            mois = data.get("moisture")
            
            self.agent.last_value = {"temp": temp, "nutr": nutr, "mois": mois}
            self.agent.logger.info(f"Scan concluído. T: {temp:.2f}, N: {nutr:.2f}, M: {mois:.2f}")

            # 1. Verificar Humidade
            if mois < MOISTURE_THRESHOLD:
                self.agent.logger.warning(f"Humidade baixa ({mois:.2f}). A iniciar CFP para Irrigação.")
                self.agent.status = "irrigating"
                self.agent.add_behaviour(CallForProposal(
                    task_type="irrigation_application", 
                    agents_jids=self.agent.irrig_jid, 
                    required_resource={"type": "water", "amount": 4} # Valor placeholder
                ))
                return

            # 2. Verificar Nutrientes
            if nutr < NUTRIENTS_THRESHOLD:
                self.agent.logger.warning(f"Nutrientes baixos ({nutr:.2f}). A iniciar CFP para Fertilização.")
                self.agent.status = "fertilizing"
                self.agent.add_behaviour(CallForProposal(
                    task_type="fertilize_application", 
                    agents_jids=self.agent.fert_jid, 
                    required_resource={"type": "fertilizer", "amount": 1} # Valor placeholder
                ))
                return

            # 3. Tudo OK
            self.agent.logger.info("Condições ideais. A aguardar próximo scan.")
            self.agent.status = "idle"

        except json.JSONDecodeError:
            self.agent.logger.error(f"Erro ao descodificar JSON da resposta do Environment Agent: {msg.body}")
            self.agent.status = "idle"
        except Exception as e:
            self.agent.logger.exception(f"Erro ao processar dados do scan: {e}")
            self.agent.status = "idle"


class CallForProposal(OneShotBehaviour):
    """
    Comportamento para iniciar um CFP (Contract-Net Protocol) para uma tarefa.
    """
    def __init__(self, task_type, agents_jids, required_resource):
        super().__init__()
        self.task_type = task_type
        self.agents_jids = agents_jids
        self.required_resource = required_resource
        self.cfp_id = f"cfp_{task_type}_{time.time()}"

    async def run(self):
        self.agent.logger.info(f"A enviar CFP ({self.task_type}) com ID: {self.cfp_id}")
        
        # 1. Enviar CFP para todos os agentes
        body = {
            "cfp_id": self.cfp_id,
            "task_type": self.task_type,
            "zone": [self.agent.position[0], self.agent.position[1]],
            "required_resources": [self.required_resource],
            "priority": "High",
            "sender_id": str(self.agent.jid)
        }
        for jid in self.agents_jids:
            msg = make_message(
                to=jid,
                performative=PERFORMATIVE_CFP,
                body_dict=body,
            )
            await self.send(msg)
        # 2. Receber Propostas
        proposals = []
        timeout = 5 # Tempo para receber propostas
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            template = Template()
            template.set_metadata("performative", "propose_task")
            
            # Filtra apenas propostas para este CFP
            msg = await self.receive(timeout=1) 
            
            if msg:
                try:
                    content = json.loads(msg.body)
                    # Verifica se o CFP ID corresponde
                    if content.get("cfp_id") == self.cfp_id:
                        proposals.append({
                            "sender": str(msg.sender),
                            "eta": content.get("eta_ticks", float('inf')),
                            "battery_lost": content.get("battery_lost", float('inf'))
                        })
                        self.agent.logger.info(f"Proposta recebida de {msg.sender}: ETA={content.get('eta_ticks')}, Bateria={content.get('battery_lost')}")
                except json.JSONDecodeError:
                    self.agent.logger.error(f"Erro ao descodificar proposta: {msg.body}")
            
            await asyncio.sleep(0.1) # Pequena pausa para não bloquear

        if not proposals:
            self.agent.logger.warning(f"Nenhuma proposta recebida para {self.task_type}. A retornar ao estado idle.")
            self.agent.status = "idle"
            return

        # 3. Selecionar a Melhor Proposta (Critério: Menor ETA)
        best_proposal = min(proposals, key=lambda p: p["eta"])
        
        self.agent.logger.info(f"Melhor proposta selecionada: {best_proposal['sender']} (ETA: {best_proposal['eta']})")

        # 4. Enviar Aceitação e Rejeição
        for proposal in proposals:
            performative = "accept-proposal" if proposal["sender"] == best_proposal["sender"] else "reject-proposal"
            
            body = {
                "cfp_id": self.cfp_id,
                "decision": performative.split('-')[0],
                "sender_id": str(self.agent.jid)
            }
            
            msg = make_message(
                to=proposal["sender"],
                performative=performative,
                body_dict=body,
            )
            await self.send(msg)
            
            if performative == "accept-proposal":
                self.agent.current_task = {"cfp_id": self.cfp_id, "agent": proposal["sender"], "type": self.task_type}
                self.agent.logger.info(f"Aceitação enviada para {proposal['sender']}. A aguardar 'Done'.")
            else:
                self.agent.logger.info(f"Rejeição enviada para {proposal['sender']}.")


class RequestRecharge(OneShotBehaviour):
    """
    Comportamento para solicitar recarga de bateria aos Logistic Agents.
    """
    def __init__(self, period=None):
        super().__init__()
        self.cfp_id = f"cfp_recharge_{time.time()}"

    async def run(self):
        self.agent.logger.info(f"A enviar CFP de Recarga (Bateria) com ID: {self.cfp_id}")
        
        # 1. Enviar CFP para todos os Logistic Agents
        body = {
            "cfp_id": self.cfp_id,
            "task_type": "battery",
            "required_resources": 100 - self.agent.energy, # Pedir o que falta para 100%
            "position": self.agent.position,
            "priority": "Urgent",
            "sender_id": str(self.agent.jid)
        }
        
        for jid in self.agent.log_jid:
            msg = make_message(
                to=jid,
                performative="cfp_recharge",
                body_dict=body,
            )
            await self.send(msg)

        # 2. Receber Propostas (Propose_recharge)
        proposals = []
        timeout = 5
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            
            msg = await self.receive(timeout=1) 
            
            if msg:
                try:
                    content = json.loads(msg.body)
                    if content.get("cfp_id") == self.cfp_id:
                        proposals.append({
                            "sender": str(msg.sender),
                            "eta": content.get("eta_ticks", float('inf')),
                            "resources": content.get("resources", 0)
                        })
                        self.agent.logger.info(f"Proposta de recarga recebida de {msg.sender}: ETA={content.get('eta_ticks')}")
                except json.JSONDecodeError:
                    self.agent.logger.error(f"Erro ao descodificar proposta de recarga: {msg.body}")
            
            await asyncio.sleep(0.1)

        if not proposals:
            self.agent.logger.error("Nenhuma proposta de recarga recebida. A tentar novamente no próximo ciclo.")
            self.agent.status = "idle" # Volta a idle para tentar de novo no próximo scan
            return

        # 3. Selecionar a Melhor Proposta (Critério: Menor ETA)
        best_proposal = min(proposals, key=lambda p: p["eta"])
        
        self.agent.logger.info(f"Melhor proposta de recarga selecionada: {best_proposal['sender']} (ETA: {best_proposal['eta']})")

        # 4. Enviar Aceitação e Rejeição
        for proposal in proposals:
            performative = "accept-proposal" if proposal["sender"] == best_proposal["sender"] else "reject-proposal"
            
            body = {
                "cfp_id": self.cfp_id,
                "decision": performative.split('-')[0],
                "sender_id": str(self.agent.jid)
            }
            
            msg = make_message(
                to=proposal["sender"],
                performative=performative,
                body_dict=body,
            )
            await self.send(msg)
            
            if performative == "accept-proposal":
                self.agent.current_task = {"cfp_id": self.cfp_id, "agent": proposal["sender"], "type": "recharge"}
                self.agent.logger.info(f"Aceitação de recarga enviada para {proposal['sender']}. A aguardar 'Done'.")
            else:
                self.agent.logger.info(f"Rejeição de recarga enviada para {proposal['sender']}.")


class ReceiveDoneBehaviour(CyclicBehaviour):
    """
    Comportamento cíclico para receber mensagens 'Done' e atualizar o estado do agente.
    """
    async def run(self):
        # Template para receber 'Done' de qualquer agente
        
        msg = await self.receive(timeout=5)
        
        if msg:
            try:
                content = json.loads(msg.body)
                cfp_id = content.get("cfp_id")
                sender = str(msg.sender)
                details = content.get("details", {}) 
                
                self.agent.logger.info(f"Mensagem 'Done' recebida de {sender} para CFP ID: {cfp_id}")

                # 1. Verificar se o 'Done' é para a tarefa atual
                if self.agent.current_task and self.agent.current_task["cfp_id"] == cfp_id:
                    task_type = self.agent.current_task["type"]
                    
                    if task_type == "recharge":
                        # 2. Aumentar a energia (o Logistic Agent deve ter feito a recarga)
                        # Assumimos que a recarga é total para simplificar, ou podemos usar um valor do 'details'
                        self.agent.energy += details.get("amount_delivered")
                        self.agent.logger.info(f"Recarga de bateria concluída. Energia atual: {self.agent.energy:.2f}%.")
                        
                    elif task_type in ["irrigation_application", "fertilize_application"]:
                        self.agent.logger.info(f"Tarefa de {task_type} concluída com sucesso.")
                        
                    # 3. Resetar o estado e a tarefa
                    self.agent.status = "idle"
                    self.agent.current_task = None
                    self.agent.logger.info("Agente regressa ao estado 'idle'. Pronto para o próximo scan.")
                    
                else:
                    self.agent.logger.warning(f"Mensagem 'Done' recebida para CFP ID desconhecido ou não ativo: {cfp_id}")

            except json.JSONDecodeError:
                self.agent.logger.error(f"Erro ao descodificar JSON do 'Done': {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"Erro ao processar mensagem 'Done': {e}")
        
        # Pequena pausa para não consumir CPU
        await asyncio.sleep(0.1)


# --- Agente Principal ---

class SoilSensorAgent(Agent):

    def __init__(self,jid,password,log_jid,irrig_jid,fert_jid,env_jid,row,col):
        super().__init__(jid,password)
        
        # Configuração de Logging
        self.logger = logging.getLogger(f"[SOIL] {jid}")
        self.logger.setLevel(logging.INFO)

        self.position = (row, col)
        self.status = "idle"  # idle, charging, irrigating, fertilizing
        self.irrig_jid = irrig_jid
        self.fert_jid = fert_jid
        self.log_jid = log_jid
        self.env_jid = env_jid
        self.row = row
        self.col = col

        self.energy = 100.0
        self.last_value = None # Guarda o ultimo scan realizado
        self.current_task = None # Guarda a tarefa em curso: {"cfp_id": ..., "agent": ..., "type": ...}

    async def setup(self):
        self.logger.info(f"SoilSensorAgent {self.jid} a iniciar...")
        
        # 1. Comportamento Cíclico para receber 'Done'
        template_done = Template()
        template_done.set_metadata("performative", PERFORMATIVE_DONE)

        done_b = ReceiveDoneBehaviour()
        self.add_behaviour(done_b,template=template_done)
        
        # 2. Comportamento Periódico para realizar o Scan
        # O período deve ser ajustado à simulação, aqui usamos 30 segundos como exemplo
        scan_b = ScanBehaviour(period=40, row=self.row, col=self.col, env_jid=self.env_jid)
        self.add_behaviour(scan_b)
        
        self.logger.info("SoilSensorAgent iniciado com sucesso.")