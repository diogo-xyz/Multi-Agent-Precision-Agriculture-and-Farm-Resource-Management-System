import numpy as np

from ..config import MM_TO_PCT,EVAP_BASE_COEFF,EVAP_TEMP_THRESHOLD,DIFFUSION_COEF_MOISTURE,FIELD_CAPACITY,LEACH_COEFF,RAIN_NOISE, UPTAKE_RATES_MM_PER_HOUR, IDEAL_MOISTURE_TARGET, DROUGHT_TOLERANCE,IRRIG_TO_PCT

class Moisture():

    def __init__(self, num_linhas, num_colunas):
        # Inicializa a humidade do solo com valores triangulares aleatórios (50-70%)
        self.moisture = np.random.triangular(75, 80, 85, size=(num_linhas, num_colunas))

    def _rain_mm_per_hour(self, nivel_chuva):
        """
        Mapeia o nível de chuva (0-3) para precipitação em mm/h.
        0: Sem chuva (0.0 mm/h)
        1: Chuva leve (4.0 mm/h)
        2: Chuva moderada (20.0 mm/h)
        3: Chuva forte (60.0 mm/h)
        """
        return {0: 0.0, 1: 1, 2: 3, 3: 5}.get(nivel_chuva)

    def _calculate_stress_plant(self, humidade_atual, tipo_planta):
        """
        Calcula o fator de stress da planta (0.0 a 1.0) baseado na humidade atual
        e nas necessidades da planta. 1.0 = sem stress, 0.0 = stress máximo.
        """
        target = IDEAL_MOISTURE_TARGET[tipo_planta]
        tolerancia = DROUGHT_TOLERANCE[tipo_planta]
        
        # Desvio absoluto da humidade ideal
        desvio = np.abs(humidade_atual - target)
        
        # O stress aumenta linearmente quando o desvio excede a tolerância
        # Fator de stress = 1.0 - (desvio / (tolerancia * 2))
        # O fator de 2 na tolerância é para que o stress chegue a 0.0 quando o desvio for 2*tolerancia
        # O stress é calculado com base no desvio em relação ao intervalo [target - tolerancia, target + tolerancia]
        # Se o desvio for 0, stress_factor = 1.0. Se o desvio for 2*tolerancia, stress_factor = 0.0.
        stress_factor = 1.0 - np.clip(desvio - tolerancia, 0.0, tolerancia) / tolerancia
        
        # O stress afeta o uptake, seja por seca (humidade baixa) ou por excesso de água (humidade alta)
        return stress_factor


    def update_moisture(self, rain, temperature, nutrients, crop_stage, crop_type, dt_hours=1.0):
        """
        Atualiza self.moisture (0-100) em função de:
        - nivel_chuva (0..3)
        - temperatura (único valor, °C)
        - nutrients (para lixiviação)
        - crop_stage (matriz de inteiros 0-3)
        - crop_type (matriz de inteiros 0-5)
        - dt_hours: quantas horas avança neste step 
        """

        # 1) Precipitação (Chuva) -> mm/h -> % pontos
        rain_mm = self._rain_mm_per_hour(rain) * dt_hours
        rain_pct = rain_mm * MM_TO_PCT
        # Variação espacial na precipitação
        rain_add = rain_pct * (1.0 + np.random.normal(0, RAIN_NOISE, size=self.moisture.shape))

        # 2) Evaporação (mm -> %), depende da temperatura e da disponibilidade de água
        temp_factor = max(0.0, temperature - EVAP_TEMP_THRESHOLD)
        evap_mm = EVAP_BASE_COEFF * temp_factor * dt_hours
        evap_pct = evap_mm * MM_TO_PCT
        # Evaporação limitada pela água disponível (solo seco evapora menos)
        evap_loss = evap_pct * (self.moisture / 100.0)

        # 3) Absorção/Transpiração pelas Plantas (mm -> %)
        
        # Mapear estágios e tipos para as taxas de absorção
        # estagio_cultura (0-4). 0 = Sem Plantação. 1-4 = Estágios 1-4.
        # O índice da linha na matriz UPTAKE_RATES_MM_PER_HOUR será (estagio_cultura - 1).
        # tipo_cultura (0-5) -> coluna
        
        # Usar np.take para obter a taxa de absorção correta para cada célula
        # A indexação é feita de forma plana (flat)
        rows, cols = self.moisture.shape
        # Ajustar o estágio para a indexação da matriz (1->0, 2->1, 3->2, 4->3)
        # O estágio 0 (Sem Plantação) será mapeado para um índice negativo (-1)
        # que será tratado com np.clip para garantir que a taxa de absorção seja 0.0.
        stage_index = crop_stage - 1
        stage_index_clipped = np.clip(stage_index, 0, UPTAKE_RATES_MM_PER_HOUR.shape[0] - 1)

        indices_flat = stage_index_clipped.flatten() * UPTAKE_RATES_MM_PER_HOUR.shape[1] + crop_type.flatten()

        # Criar uma máscara para células com estágio 0 (Sem Plantação)
        mascara_sem_plantacao = (crop_stage == 0)
                
        # Obter as taxas de absorção (mm/h) para cada célula
        taxas_uptake_flat = np.take(UPTAKE_RATES_MM_PER_HOUR, indices_flat)
        mm_uptake_base = taxas_uptake_flat.reshape(rows, cols) * dt_hours

        # Aplicar taxa de absorção zero para células sem plantação (estágio 0)
        mm_uptake_base[mascara_sem_plantacao] = 0.0
                
        # A transpiração aumenta com a temperatura (simples linear)
        mm_uptake_temp_ajustado = mm_uptake_base * (1.0 + 0.03 * (temperature - 20.0))
        pct_uptake_temp_ajustado = mm_uptake_temp_ajustado * MM_TO_PCT
        
        # Aplicar o fator de stress da planta (reduz o uptake se a humidade estiver baixa)
        fator_stress = self._calculate_stress_plant(self.moisture, crop_type)
        pct_uptake_stress_ajustado = pct_uptake_temp_ajustado * fator_stress
        
        # Não retirar mais humidade do que existe
        uptake = np.minimum(pct_uptake_stress_ajustado, self.moisture)

        # 4) Difusão Espacial (8-vizinhos)
        m = self.moisture
        neigh_avg = (
            np.roll(m, 1, axis=0) + np.roll(m, -1, axis=0) +      # cima e baixo
            np.roll(m, 1, axis=1) + np.roll(m, -1, axis=1) +      # esquerda e direita
            np.roll(np.roll(m, 1, axis=0), 1, axis=1) +            # diagonal superior esquerda
            np.roll(np.roll(m, 1, axis=0), -1, axis=1) +           # diagonal superior direita
            np.roll(np.roll(m, -1, axis=0), 1, axis=1) +           # diagonal inferior esquerda
            np.roll(np.roll(m, -1, axis=0), -1, axis=1)            # diagonal inferior direita
        ) / 8.0
        diffusion = DIFFUSION_COEF_MOISTURE * (neigh_avg - m)

        # 5) Composição
        new_moisture = m + rain_add - evap_loss - uptake + diffusion

        # 6) Lixiviação/Escoamento (Leaching/Runoff)
        excesso = np.maximum(0.0, new_moisture - FIELD_CAPACITY)
        new_nutrients = nutrients.copy()
        
        if np.any(excesso > 0):
            # Fração do excesso é perdida
            perda_lixiviada = excesso * LEACH_COEFF
            new_moisture = new_moisture - perda_lixiviada
            
            # Aplicar perda proporcional de nutrientes
            # Assumindo nutrientes em escala 0-100
            fracao_perda_nutrientes = (perda_lixiviada / 100.0)
            new_nutrients = np.clip(nutrients - (nutrients * fracao_perda_nutrientes), 0, 100)

        # 7) Limites Absolutos
        new_moisture = np.clip(new_moisture, 0.0, 100.0)

        return new_moisture, new_nutrients

    def apply_irrigation(self, row, col, flow_rate_lph):
        """
        Aplica água na célula (row, col) e difunde a humidade para os vizinhos.

        :param row: Índice da linha da célula a ser irrigada.
        :param col: Índice da coluna da célula a ser irrigada.
        :param flow_rate_lph: Caudal de água aplicado (Litros por hora).
        """
        
        # 1. Conversão do Caudal para Aumento de Humidade (%)
        # Assumindo a simplificação: 1 L/h aplicado a 1m² por 1h resulta em 1 mm de água.
        # Caudal total aplicado em mm
        
        # Aumento de humidade em %
        irrigation_pct = flow_rate_lph * IRRIG_TO_PCT 
        
        # 2. Aplicação Inicial na Célula
        delta_moisture = np.zeros_like(self.moisture)
        
        delta_moisture[row, col] = irrigation_pct

        # 3. Humidade Temporária (Humidade Atual + Água Adicionada)
        m_temp = self.moisture + delta_moisture
        
        # 4. Difusão Espacial (8-vizinhos)
        # A difusão atua para suavizar as diferenças de humidade.
        
        # Soma da humidade dos 8 vizinhos para a matriz temporária
        neigh_sum_temp = (
            np.roll(m_temp, 1, axis=0) + np.roll(m_temp, -1, axis=0) +      # cima e baixo
            np.roll(m_temp, 1, axis=1) + np.roll(m_temp, -1, axis=1) +      # esquerda e direita
            np.roll(np.roll(m_temp, 1, axis=0), 1, axis=1) +            # diagonal superior esquerda
            np.roll(np.roll(m_temp, 1, axis=0), -1, axis=1) +           # diagonal superior direita
            np.roll(np.roll(m_temp, -1, axis=0), 1, axis=1) +           # diagonal inferior esquerda
            np.roll(np.roll(m_temp, -1, axis=0), -1, axis=1)            # diagonal inferior direita
        )
        neigh_avg_temp = neigh_sum_temp / 8.0
        
        # Cálculo da difusão: fluxo de humidade (DIFFUSION_COEF_MOISTURE deve ser importado do seu config)
        diffusion = DIFFUSION_COEF_MOISTURE * (neigh_avg_temp - m_temp)
        
        # 5. Composição
        new_moisture = m_temp + diffusion
        
        # 6. Limites Absolutos
        new_moisture = np.clip(new_moisture, 0.0, 100.0)
        
        self.moisture = new_moisture
