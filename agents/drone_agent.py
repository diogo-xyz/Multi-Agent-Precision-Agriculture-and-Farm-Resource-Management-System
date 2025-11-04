from spade.agent import Agent
from spade.behaviour import PeriodicBehaviour
from spade.message import Message as SpadeMessage
import json
import time
import numpy as np

from .message import Message # Assumindo que Message é uma classe auxiliar para construir mensagens
from ..environment.field import Field # Assumindo que o Field é acessível de alguma forma, mas na simulação real, o Field seria um objeto partilhado ou o Drone teria um sensor. Vou simular o acesso ao Field através de um atributo de simulação.
from ..config import ROW, COLS

# Constantes de Limite
BATTERY_LOW_THRESHOLD = 20.0
PESTICIDE_LOW_THRESHOLD = 1.0

class DroneAgent(Agent):
    def __init__(self, zones, jid, password, field_ref=None):
        super().__init__(jid, password)
        self.energy = 100.0
        self.position = (0,1)
        self.zones = zones # Lista de tuplos (row, col) que o drone patrulha
        self.status = "idle" # flying, charging, handling_task
        self.pesticideAmount =  # Quantidade de pesticida em KG
        self.maxpesticideAmount = 10.0
        self.field = field_ref # Referência ao objeto Field (para simulação)
        self.logistics_jid = "logistics@localhost" # JID do agente Logistics (assumindo um padrão)
        self.current_zone_index = 0

    async def setup(self):
        self.logger.info(f"DroneAgent {self.jid.localpart} iniciado. Posição: {self.position}")
        # O período deve ser ajustado para a simulação
        patrol_b = self.PatrolBehaviour(period=10) # Patrulha a cada 10 ticks
        self.add_behaviour(patrol_b)

    async def _get_current_zone(self):
        """Retorna a zona atual a ser patrulhada."""
        if not self.zones_id:
            return None
        # Simplesmente itera pelas zonas
        zone = self.zones_id[self.current_zone_index]
        self.current_zone_index = (self.current_zone_index + 1) % len(self.zones_id)
        return zone

    async def _send_message(self, receiver_jid, performative, body):
        """Função auxiliar para enviar mensagens Spade."""
        msg = SpadeMessage(to=receiver_jid, body=json.dumps(body), metadata={"performative": performative})
        self.send(msg)
        self.logger.info(f"Mensagem enviada para {receiver_jid} com performative: {performative}")

    async def _inform_crop(self, zone, state):
        """Envia uma mensagem inform_crop ao Logistics."""
        body = {
            "sender_id": str(self.jid),
            "receiver_id": self.logistics_jid,
            "inform_id": f"inform_crop_{time.time()}",
            "zone": list(zone),
            "state": state, # "0 -> not planted" ou "1 -> Ready for harvasting"
            "checked_at": time.time()
        }
        #self._send_message(self.logistics_jid, "inform_crop", body)
        return body

    async def _cfp_recharge(self, task_type, required_resources, priority):
        """Envia uma mensagem cfp_recharge ao Logistics."""
        body = {
            "sender_id": str(self.jid),
            "receiver_id": self.logistics_jid,
            "cfp_id": f"cfp_recharge_{time.time()}",
            "task_type": task_type, # battery | pesticides
            "required_resources": required_resources, # 80 mA (battery) | 2 doses (pesticides)
            "priority": priority
        }
        self._send_message(self.logistics_jid, "cfp_recharge", body)

    async def _apply_pesticide(self, row, col):
        """Simula a aplicação de pesticida e gasta o recurso."""
        if self.pesticideAmount >= 1.0:
            # Na simulação real, isto chamaria um método no objeto Field
            if self.field:
                self.field.apply_pesticide(row, col)
                self.pesticideAmount -= 1.0
                self.energy -= 3.0 # Gasto de energia
                self.logger.info(f"Pesticida aplicado em ({row},{col}). Restante: {self.pesticideAmount}. Energia: {self.energy}")
                return True
            else:
                self.logger.warning("Referência ao Field não definida. Não foi possível aplicar pesticida.")
                return False
        else:
            self.logger.warning("Pesticida insuficiente para aplicação.")
            return False

    class PatrolBehaviour(PeriodicBehaviour):

        async def run(self):
            # 1. Verificar Recursos (Bateria e Pesticida)
            if (self.agent.position) == (0,1):
                if self.agent.energy < len(self.zones) * 3 and self.agent.status != "charging":
                    self.agent.logger.warning(f"Bateria baixa ({self.agent.energy:.2f}%). Solicitando recarga.")
                    self.agent._cfp_recharge("battery", 100 - self.agent.energy , "Urgent")

                if self.agent.pesticideAmount < 1.0 and self.agent.status != "charging":
                    self.agent.logger.warning(f"Pesticidas baixa ({self.agent.pesticideAmount:.2f}%). Solicitando pesticidas.")
                    self.agent._cfp_recharge("pesticides", 3 - self.agent.pesticideAmount, "Urgent")
            
            # 2. Patrulhar aa zonas
            self.agent.status = "flying"
            for row,col in self.agent.zones:
                self.agent.energy -= 1.0 
                self.agent.position = (row,col)
                self.agent.logger.info(f"Patrulhando zona: ({row},{col}). Energia: {self.agent.energy:.2f}%.")

            # 3. Obter dados da cultura e peste
            crop_stage,crop_type,pest_status = self.agent.field.get_drone(row, col)

        async def run_(self):
            agent = self.agent
            
            # 1. Verificar Recursos (Bateria e Pesticida)
            if agent.energy < BATTERY_LOW_THRESHOLD and agent.status != "charging":
                agent.logger.warning(f"Bateria baixa ({agent.energy:.2f}%). Solicitando recarga.")
                agent._cfp_recharge("battery", 80, "Urgent")
                # Não continua a patrulha se a bateria estiver muito baixa
                return

            if agent.pesticideAmount < PESTICIDE_LOW_THRESHOLD:
                agent.logger.warning(f"Pesticida baixo ({agent.pesticideAmount:.2f} doses). Solicitando reabastecimento.")
                agent._cfp_recharge("pesticides", agent.maxpesticideAmount - agent.pesticideAmount, "High")
            
            # 2. Patrulhar a próxima zona
            zone = agent._get_current_zone()
            if zone is None:
                agent.logger.info("Nenhuma zona para patrulhar.")
                return

            row, col = zone
            agent.position = (row, col)
            agent.energy -= 1.0 # Gasto de energia por patrulha
            agent.status = "flying"
            agent.logger.info(f"Patrulhando zona: ({row},{col}). Energia: {agent.energy:.2f}%.")

            # 3. Obter dados da cultura e peste
            # Assumindo que o método get_drone retorna [crop_stage, pest_status]
            if agent.field:
                crop_stage, pest_status = agent.field.get_drone(row, col)
            else:
                # Simulação de dados se o Field não estiver disponível
                crop_stage = np.random.randint(0, 5)
                pest_status = np.random.randint(0, 2)
                agent.logger.warning("Usando dados simulados: Field não acessível.")

            # 4. Lógica de Peste
            if pest_status == 1:
                agent.logger.warning(f"Peste detetada em ({row},{col}). Aplicando pesticida.")
                if agent.pesticideAmount >= 1.0:
                    agent._apply_pesticide(row, col)
                else:
                    agent.logger.error("Peste detetada, mas sem pesticida. Solicitando reabastecimento urgente.")
                    agent._cfp_recharge("pesticides", agent.maxpesticideAmount, "Urgent")
            
            # 5. Lógica de Colheita/Plantação
            if crop_stage == 0:
                # Campo vazio, precisa de plantar
                agent.logger.info(f"Zona ({row},{col}) vazia. Informando Logistics para plantar.")
                agent._inform_crop(zone, "0") # 0 -> not planted
            elif crop_stage == 4:
                # Cultura madura, pronta para colheita
                agent.logger.info(f"Zona ({row},{col}) pronta para colheita. Informando Logistics.")
                agent._inform_crop(zone, "1") # 1 -> Ready for harvasting
            
            agent.status = "idle"