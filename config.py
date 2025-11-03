import numpy as np
# Variáveis de Simulação

TICK_HOURS = 1
ROWS = 3
COLS = 3


# Parametros da humidade 

MM_TO_PCT = 0.25 # Converte milímetros de chuva (mm) em pontos percentuais de humidade do solo %
# 1 mm de chuva aumenta a humidade em cerca de 0.25%

EVAP_BASE_COEFF = 0.05 # Taxa base de evaporação em mm/h por grau Celsius acima de um certo threshold

EVAP_TEMP_THRESHOLD = 5
# Abaixo desse valor, considera-se que a evaporação é quase nula 

DIFFUSION_COEF_MOISTURE = 0.30
# Coeficiente de difusão espacial de humidade entre células vizinhas  [0,1]

FIELD_CAPACITY = 90.0
# Percentagem de humidade máxima que o solo pode reter antes de ocorrer runoff (escoamento superficial) ou leaching (lixiviação)

LEACH_COEFF = 0.2 # Controla a intensidade da drenagem
# Fração do excesso de água acima da capacidade de campo que é perdida (runoff/leaching), levando nutrientes junto

RAIN_NOISE = 0.05 
# Desvio padrão do ruído aleatório aplicado à chuva, representando variação espacial (chuva desigual entre células)

IRRIG_TO_PCT = 5.0 # 1 L de agua aumenta 5% da humiade



# Parametros dos Nutrientes

MINERAL_BASE = 0.005
# Taxa base de mineralização natural, ou seja, o ganho lento e contínuo de nutrientes por decomposição da matéria orgânica

DIFFUSION_COEF_NUTRIENTS = 0.06 # Taxa de difusão espacial, redistribuição de nutrientes entre células vizinhas

PEST_LOSS_RATE = 0.02  # Taxa de perda de nutrientes causada por pragas no solo

KG_TO_PCT = 10.0 # 1 kg de fertilizante aplicado 10% de aumento nos nutrientes


#Parametros Chuva

# Modificador de probabilidade de chuva quando em seca e não está a chover (0: none, 1: light, 2: moderate, 3: heavy)
# Reduz drasticamente a chance de começar a chover
DROUGHT_PROB_MOD = np.array([1.0, 0.15, 0.001, 0.0001])

# Fator pelo qual a duração média da chuva é reduzida quando começa a chover em seca
DROUGHT_DURATION_FACTOR = 4.0


# Probabilidades sazonais para (0: none, 1: light, 2: moderate, 3: heavy)
SEASON_PROBS = {
    "summer": np.array([0.75, 0.20, 0.045, 0.005]),   # verão seco: muito provavelmente nada ou chuvisco leve
    "spring": np.array([0.45, 0.30, 0.20, 0.05]),    # primavera: mistura de dias secos e chuvas leves/moderadas
    "autumn": np.array([0.40, 0.35, 0.20, 0.05]),    # outono: mais equilíbrio, um pouco mais de moderada
    "winter": np.array([0.10, 0.30, 0.35, 0.25]),    # inverno: baixa chance de nenhum, maior de moderada/pesada
}

# Média de duração (horas) de um episódio para cada intensidade por estação.
MEAN_DURATION_HOURS_BASE = {
    "summer":   {0: 72.0, 1: 5.0, 2: 3.0, 3: 2.0},
    "spring":   {0: 36.0, 1: 6.0, 2: 8.0, 3: 10.0},
    "autumn":   {0: 36.0, 1: 6.0, 2: 8.0, 3: 10.0},
    "winter":   {0: 24.0, 1: 8.0, 2: 10.0, 3: 20.0},
}


# Probabilidade (por hora) de terminar prematuramente um episódio 
P_STOP_EARLY_PER_HOUR = 0.02 

# Chance muito pequena de evento extremo extra 
EXTREME_OVERRIDE_PROB = 1e-4


# Parametros Peste

P_SPREAD = 0.1 # Probabilidade de um vizinho ser infetado por uma célula com peste


# Parametros Plantas 

# 4 Estágios de Crescimento (1-4)
# 0: Sem Plantação 
# 1: Semente 
# 2: Germinar 
# 3: Vegetação 
# 4: Maduro 

# 6 Tipos de Planta (0-5)
# 0: Tomate 
# 1: Pimento 
# 2: Trigo 
# 3: Couve 
# 4: Alface 
# 5: Cenoura 

# Taxas de Absorção de Água (Uptake) em mm/h por Estágio (linhas) e por Tipo de Planta (colunas)
# A ordem das linhas é: Semente (índice 0), Germinar (índice 1), Vegetação (índice 2), Maduro (índice 3)
# Nota: O estágio 0 (Sem Plantação) será tratado com uma taxa de absorção de 0.0.
# A ordem das colunas é: Tomate, Pimento, Trigo, Couve, Alface, Cenoura
# Valores de exemplo (mm/h):
# Tomate: 0.01, 0.05, 0.25, 0.15 (Alto consumo na vegetação/frutificação)
# Pimento: 0.01, 0.04, 0.20, 0.12 (Similar ao tomate, ligeiramente menor)
# Trigo: 0.01, 0.03, 0.15, 0.10 (Moderado, pico na vegetação)
# Couve: 0.01, 0.04, 0.18, 0.10 (Moderado a alto)
# Alface: 0.01, 0.05, 0.22, 0.08 (Rápido crescimento, alto consumo na vegetação)
# Cenoura: 0.01, 0.03, 0.12, 0.07 (Baixo a moderado)
UPTAKE_RATES_MM_PER_HOUR = np.array([
    [0.01, 0.01, 0.01, 0.01, 0.01, 0.01],  # Semente
    [0.05, 0.04, 0.03, 0.04, 0.05, 0.03],  # Germinar
    [0.25, 0.20, 0.15, 0.18, 0.22, 0.12],  # Vegetação
    [0.15, 0.12, 0.10, 0.10, 0.08, 0.07]   # Maduro
])

# Humidade Ideal (Target) por Tipo de Planta (%)
# Estes valores representam o intervalo ideal de humidade do solo
# A ordem é: Tomate, Pimento, Trigo, Couve, Alface, Cenoura
# Tomate/Pimento/Alface/Couve: 70-85% (Alta necessidade, sensível à seca)
# Trigo: 60-75% (Moderada necessidade, mais tolerante)
# Cenoura: 65-80% (Moderada necessidade, solo bem drenado)
IDEAL_MOISTURE_TARGET = np.array([
    77.5,  # Tomate (média de 70-85)
    77.5,  # Pimento (média de 70-85)
    67.5,  # Trigo (média de 60-75)
    77.5,  # Couve (média de 70-85)
    77.5,  # Alface (média de 70-85)
    72.5   # Cenoura (média de 65-80)
])

# Tolerância à Seca (Desvio Máximo Aceitável da Humidade Ideal)
# Usado para calcular o stress da planta. Valores mais baixos significam menos tolerância.
DROUGHT_TOLERANCE = np.array([
    10.0,  # Tomate (Baixa tolerância)
    10.0,  # Pimento (Baixa tolerância)
    15.0,  # Trigo (Média tolerância)
    12.0,  # Couve (Média-Baixa tolerância)
    10.0,  # Alface (Baixa tolerância)
    12.0   # Cenoura (Média-Baixa tolerância)
])


# Consumo de Nutrientes (Uptake) por Estágio e Tipo de Planta
# Os valores são fictícios, mas seguem a lógica de que o consumo deve ser proporcional ao consumo de água (UPTAKE_RATES_MM_PER_HOUR)
# e deve ser uma matriz 4x6 (Estágios x Tipos de Planta)
# Vamos usar uma proporção do consumo de água como base para o consumo de nutrientes
# Por exemplo, 1% do consumo de água em mm/h é o consumo de nutrientes em %/h

# Fator de conversão de consumo de água para consumo de nutrientes
NUTRIENT_CONCENTRATION_FACTOR = 0.1




# Duração de cada estágio em horas por tipo de planta
# Formato: [Semente, Germinar, Vegetação, Maduro]
# Valores base em horas (podem ser ajustados)
STAGE_DURATIONS = {
    0: [48, 72, 168, 240],    # Tomate: 2d, 3d, 7d, 10d
    1: [48, 72, 168, 240],    # Pimento: 2d, 3d, 7d, 10d
    2: [24, 48, 336, 480],    # Trigo: 1d, 2d, 14d, 20d
    3: [36, 60, 144, 192],    # Couve: 1.5d, 2.5d, 6d, 8d
    4: [24, 48, 120, 168],    # Alface: 1d, 2d, 5d, 7d
    5: [48, 72, 240, 336],    # Cenoura: 2d, 3d, 10d, 14d
}


# Dias até começar apodrecimento após maturação (por tipo de planta)
DAYS_BEFORE_ROT = {
    0: 7,   # Tomate: 7 dias
    1: 7,   # Pimento: 7 dias
    2: 10,  # Trigo: 10 dias
    3: 5,   # Couve: 5 dias
    4: 3,   # Alface: 3 dias
    5: 14,  # Cenoura: 14 dias
}

# Taxa de perda de saúde por apodrecimento (% por dia)
ROT_RATE = 10.0