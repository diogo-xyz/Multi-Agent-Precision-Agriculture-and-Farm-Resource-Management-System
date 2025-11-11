import sys
import os
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from human_agent import HumanAgent
from environment_agent import FarmEnvironmentAgent
from agents.drone_agent import DroneAgent
from agents.logistics_agent import LogisticsAgent
from agents.harvester_agent import HarvesterAgent
from agents.soil_sensor_agent import SoilSensorAgent
from agents.fertilizer_agent import FertilizerAgent
from agents.irrigation_agent import IrrigationAgent
from agents.storage_agent import StorageAgent

from config_agents import (
    DRONE_JID, DRONE_PASS,
    LOG_JID, LOG_PASS,
    HARVESTERS_JID, HARVESTERS_PASS,
    SOIL_JID, SOIL_PASS,
    FERT_JID, FERT_PASS,
    IRRIG_JID, IRRIG_PASS,
    ENV_JID, ENV_PASS,
    HUMAN_JID, HUMAN_PASS,
    STORAGE_JID,STORAGE_PASS   
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from TB_Sistemas.environment.field import Field


# --- Configuração Centralizada de Logging ---

# ===  Criar handlers ===

# Handler para consola (terminal)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Handler para ficheiro (guarda logs em disco)
file_handler = RotatingFileHandler(
    "agentes.log",          # nome do ficheiro
    maxBytes=5_000_000,     # tamanho máximo antes de criar novo ficheiro (~5 MB)
    backupCount=3,          # quantos ficheiros antigos manter
    encoding="utf-8"
)
file_handler.setLevel(logging.INFO)

# ===  Criar formatter (formato comum para ambos os handlers) ===
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# ===  Configurar logger raiz ===
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)

# === Criar logger específico para o teu módulo principal ===
logger = logging.getLogger("MainStarter")


async def main():
    # ===  Inicializar agentes principais ===
    human_agent = HumanAgent(HUMAN_JID[0], HUMAN_PASS[0], ENV_JID[0])
    storage_agent = StorageAgent(STORAGE_JID[0], STORAGE_PASS[0])
    env_agent = FarmEnvironmentAgent(ENV_JID[0], ENV_PASS[0], Field())

    # ===  Inicializar listas de agentes auxiliares ===
    logistics_agents = []
    harvesters = []
    irrigations = []
    fertilizers = []
    soils = []
    drones = []

    # ===  Criar agentes logísticos ===
    pos_logistics = [[-1, 3], [6, 3], [3, -1], [4, 6]]
    for i in range(4):
        logistics_agents.append(
            LogisticsAgent(
                LOG_JID[i],
                LOG_PASS[i],
                HARVESTERS_JID,
                LOG_JID,
                pos_logistics[i][0],
                pos_logistics[i][1]
            )
        )

    # ===  Criar agentes de colheita (harvesters) ===
    pos_agents = [[-1, -1], [-1, 6], [6, -1], [6, 6]]
    for i in range(4):
        harvesters.append(
            HarvesterAgent(
                HARVESTERS_JID[i],
                HARVESTERS_PASS[i],
                pos_agents[i][0],
                pos_agents[i][1],
                ENV_JID[0],
                LOG_JID,
                STORAGE_JID[0]
            )
        )

    # === Criar agentes de irrigação ===
    for i in range(4):
        irrigations.append(
            IrrigationAgent(
                IRRIG_JID[i],
                IRRIG_PASS[i],
                LOG_JID,
                SOIL_JID,
                pos_agents[i][0],
                pos_agents[i][1]
            )
        )

    # ===  Criar agentes de fertilização ===
    for i in range(4):
        fertilizers.append(
            FertilizerAgent(
                FERT_JID[i],
                FERT_PASS[i],
                LOG_JID,
                SOIL_JID,
                pos_agents[i][0],
                pos_agents[i][1]
            )
        )

    # ===  Iniciar agentes principais e operacionais (exceto sensores e drones) ===
    await asyncio.gather(
        human_agent.start(),
        storage_agent.start(),
        env_agent.start(),
        *[agent.start() for agent in logistics_agents],
        *[agent.start() for agent in harvesters],
        *[agent.start() for agent in irrigations],
        *[agent.start() for agent in fertilizers],
    )
    logger.info("Agentes principais, logísticos, colheitadeiras, irrigação e fertilização em execução.")

    # ===  Criar e iniciar agentes sensores de solo ===
    for i in range(6):
        soils.append(
            SoilSensorAgent(
                SOIL_JID[i],
                SOIL_PASS[i],
                LOG_JID,
                IRRIG_JID,
                FERT_JID,
                ENV_JID[0],
                0,
                i
            )
        )

    await asyncio.gather(*[agent.start() for agent in soils])
    logger.info("Agentes Sensores de Solo em execução.")

    # ===  Criar e iniciar agentes drones (últimos) ===
    zonas = [
        [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0)],
        [(0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1)],
        [(0, 2), (1, 2), (2, 2), (3, 2), (4, 2), (5, 2)],
        [(0, 3), (1, 3), (2, 3), (3, 3), (4, 3), (5, 3)],
        [(0, 4), (1, 4), (2, 4), (3, 4), (4, 4), (5, 4)],
        [(0, 5), (1, 5), (2, 5), (3, 5), (4, 5), (5, 5)],
    ]
    for i in range(6):
        drones.append(
            DroneAgent(
                DRONE_JID[i],
                DRONE_PASS[i],
                zonas[i],
                0,
                i,
                ENV_JID[0],
                LOG_JID
            )
        )

    await asyncio.gather(*[agent.start() for agent in drones])
    logger.info("Agentes Drones em execução.")

    # === Loop principal de execução ===
    try:
        while env_agent.is_alive():
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Encerrando todos os agentes...")
    finally:
        # Parar todos os agentes com segurança
        all_agents = [
            human_agent, storage_agent, env_agent,
            *logistics_agents, *harvesters,
            *irrigations, *fertilizers,
            *soils, *drones
        ]
        for agent in all_agents:
            if agent.is_alive():
                await agent.stop()
        logger.info("Todos os agentes foram parados com sucesso.")

if __name__ == "__main__":
    asyncio.run(main())