import sys
import os
import asyncio
import logging

from human_agent import HumanAgent
from environment_agent import FarmEnvironmentAgent

from config_agents import ENV_JID, ENV_PASS, HUMAN_JID, HUMAN_PASS 

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from TB_Sistemas.environment.field import Field


# --- Configuração Centralizada de Logging ---
# 1. Configurar o Handler (para onde enviar os logs, e.g., consola)
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)

# 2. Configurar o Formatter (como formatar a mensagem)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# 3. Obter o logger raiz e adicionar o handler
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO) # Define o nível mínimo para toda a aplicação
root_logger.addHandler(handler)

logger = logging.getLogger("MainStarter")


async def main():
    field = Field()

    # Inicializar e iniciar o agente
    env_agent = FarmEnvironmentAgent(ENV_JID, ENV_PASS, field)
    await env_agent.start()
    logger.info("Agente Ambiente em execução. Pressione Ctrl+C para parar.")

    human_agent = HumanAgent(HUMAN_JID, HUMAN_PASS, ENV_JID)
    await human_agent.start()
    logger.info("Agente Humano em execução. Pressione Ctrl+C para parar.")

    
    # Manter o agente a correr
    try:
        while env_agent.is_alive():
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if env_agent.is_alive():
            await env_agent.stop()
        logger.info("Agente Ambiente parado.")
        if human_agent.is_alive():
            await human_agent.stop()
        logger.info("Agente Humano parado.")


if __name__ == "__main__":
    asyncio.run(main())