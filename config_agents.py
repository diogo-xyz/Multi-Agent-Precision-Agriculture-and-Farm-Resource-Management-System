# Ficheiro de configuração para JIDs, passwords e quantidades de agentes

DRONE_JID = [f"drone{i+1}@localhost" for i in range(6)]
DRONE_PASS = ["dronepass"] * 6


LOG_JID = [f"logistics{i+1}@localhost" for i in range(3)]
LOG_PASS = ["logpass"] * 3


HARVESTERS_JID = [f"harvester{i+1}@localhost" for i in range(4)]
HARVESTERS_PASS = ["harpass"] * 4


SOIL_JID = [f"soil{i+1}@localhost" for i in range(6)]
SOIL_PASS = ["soilpass"] * 6


FERT_JID = [f"fert{i+1}@localhost" for i in range(4)]
FERT_PASS = ["ferstpass"] * 4


IRRIG_JID = [f"irrig{i+1}@localhost" for i in range(4)]
IRRIG_PASS = ["irrigpass"] * 4


ENV_JID = ["environment@localhost"]
ENV_PASS = ["password"]


HUMAN_JID = ["human@localhost"]
HUMAN_PASS = ["human123"]