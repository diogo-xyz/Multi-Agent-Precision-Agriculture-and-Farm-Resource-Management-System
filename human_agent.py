import asyncio
import json
import logging
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour
from spade.message import Message

logger = logging.getLogger("HumanAgent")


PERFORMATIVE_REQUEST = "request"
PERFORMATIVE_INFORM = "inform"
ONTOLOGY_DYNAMIC_EVENT = "dynamic_event"

def get_user_choice():
    print("\n--- Menu de Eventos Dinâmicos ---")
    print("1. Aplicar Chuva (apply_rain)")
    print("2. Parar Chuva (stop_rain)")
    print("3. Alternar Seca (toggle_drought)")
    print("4. Aplicar Peste (apply_pest)")
    print("5. Remover Peste (remove_pest)")
    print("6. Ver Ambiente (view_environment)")
    print("7. Sair")
    while True:
        choice = input("Escolha o número do evento a aplicar: ")
        if choice in ['1', '2', '3', '4', '5', '6', '7']:
            return choice
        logger.warning("Escolha inválida. Por favor, insira um número de 1 a 7.")

def get_rain_intensity():
    while True:
        try:
            intensity = float(input("Insira a intensidade da chuva [1,2,3]: "))
            if 1 <= intensity <= 3:
                return intensity
            print("Intensidade inválida. Deve ser um valor na lista [1,2,3]")
        except ValueError:
            print("Entrada inválida. Por favor, insira um número.")

class HumanInteractionBehaviour(OneShotBehaviour):
    def __init__(self, receiver_jid):
        super().__init__()
        self.receiver_jid = receiver_jid

    async def run(self):
        loop = asyncio.get_event_loop()
        # executar funções bloqueantes em executor
        choice = await loop.run_in_executor(None, get_user_choice)
	
        if choice == '7':
            print("A sair do Agente Humano.")
            return
	
        action = None
        content = {}

        if choice == '1':
            action = "apply_rain"
            intensity = await loop.run_in_executor(None, get_rain_intensity)
            content = {"action": action, "intensity": intensity}
        elif choice == '2':
            action = "stop_rain"
            content = {"action": action}
        elif choice == '3':
            action = "toggle_drought"
            content = {"action": action}
        elif choice == '4':
            action = "apply_pest"
            content = {"action": action}
        elif choice == '5':
            action = "remove_pest"
            content = {"action": action}
        elif choice == '6':
            action = "view_environment"
            content = {"action": action}
	
        if not action:
            return

        # criar mensagem e metadata
        msg = Message(to=self.receiver_jid, body=json.dumps(content))
        msg.set_metadata("performative", PERFORMATIVE_REQUEST)
        msg.set_metadata("ontology", ONTOLOGY_DYNAMIC_EVENT)
        await self.send(msg)
        logger.info(f"A enviar evento dinâmico: {action} para {self.receiver_jid}")
        
        msg = await self.receive(timeout=5)  # espera por respostas
        if msg:
            try:
                data = json.loads(msg.body)
            except Exception:
                data = msg.body
            logger.info(f"Resposta recebida de {msg.sender}: {data}")
        self.agent.add_behaviour(HumanInteractionBehaviour(self.receiver_jid))


class HumanAgent(Agent):
    def __init__(self, jid, password, env_jid, verify_security=False):
        super().__init__(jid, password, verify_security=verify_security)
        self.env_jid = env_jid

    async def setup(self):
        logger.info(f"HumanAgent {self.jid} a iniciar...")
        self.add_behaviour(HumanInteractionBehaviour(self.env_jid))
        logger.info("HumanAgent iniciado com sucesso.")