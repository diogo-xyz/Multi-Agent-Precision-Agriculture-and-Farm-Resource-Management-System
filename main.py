import sys
import os
import asyncio
import logging

from human_agent import HumanAgent
from environment_agent import FarmEnvironmentAgent
from agents.drone_agent import DroneAgent
from agents.logistics_agent import LogisticsAgent
from agents.harvester_agent import HarvesterAgent
from agents.soil_sensor_agent import SoilSensorAgent
from agents.fertilizer_agent import FertilizerAgent
from agents.irrigation_agent import IrrigationAgent

from config_agents import (
    DRONE_JID, DRONE_PASS,
    LOG_JID, LOG_PASS,
    HARVESTERS_JID, HARVESTERS_PASS,
    SOIL_JID, SOIL_PASS,
    FERT_JID, FERT_PASS,
    IRRIG_JID, IRRIG_PASS,
    ENV_JID, ENV_PASS,
    HUMAN_JID, HUMAN_PASS   
)

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
    # drones e soiles são os ultimos a iniciar 
    #human_agent = HumanAgent(HUMAN_JID[0], HUMAN_PASS[0], ENV_JID[0])
    #await human_agent.start()
    #logger.info("Agente Humano em execução. Pressione Ctrl+C para parar.")

    field = Field()
    logistic_agent = LogisticsAgent(LOG_JID[0], LOG_PASS[0], HARVESTERS_JID,3, -1)
    await logistic_agent.start()
    logger.info("Agente Logística em execução.")

    logistic_agent = LogisticsAgent(LOG_JID[1], LOG_PASS[1], HARVESTERS_JID,3, -5)
    await logistic_agent.start()
    logger.info("Agente Logística em execução.")

    # Inicializar e iniciar o agente
    env_agent = FarmEnvironmentAgent(ENV_JID[0], ENV_PASS[0], field)
    await env_agent.start()
    logger.info("Agente Ambiente em execução. Pressione Ctrl+C para parar.")

    harv_agent = HarvesterAgent(HARVESTERS_JID[0],HARVESTERS_PASS[0],0,0,ENV_JID[0],LOG_JID)
    await harv_agent.start()
    logger.info("Agente Harv  em execução.")
    #
    #soil_agent = SoilSensorAgent(SOIL_JID[0], SOIL_PASS[0],LOG_JID, IRRIG_JID, FERT_JID, ENV_JID[0],0, 1)
    #await soil_agent.start()
    #logger.info("Agente Sensor de Solo em execução.")

    #drone_agent = DroneAgent(DRONE_JID[0], DRONE_PASS[0],[(0,0),(1,0),(2,0)],0, 0, ENV_JID[0],LOG_JID)
    #await drone_agent.start()
    #logger.info("Agente Drone em execução.")




    # Manter o agente a correr
    try:
        while env_agent.is_alive():
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    '''
    finally:
        if env_agent.is_alive():
            await env_agent.stop()
        logger.info("Agente Ambiente parado.")
        if human_agent.is_alive():
            await human_agent.stop()
        logger.info("Agente Humano parado.") '''


if __name__ == "__main__":
    asyncio.run(main())