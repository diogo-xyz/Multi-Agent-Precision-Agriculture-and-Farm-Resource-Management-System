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

# ========== HANDLER CUSTOMIZADO PARA TERMINAL ==========
class FarmTaskPrinter(logging.Handler):
    """Handler customizado para mostrar apenas eventos importantes da farm no terminal"""
    
    def __init__(self):
        super().__init__()
        self.in_environment_view = False  # Flag para controlar visualização do ambiente
    
    def emit(self, record):
        msg = record.getMessage()
        agent = record.name  # Nome do logger (ex: "[LOG] logistics1@localhost")
        
        # ========== VISUALIZAÇÃO DO AMBIENTE (comando 6) ==========
        if "======================================================================" in msg and agent == "FarmEnvironmentAgent":
            if not self.in_environment_view:
                # Início da visualização
                self.in_environment_view = True
                print(f"\n{'='*70}")
                print("🌍 VISUALIZAÇÃO DO AMBIENTE")
                print(f"{'='*70}")
            else:
                # Fim da visualização
                self.in_environment_view = False
                print(f"{'='*70}\n")
            return
        
        # Se estamos dentro da visualização do ambiente, mostra tudo
        if self.in_environment_view and agent == "FarmEnvironmentAgent":
            # Remove o prefixo de log para ficar mais limpo
            clean_msg = msg.strip()
            
            # Adiciona emojis para as seções
            if "Dia:" in clean_msg and "Hora:" in clean_msg:
                print(f"📅 {clean_msg}")
            elif "Temperatura:" in clean_msg:
                print(f"🌡️  {clean_msg}")
            elif "Chuva:" in clean_msg:
                print(f"🌧️  {clean_msg}")
            elif clean_msg == "Humidade:":
                print(f"\n💧 {clean_msg}")
            elif clean_msg == "Nutrientes:":
                print(f"\n🧪 {clean_msg}")
            elif clean_msg == "Estágio da Cultura:":
                print(f"\n🌱 {clean_msg}")
            elif clean_msg == "Tipo de Cultura:":
                print(f"\n🌾 {clean_msg}")
            elif clean_msg == "Saúde da Cultura:":
                print(f"\n💚 {clean_msg}")
            elif clean_msg == "Pragas:":
                print(f"\n🐛 {clean_msg}")
            else:
                # Valores das matrizes
                print(f"  {clean_msg}")
            return
        
        # ========== PEDIDOS AO ENVIRONMENT AGENT ==========
        if "Mensagem recebida:" in msg and " de " in msg:
            # Extrai: "Mensagem recebida: get_soil de soil1@localhost"
            try:
                parts = msg.split("Mensagem recebida: ")[1].split(" de ")
                action = parts[0]
                requester = parts[1]
                
                # Emojis específicos por tipo de ação
                emoji_map = {
                    "get_soil": "🌱",
                    "get_drone": "🚁",
                    "apply_irrigation": "💧",
                    "apply_fertilize": "🧪",
                    "apply_pesticide": "🐛",
                    "plant_seed": "🌾",
                    "harvest": "🚜"
                }
                emoji = emoji_map.get(action, "📨")
                print(f"{emoji} {requester} pediu ao Environment: {action}")
            except:
                pass
        
        # ========== PEDIDOS DE RECARGA (CFP para Logistics) ==========
        # Quando um agente PEDE recarga
        elif "[CFP_RECHARGE]" in msg and "Enviando CFP" in msg:
            print(f"🔋 {agent} pediu recarga ao Logistics")
        
        elif "[CFP_RECHARGE]" in msg and "A iniciar CFP" in msg:
            if "para" in msg:
                try:
                    requester = msg.split("para ")[1].split(" (")[0]
                    resource_type = msg.split("(")[1].split(")")[0] if "(" in msg else "recurso"
                    print(f"🔔 {agent} recebeu pedido de recarga: {requester} ({resource_type})")
                except:
                    print(f"🔔 {agent} criou CFP de recarga")
        
        # Quando um agente ACEITA fazer a recarga
        elif "[ACCEPT_RECHARGE]" in msg and "aceite" in msg.lower():
            if "para" in msg:
                try:
                    target = msg.split("para ")[1].split(" ")[0].strip()
                    print(f"✅ {agent} aceitou recarregar: {target}")
                except:
                    print(f"✅ {agent} aceitou fazer recarga")
        
        # Quando Logistics SELECIONA quem vai recarregar
        elif "selecionado para recarga" in msg.lower() or "[CFP_RECHARGE] Logistics selecionado:" in msg:
            try:
                selected = msg.split("selecionado: ")[1].split(" ")[0] if "selecionado:" in msg else "desconhecido"
                print(f"✅ Logistics escolhido para recarga: {selected}")
            except:
                pass
        
        # ========== TAREFAS DE PLANTAÇÃO/COLHEITA ==========
        # Quando um CFP de tarefa é iniciado
        elif "[CFP_INIT]" in msg and "A iniciar CFP" in msg:
            if "para" in msg and "em" in msg:
                try:
                    task_type = msg.split("para ")[1].split(" em")[0]
                    location = msg.split("em ")[1].split(".")[0]
                    
                    # Simplifica o nome da tarefa
                    task_name = task_type.replace("_application", "").replace("_", " ")
                    print(f"🔔 {agent} criou tarefa: {task_name} em {location}")
                except:
                    pass
        
        # Quando um harvester é ESCOLHIDO para uma tarefa
        elif "[CFP_TASK_RECV] Harvester selecionado:" in msg:
            try:
                parts = msg.split("selecionado: ")[1].split(" com ETA")
                selected = parts[0]
                eta = parts[1].strip().replace(".", "")
                print(f"✅ {agent} escolheu: {selected} (ETA:{eta})")
            except:
                pass
        
        # Quando um harvester ACEITA uma proposta de tarefa
        elif "[PROPOSAL]" in msg and "ACEITE" in msg and "para" in msg:
            if "em (" in msg:
                try:
                    task = msg.split("para ")[1].split(" em")[0]
                    location = msg.split("em ")[1].split(".")[0]
                    
                    # Emoji por tipo de tarefa
                    if "plant" in task:
                        emoji = "🌱"
                    elif "harvest" in task:
                        emoji = "🚜"
                    elif "irrigation" in task:
                        emoji = "💧"
                    elif "fertilize" in task:
                        emoji = "🧪"
                    else:
                        emoji = "✓"
                    
                    task_name = task.replace("_application", "").replace("_", " ")
                    print(f"{emoji} {agent} vai executar: {task_name} em {location}")
                except:
                    pass
        
        # ========== EXECUÇÃO E CONCLUSÃO DE TAREFAS ==========
        elif "[PLANT]" in msg and "concluída" in msg.lower():
            try:
                if "CFP" in msg or "cfp" in msg:
                    print(f"✔️ {agent} concluiu tarefa de plantação")
            except:
                pass
        
        elif "[HARVEST]" in msg and "concluída" in msg.lower():
            print(f"✔️ {agent} concluiu colheita")
        
        # Quando há FALHA
        elif "[FAILURE]" in msg or "falhou" in msg.lower():
            if "Tarefa" in msg:
                print(f"❌ {agent} - Tarefa falhou")
        
        # ========== RECARGA REALIZADA ==========
        elif "[RECHARGE]" in msg and "concluída" in msg.lower():
            print(f"🔋 {agent} completou recarga")
        
        elif "recarregado com sucesso" in msg.lower():
            print(f"🔋 {agent} foi recarregado")
        
        # ========== INFORMAÇÕES DE RECURSOS CRÍTICOS ==========
        elif "Bateria baixa" in msg or "Combustível baixo" in msg or "Recursos baixos" in msg:
            print(f"⚠️ {agent} - Recursos baixos!")
        
        # ========== TICKS DO AMBIENTE ==========
        elif "TICK: Ambiente avançou" in msg:
            try:
                day = msg.split("dia ")[1].split(",")[0]
                hour = msg.split("hora ")[1].split(".")[0]
                print(f"\n{'='*60}")
                print(f"⏰ DIA {day}, HORA {hour}")
                print(f"{'='*60}\n")
            except:
                pass

# ===  Criar handlers ===

# Handler customizado para terminal
task_printer = FarmTaskPrinter()
task_printer.setLevel(logging.INFO)

# Handler para ficheiro (guarda logs em disco)
file_handler = RotatingFileHandler(
    "agentes.log",
    maxBytes=10_000_000,
    backupCount=3,
    encoding="utf-8"
)
file_handler.setLevel(logging.INFO)

# ===  Criar formatter (apenas para o ficheiro) ===
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
file_handler.setFormatter(formatter)

# ===  Configurar logger raiz ===
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(task_printer)  # Handler customizado para terminal
root_logger.addHandler(file_handler)  # Handler para ficheiro

# === Criar logger específico para o teu módulo principal ===
logger = logging.getLogger("MainStarter")


async def main():
    field = Field()
    # ===  Inicializar agentes principais ===
    human_agent = HumanAgent(HUMAN_JID[0], HUMAN_PASS[0], ENV_JID[0])
    storage_agent = StorageAgent(STORAGE_JID[0], STORAGE_PASS[0])
    env_agent = FarmEnvironmentAgent(ENV_JID[0], ENV_PASS[0], field)
    
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
                pos_logistics[i][1],
                field
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

    # === Loop principal de execução ===
    try:
        while env_agent.is_alive():
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        # Parar todos os agentes com segurança
        all_agents = [
            human_agent, env_agent,
            *logistics_agents, *harvesters,storage_agent,
            *irrigations, *fertilizers,
            *soils, *drones
        ]
        for agent in all_agents:
            if agent.is_alive():
                print(f"Stopping {agent.jid}...")
                try:
                    await asyncio.wait_for(agent.stop(), timeout=5)
                except asyncio.TimeoutError:
                    pass

        await asyncio.sleep(1)
        os._exit(0)


if __name__ == "__main__":
    asyncio.run(main())