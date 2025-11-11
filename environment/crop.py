import numpy as np

from ..config import (
    IDEAL_MOISTURE_TARGET,
    DROUGHT_TOLERANCE,
    STAGE_DURATIONS,
    DAYS_BEFORE_ROT,
    ROT_RATE
)

class Crop():
    """
    Simula o estado das culturas no campo.
    
    Atributos:
        crop_stage: Matriz com o estágio de cada célula (0-4)
                    0: Sem plantação
                    1: Semente
                    2: Germinar
                    3: Vegetação
                    4: Maduro
        crop_type: Matriz com o tipo de planta (0-5)
                   0: Tomate, 1: Pimento, 2: Trigo, 3: Couve, 4: Alface, 5: Cenoura
        crop_health: Matriz com a saúde das plantas (0-100)
        crop_hours_remaining: Matriz com horas restantes até próximo estágio ou apodrecimento
        crop_days_mature: Matriz com dias desde que atingiu maturação (para apodrecimento)
    """

    def __init__(self, rows, cols):
        self.rows = rows
        self.cols = cols
        
        # Estágio da cultura (0: sem plantação, 1-4: estágios de crescimento)
        self.crop_stage = np.zeros((rows, cols), dtype=int)
        
        # Tipo de planta (0-5)
        self.crop_type = np.zeros((rows, cols), dtype=int)
        
        # Saúde da planta (0-100%)
        self.crop_health = np.zeros((rows, cols), dtype=float)
        
        # Horas restantes até próxima transição de estágio
        self.crop_hours_remaining = np.zeros((rows, cols), dtype=float)
        
        # Dias desde que atingiu maturação (para controlar apodrecimento)
        self.crop_days_mature = np.zeros((rows, cols), dtype=float)
        
    def plant_seed(self, row, col, plant_type):
        """
        Planta uma semente na posição (row, col).
        """
        self.crop_stage[row, col] = 1  # Estágio 1: Semente
        self.crop_type[row, col] = plant_type
        self.crop_health[row, col] = 100.0
        # Duração do primeiro estágio (Semente)
        self.crop_hours_remaining[row, col] = STAGE_DURATIONS[plant_type][0]
        self.crop_days_mature[row, col] = 0.0
        return True

    def harvest(self, row, col):
        """
        Colhe a planta na posição (row, col) e limpa a célula.
        Retorna a saúde da planta colhida.
        """
        health = self.crop_health[row, col]
        self.crop_stage[row, col] = 0
        self.crop_type[row, col] = 0
        self.crop_health[row, col] = 0.0
        self.crop_hours_remaining[row, col] = 0.0
        self.crop_days_mature[row, col] = 0.0
        return health

    def _calculate_moisture_stress(self, moisture, crop_type_matrix):
        """
        Calcula o stress hídrico das plantas (0.0 = stress máximo, 1.0 = sem stress).
        
        Args:
            moisture: Matriz de humidade do solo (0-100%)
            crop_type_matrix: Matriz com tipos de plantas
            
        Returns:
            Matriz com fatores de stress (0.0-1.0)
        """
        stress = np.ones_like(moisture, dtype=float)
        
        for r in range(self.rows):
            for c in range(self.cols):
                if self.crop_stage[r, c] > 0:  # Só calcula se houver planta
                    plant_type = int(crop_type_matrix[r, c])
                    target = IDEAL_MOISTURE_TARGET[plant_type]
                    tolerance = DROUGHT_TOLERANCE[plant_type]
                    
                    # Desvio da humidade ideal
                    deviation = abs(moisture[r, c] - target)
                    
                    # Stress aumenta linearmente quando desvio excede tolerância
                    if deviation <= tolerance:
                        stress[r, c] = 1.0  # Sem stress
                    else:
                        excess_deviation = deviation - tolerance
                        stress[r, c] = max(0.0, 1.0 - (excess_deviation / tolerance))
        
        return stress

    def _calculate_nutrient_stress(self, nutrients):
        """
        Calcula o stress por deficiência de nutrientes (0.0 = stress máximo, 1.0 = sem stress).
        
        Args:
            nutrients: Matriz de nutrientes do solo (0-100%)
            
        Returns:
            Matriz com fatores de stress (0.0-1.0)
        """
        # Stress aumenta quando nutrientes < 40%
        # 100% nutrientes = 1.0 (sem stress)
        # 40% nutrientes = 1.0 (sem stress)
        # 0% nutrientes = 0.0 (stress máximo)
        stress = np.clip(nutrients / 40.0, 0.0, 1.0)
        
        # Só aplica stress onde há plantas
        mask = (self.crop_stage == 0)
        stress[mask] = 1.0
        
        return stress

    def _calculate_temperature_stress(self, temperature):
        """
        Calcula o stress térmico das plantas (0.0 = stress máximo, 1.0 = sem stress).
        
        Args:
            temperature: Temperatura do ar (°C)
            
        Returns:
            float: Fator de stress (0.0-1.0)
        """
        # Temperatura ideal: 15-30°C
        # Stress aumenta fora desse intervalo
        if 15 <= temperature <= 30:
            return 1.0  # Sem stress
        elif temperature < 15:
            # Stress por frio (5°C = stress máximo)
            return max(0.0, (temperature - 5.0) / 10.0)
        else:
            # Stress por calor (40°C = stress máximo)
            return max(0.0, (40.0 - temperature) / 10.0)

    def _calculate_pest_damage(self, pest_matrix):
        """
        Calcula o dano causado por pestes às plantas.
        
        Args:
            pest_matrix: Matriz de pestes (0 ou 1)
            
        Returns:
            Matriz com dano por pestes (% de saúde perdida por hora)
        """
        # Pestes causam 2% de dano por hora
        damage = pest_matrix.astype(float) * 2.0
        
        # Só aplica dano onde há plantas
        mask = (self.crop_stage == 0)
        damage[mask] = 0.0
        
        return damage

    def update_crop(self, moisture, nutrients, temperature, pest_matrix, dt_hours=1.0):
        """
        Atualiza o estado das culturas.
        
        Args:
            moisture: Matriz de humidade do solo (0-100%)
            nutrients: Matriz de nutrientes do solo (0-100%)
            temperature: Temperatura do ar (°C)
            pest_matrix: Matriz de pestes (0 ou 1)
            dt_hours: Intervalo de tempo em horas (padrão: 1.0)
        """
        # Máscara de células com plantas
        has_plant = (self.crop_stage > 0)
        
        if not np.any(has_plant):
            return  # Nenhuma planta para atualizar
        
        # --- 1. Calcular fatores de stress ---
        moisture_stress = self._calculate_moisture_stress(moisture, self.crop_type)
        nutrient_stress = self._calculate_nutrient_stress(nutrients)
        temp_stress = self._calculate_temperature_stress(temperature)
        pest_damage = self._calculate_pest_damage(pest_matrix)
        
        # --- 2. Atualizar saúde das plantas ---
        # Stress combinado (produto dos fatores)
        combined_stress = moisture_stress * nutrient_stress * temp_stress
        
        # Perda de saúde por stress (quanto menor o stress, maior a perda)
        # Se stress = 1.0 (sem stress), perda = 0
        # Se stress = 0.0 (stress máximo), perda = 1% por hora
        stress_damage = (1.0 - combined_stress) * 1.0 * dt_hours
        
        # Perda total de saúde
        # Regeneração de saúde (se o stress for baixo, a planta recupera)
        # Se combined_stress = 1.0, regeneração = 2% por hora
        # Se combined_stress < 0.5, regeneração = 0
        regeneration_rate = np.clip((combined_stress - 0.5) * 2.0, 0.0, 1.0) * 2 * dt_hours
        
        # Perda total de saúde
        total_damage = stress_damage + pest_damage * dt_hours
        
        # Alteração líquida na saúde (regeneração - dano)
        health_change = regeneration_rate - total_damage
        
        # Aplicar alteração líquida apenas onde há plantas
        self.crop_health[has_plant] += health_change[has_plant]
        
        # --- 3. Processar apodrecimento (plantas maduras) ---
        mature_mask = (self.crop_stage == 4)
        
        if np.any(mature_mask):
            # Incrementar dias de maturação
            self.crop_days_mature[mature_mask] += dt_hours / 24.0
            
            # Verificar quais plantas devem começar a apodrecer
            for r in range(self.rows):
                for c in range(self.cols):
                    if mature_mask[r, c]:
                        plant_type = int(self.crop_type[r, c])
                        days_mature = self.crop_days_mature[r, c]
                        days_threshold = DAYS_BEFORE_ROT[plant_type]
                        
                        if days_mature > days_threshold:
                            # Apodrecimento: perda de saúde proporcional aos dias excedentes
                            rot_damage = ROT_RATE * dt_hours / 24.0
                            self.crop_health[r, c] -= rot_damage
        
        # --- 4. Limitar saúde (0-100) ---
        self.crop_health = np.clip(self.crop_health, 0.0, 100.0)
        
        # --- 5. Processar morte das plantas ---
        dead_mask = (self.crop_health <= 0.0) & has_plant
        
        if np.any(dead_mask):
            self.crop_stage[dead_mask] = 0
            self.crop_type[dead_mask] = 0
            self.crop_health[dead_mask] = 0.0
            self.crop_hours_remaining[dead_mask] = 0.0
            self.crop_days_mature[dead_mask] = 0.0
        
        # --- 6. Atualizar crescimento (progressão de estágios) ---
        growing_mask = has_plant & (self.crop_stage < 4) & (self.crop_health > 0)
        
        if np.any(growing_mask):
            # Fator de crescimento baseado nas condições (stress reduz crescimento)
            growth_factor = combined_stress
            
            # Reduzir horas restantes proporcionalmente ao fator de crescimento
            # Se stress = 1.0, crescimento normal
            # Se stress = 0.0, crescimento para
            self.crop_hours_remaining[growing_mask] -= dt_hours * growth_factor[growing_mask]
            
            # Verificar transições de estágio
            for r in range(self.rows):
                for c in range(self.cols):
                    if growing_mask[r, c] and self.crop_hours_remaining[r, c] <= 0:
                        # Avançar para próximo estágio
                        current_stage = int(self.crop_stage[r, c])
                        plant_type = int(self.crop_type[r, c])
                        
                        if current_stage < 4:
                            self.crop_stage[r, c] = current_stage + 1
                            
                            # Definir horas para próximo estágio
                            if current_stage < 3:  # Ainda não é maduro
                                self.crop_hours_remaining[r, c] = STAGE_DURATIONS[plant_type][current_stage]
                            else:  # Atingiu maturação
                                self.crop_hours_remaining[r, c] = 0.0
                                self.crop_days_mature[r, c] = 0.0
