import json
import logging
import time


from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.template import Template
from agents.message import make_message

PERFORMATIVE_INFORM_RECEIVED = "inform_received"
PERFORMATIVE_INFORM_HARVEST = "inform_harvest"
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
                        self.agent.yield_storage[seed_type] += amount
                        
                        details_received.append({"seed_type": seed_type, "amount": amount})
                        self.agent.logger.info(f"[INFORM_HARVEST] Yield de semente {seed_type} atualizado. Adicionado: {amount}. Total: {self.agent.yield_storage[seed_type]}.")

                #print(self.agent.yield_storage)
                # Enviar confirmação `inform_received`
                if details_received:
                    msg = await self.agent.send_inform_received(sender_jid, details_received)
                    await self.send(msg)
                    self.agent.logger.info(f"[INFORM_HARVEST] Confirmação 'inform_received' enviada para {sender_jid}.")

            except json.JSONDecodeError:
                self.agent.logger.error(f"[INFORM_HARVEST] Erro ao descodificar JSON: {msg.body}")
            except Exception as e:
                self.agent.logger.exception(f"[INFORM_HARVEST] Erro ao processar INFORM_HARVEST: {e}")


class StorageAgent(Agent):

    def __init__(self, jid, password):
        super().__init__(jid, password)
        
        self.logger = logging.getLogger(f"[STO] {jid}")
        self.logger.setLevel(logging.INFO)

        self.yield_storage = {
            0: 0, # 0: Tomate
            1: 0, # 1: Pimento
            2: 0, # 2: Trigo
            3: 0, # 3: Couve
            4: 0, # 4: Alface
            5: 0  # 5: Cenoura
        }

        self.numb_to_string = {
            0: "Tomate",
            1: "Pimento",
            2: "Trigo",
            3: "Couve",
            4: "Alface",
            5: "Cenoura"
        }
    
    async def setup(self):
        self.logger.info("Storage started")

        template = Template()
        template.set_metadata("performative", PERFORMATIVE_INFORM_HARVEST)

        self.add_behaviour(InformHarvestReceiver(),template=template)

    async def stop(self):
        self.logger.info(f"{'=' * 35} STOR {'=' * 35}")
        self.logger.info(f"{self.jid} guardou em toda a simulação:")
        for seed, amount in self.yield_storage.items():
            self.logger.info(f"{self.numb_to_string[seed]}: {amount}")
        self.logger.info(f"{'=' * 35} STOR {'=' * 35}")
        await super().stop()

    
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