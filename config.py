import numpy as np
# Variáveis de Simulação

TICK_HOURS = 1
ROWS = 4
COLS = 4


# Parametros da humidade 

MM_TO_PCT = 0.25 # Converte milímetros de chuva (mm) em pontos percentuais de humidade do solo %
# 1 mm de chuva aumenta a humidade em cerca de 0.25%

EVAP_BASE_COEFF = 0.08 # Taxa base de evaporação em mm/h por grau Celsius acima de um certo threshold

EVAP_TEMP_THRESHOLD = 5
# Abaixo desse valor, considera-se que a evaporação é quase nula 

DIFFUSION_COEF = 0.12
# Coeficiente de difusão espacial de humidade entre células vizinhas  [0,1]

FIELD_CAPACITY = 90.0
# Percentagem de humidade máxima que o solo pode reter antes de ocorrer runoff (escoamento superficial) ou leaching (lixiviação)

LEACH_COEFF = 0.5 # Controla a intensidade da drenagem
# Fração do excesso de água acima da capacidade de campo que é perdida (runoff/leaching), levando nutrientes junto

RAIN_NOISE = 0.05 
# Desvio padrão do ruído aleatório aplicado à chuva, representando variação espacial (chuva desigual entre células)



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
