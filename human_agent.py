"""
Módulo HumanAgent para interação com eventos dinâmicos em sistemas multi-agente.

Este módulo implementa um agente SPADE que permite a um utilizador humano
interagir com um ambiente de simulação através de eventos dinâmicos como
chuva, seca e pragas.
"""

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
    """
    Apresenta um menu de opções ao utilizador e obtém a sua escolha.
    
    O menu inclui opções para aplicar eventos dinâmicos como chuva, seca,
    pragas, e visualizar o ambiente.
    
    Returns:
        str: Número da opção escolhida pelo utilizador ('1' a '7').
        
    Note:
        A função continua a solicitar entrada até receber uma opção válida.
    """

    print("\n--- Menu de Eventos Dinâmicos ---")
    print("1. Aplicar Chuva (apply_rain)")
    print("2. Parar Chuva (stop_rain)")
    print("3. Alternar Seca (toggle_drought)")
    print("4. Aplicar Peste (apply_pest)")
    print("5. Remover Peste (remove_pest)")
    print("6. Ver Ambiente (view_environment)")
    print("7. Sair")
    while True:
        choice = input("Escolha o número do evento a aplicar\n")
        if choice in ['1', '2', '3', '4', '5', '6', '7']:
            return choice
        logger.warning("Escolha inválida. Por favor, insira um número de 1 a 7.")

def get_rain_intensity():
    """
    Solicita ao utilizador a intensidade da chuva.
    
    Returns:
        float: Valor da intensidade da chuva entre 1 e 3 (inclusive).
        
    Raises:
        ValueError: Se a entrada não puder ser convertida para float.
        
    Note:
        A função continua a solicitar entrada até receber um valor válido.
    """

    while True:
        try:
            intensity = float(input("Insira a intensidade da chuva [1,2,3]: "))
            if 1 <= intensity <= 3:
                return intensity
            print("Intensidade inválida. Deve ser um valor na lista [1,2,3]")
        except ValueError:
            print("Entrada inválida. Por favor, insira um número.")

class HumanInteractionBehaviour(OneShotBehaviour):
    """
    Comportamento SPADE para gerir a interação humana com eventos dinâmicos.
    
    Este comportamento executa uma única vez, apresenta um menu ao utilizador,
    processa a escolha e envia uma mensagem com o evento dinâmico selecionado
    para o agente recetor (agente de ambiente).
    
    Attributes:
        receiver_jid (str): JID do agente recetor das mensagens de eventos.
    """

    def __init__(self, receiver_jid):
        """
        Inicializa o comportamento de interação humana.
        
        Args:
            receiver_jid (str): JID do agente que receberá as mensagens de eventos.
        """

        super().__init__()
        self.receiver_jid = receiver_jid

    async def run(self):
        """
        Executa o comportamento de interação com o utilizador.
        
        Este método:
        1. Apresenta o menu e obtém a escolha do utilizador
        2. Processa a escolha e constrói a mensagem apropriada
        3. Envia a mensagem para o agente ambiente
        4. Aguarda e processa a resposta
        5. Reinicia o comportamento para permitir nova interação
        
        Note:
            Utiliza run_in_executor para operações de I/O bloqueantes (input).
        """

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
    """
    Agente SPADE que representa um utilizador humano no sistema multi-agente.
    
    Este agente permite que um utilizador humano interaja com o ambiente
    de simulação através de uma interface de linha de comandos, aplicando
    eventos dinâmicos como chuva, seca e pragas.
    
    Attributes:
        env_jid (str): JID do agente de ambiente que receberá os eventos.
    """

    def __init__(self, jid, password, env_jid, verify_security=False):
        """
        Inicializa o HumanAgent.
        
        Args:
            jid (str): Jabber ID do agente.
            password (str): Palavra-passe para autenticação XMPP.
            env_jid (str): JID do agente de ambiente.
            verify_security (bool, optional): Se deve verificar certificados SSL.
                Defaults to False.
        """

        super().__init__(jid, password, verify_security=verify_security)
        self.env_jid = env_jid

    async def setup(self):
        """
        Configura e inicia o agente.
        
        Este método é chamado automaticamente quando o agente é iniciado.
        Adiciona o comportamento de interação humana ao agente.
        
        Note:
            Regista mensagens de log para acompanhar o processo de inicialização.
        """
        logger.info(f"HumanAgent {self.jid} a iniciar...")
        self.add_behaviour(HumanInteractionBehaviour(self.env_jid))
        logger.info("HumanAgent iniciado com sucesso.")