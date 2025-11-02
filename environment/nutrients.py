import numpy as np

from ..config import (
    MINERAL_BASE,
    DIFFUSION_COEF_NUTRIENTS,
    PEST_LOSS_RATE,
    NUTRIENT_CONCENTRATION_FACTOR,
    UPTAKE_RATES_MM_PER_HOUR,
    IDEAL_MOISTURE_TARGET,
    DROUGHT_TOLERANCE
)

class Nutrients():

    def __init__(self, rows, cols):
        # Inicializa com valores aleatórios, como no original
        self.nutrients = np.random.triangular(50, 60, 70, size=(rows, cols))
        # Adicionar soil_pests para evitar erro na linha 63
        self.soil_pests = np.zeros((rows, cols)) # Assumir 0 pragas por defeito

    def update_nutrients(self, drought, temperature, moisture, crop_type, crop_stage, dt_hours = 1.0):
        """
        Atualiza self.nutrients (escala 0..100) em função de:
        - consumo pelas plantas (depende do tipo e estágio da planta, humidade e temperatura)
        - mineralização (pequeno input natural, depende de humidade e temperatura)
        - perda por pragas de solo (self.soil_pests)
        - difusão espacial suave (redistribuição)
        """
        
        # ----- 1) consumo pelas plantas (uptake) -----

        # Obter as taxas de absorção de água (mm/h) para cada célula
        water_uptake_base = np.zeros_like(crop_type, dtype=float)
        
        # Iterar sobre cada célula para determinar o consumo base de água
        rows, cols = crop_type.shape
        for r in range(rows):
            for c in range(cols):
                plant_type = int(crop_type[r, c])
                plant_stage = int(crop_stage[r, c])
                
                # Estágio 0 (Sem Plantação) tem consumo 0
                if plant_stage == 0:
                    water_uptake_base[r, c] = 0.0
                    continue
                
                # Mapear estágio para índice da matriz (1->0, 2->1, 3->2, 4->3)
                stage_idx = plant_stage - 1
                
                # plant_type é o índice da coluna (0-5)
                type_idx = plant_type
                
                if 0 <= stage_idx < UPTAKE_RATES_MM_PER_HOUR.shape[0] and 0 <= type_idx < UPTAKE_RATES_MM_PER_HOUR.shape[1]:
                    # Consumo base de água em mm/h
                    water_uptake_base[r, c] = UPTAKE_RATES_MM_PER_HOUR[stage_idx, type_idx]
                else:
                    # Se o estágio ou tipo for inválido, o consumo é 0
                    water_uptake_base[r, c] = 0.0

        # O consumo base de nutrientes é proporcional ao consumo de água e ao fator de concentração
        uptake_base = water_uptake_base * NUTRIENT_CONCENTRATION_FACTOR
        
        # Consumo total no período
        uptake_base *= dt_hours
        
        
        # fator de humidade: uptake ótimo na humidade ideal (IDEAL_MOISTURE_TARGET); reduz fora disso
        m = moisture
        
        # Obter a humidade ideal e a tolerância à seca para cada célula
        ideal_m = np.array([IDEAL_MOISTURE_TARGET[int(t)] for t in crop_type.flatten()]).reshape(crop_type.shape)
        tolerance = np.array([DROUGHT_TOLERANCE[int(t)] for t in crop_type.flatten()]).reshape(crop_type.shape)
        
        # Calcular o desvio absoluto da humidade ideal
        moisture_deviation = np.abs(m - ideal_m)
        
        # O fator de humidade é 1.0 (ótimo) quando a humidade está dentro da tolerância, e decai linearmente até 0.0
        # quando o desvio é o dobro da tolerância (ou mais).
        m_factor = np.clip(1.0 - (moisture_deviation / (2 * tolerance)), 0.0, 1.0)
        
        # Para células sem planta (crop_type=0), o fator é 1.0 para não afetar a mineralização
        m_factor[crop_type == 0] = 1.0

        # fator de temperatura: temperatura ideal ~25°C; reduz fora disso (modelo mais realista)
        temp = float(temperature)
        
        # Usar um modelo de curva em sino (Bell Curve) simplificado para simular a otimização biológica
        # Assumir ótimo em 25°C, mínimo em 5°C e 45°C.
        # A função é 1.0 em 25°C e 0.0 em 5°C e 45°C.
        # Fator de escala para que o mínimo seja 0.0 em 5°C e 45°C: (temp - 5) * (45 - temp) / ((25 - 5) * (45 - 25))
        temp_factor = (temp - 5.0) * (45.0 - temp) / 400.0 # 400 = 20 * 20
        temp_factor = np.clip(temp_factor, 0.0, 1.0) # Limitar entre 0.0 e 1.0
        
        # Aplicar um fator mínimo para evitar que o uptake seja zero em temperaturas extremas (ex: 0.1)
        temp_factor = np.maximum(temp_factor, 0.1)

        # O fator de humidade (m_factor) já incorpora o stress hídrico.
        # O parâmetro 'drought' pode ser usado para um efeito adicional de stress geral, mas
        # como o m_factor é mais granular, vamos integrá-lo.
        # Se 'drought' for True, significa que o sistema está em stress hídrico generalizado,
        # o que pode ser um indicador de stress adicional para além da humidade local.
        # Vamos manter o 'drought' como um redutor de segurança, mas o m_factor é o principal.
        drought_factor = 0.8 if drought else 1.0 # Redução ligeira adicional em caso de seca geral

        # O m_factor já é 1.0 para células sem planta, mas o uptake_base também é 0.0.
        # O m_factor é o principal regulador do stress hídrico.
        uptake = uptake_base * m_factor * temp_factor * drought_factor

        # limitar uptake para não comer mais nutrientes do que existe
        uptake = np.minimum(uptake, self.nutrients)

        # subtrair uptake
        new_nutrients = self.nutrients - uptake

        # ----- 2) mineralização / input natural -----
        # mineralização depende de humidade (melhor em humidade moderada) e temperatura
        # Usar a mesma lógica de otimização de temperatura que o uptake, mas com um ótimo ligeiramente diferente (ex: 30°C)
        # Assumir ótimo em 30°C, mínimo em 5°C e 55°C.
        temp_min_factor = (temp - 5.0) * (55.0 - temp) / 625.0 # 625 = 25 * 25
        temp_min_factor = np.clip(temp_min_factor, 0.0, 1.0)
        
        # Humidade ótima para mineralização (ex: 50-80%)
        m_min_factor = np.clip((moisture - 40.0) / 40.0, 0.0, 1.0)
        
        mineral_add = MINERAL_BASE * m_min_factor * temp_min_factor * dt_hours
        new_nutrients = new_nutrients + mineral_add

        # ----- 3) perda extra por pragas de solo -----
        pest_factor = self.soil_pests
        
        # Se sp for uma matriz binária (0 ou 1), ou de contagem,
        # podemos usar um fator de perda que é proporcional à presença/intensidade da praga.
        # Se for binário, (sp > 0) garante que a perda só ocorre onde há praga.
        # Se for de contagem, sp atua como um multiplicador da taxa de perda.
        
        # A perda é uma percentagem dos nutrientes existentes, multiplicada pelo fator de praga
        pest_loss = PEST_LOSS_RATE * pest_factor * dt_hours * new_nutrients
        new_nutrients = new_nutrients - pest_loss

        # ----- 4) difusão espacial (suavização / redistribuição) -----
        m_n = new_nutrients
        
        # A difusão deve ser baseada nos nutrientes (m_n), não na humidade (m)
        # O código original estava a usar 'm' (moisture) em vez de 'm_n' (new_nutrients) para calcular a média dos vizinhos.
        # Vou corrigir para usar 'm_n'.
        
        neigh_avg = (
            np.roll(m_n, 1, axis=0) + np.roll(m_n, -1, axis=0) +      # cima e baixo
            np.roll(m_n, 1, axis=1) + np.roll(m_n, -1, axis=1) +      # esquerda e direita
            np.roll(np.roll(m_n, 1, axis=0), 1, axis=1) +            # diagonal superior esquerda
            np.roll(np.roll(m_n, 1, axis=0), -1, axis=1) +           # diagonal superior direita
            np.roll(np.roll(m_n, -1, axis=0), 1, axis=1) +           # diagonal inferior esquerda
            np.roll(np.roll(m_n, -1, axis=0), -1, axis=1)            # diagonal inferior direita
        ) / 8.0
        diffusion = DIFFUSION_COEF_NUTRIENTS * (neigh_avg - m_n)
        new_nutrients = m_n + diffusion

        # ----- 5) limites finais -----
        new_nutrients = np.clip(new_nutrients, 0.0, 100.0)

        return new_nutrients