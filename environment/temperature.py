"""
Módulo Temperature para simulação de temperatura ambiente diária e anual.

Este módulo implementa um modelo realista de variação de temperatura considerando
ciclos anuais, duração do dia (dependente da latitude e época do ano) e padrões
diários de aquecimento e arrefecimento.
"""

import numpy as np

class Temperature:
    """
    Simula a temperatura ambiente com variação anual e diária realista.
    
    Esta classe modela a temperatura do ar considerando:
    - Variação anual baseada na declinação solar
    - Duração do dia dependente da latitude e época do ano
    - Ciclo diário com três fases distintas:
      * Aquecimento (nascer do sol até pico de calor)
      * Arrefecimento lento (pico até pôr do sol)
      * Arrefecimento noturno exponencial
    - Ruído estocástico para simular flutuações atmosféricas
    
    Attributes:
        temperature (float): Temperatura atual em graus Celsius.
    
    Note:
        O modelo usa latitude fixa de 40°N (aproximadamente Portugal) e considera
        o pico de temperatura anual em meados de julho (dia ~200).
    """

    def __init__(self, day, hour):
        """
        Inicializa o sistema de temperatura.
        
        Calcula a temperatura inicial baseada no dia e hora fornecidos.
        
        Args:
            day (int): Dia do ano (1-365).
            hour (int): Hora do dia (0-23).
        """
        self.temperature = self.update_temperature(day, hour)

    def day_length(self, day):
        """
        Calcula os horários de nascer e pôr do sol para um dia específico.
        
        Utiliza cálculos astronómicos baseados na declinação solar e latitude
        para determinar a duração do dia e os horários de nascer e pôr do sol.
        O modelo assume latitude fixa de 40°N (típica de Portugal).
        
        A declinação solar varia ao longo do ano devido à inclinação axial da Terra,
        afetando a duração do dia:
        - Solstício de verão (~dia 172): dias mais longos
        - Solstício de inverno (~dia 355): dias mais curtos
        - Equinócios (~dias 80 e 265): dia ≈ noite
        
        Args:
            day (int): Dia do ano (1-365).
            
        Returns:
            tuple: (nascer_do_sol, pôr_do_sol) em horas (formato decimal).
                - nascer_do_sol (float): Hora do nascer do sol (0-24).
                - pôr_do_sol (float): Hora do pôr do sol (0-24).
                
        Note:
            - Usa np.clip para evitar erros de domínio em latitudes extremas
            - O dia de referência é ajustado para o equinócio (dia 80)
            - Valores limitados ao intervalo [0, 24] horas
        """
        latitude = np.radians(40)  # fixa
        # Ajuste do dia de referência para o equinócio
        delta = np.radians(23.44) * np.sin(2 * np.pi * (day - 80) / 365)  # declinação solar
        
        # Uso de np.clip para evitar erros de domínio (DomainError) em latitudes extremas
        arg_arccos = -np.tan(latitude) * np.tan(delta)
        omega_s = np.arccos(np.clip(arg_arccos, -1.0, 1.0))
        
        D = (2 * omega_s * 180 / np.pi) / 15  # comprimento do dia em horas
        
        # Nascer e pôr do sol
        sunrise = 12 - D / 2
        sunset = 12 + D / 2
        
        # Limites
        sunrise = max(0, sunrise)
        sunset = min(24, sunset)
        
        return sunrise, sunset

    def update_temperature(self, day, hour):
        # --- Parâmetros de Variação Anual ---
        # Ajuste do pico de temperatura anual para o dia ~200 (meados de julho)
        T_mean_year = 15 + 10 * np.sin(2 * np.pi * (day - 110) / 365)

        # Tmin e Tmax diárias (amplitude diária)
        T_min_day = T_mean_year - 5
        T_max_day = T_mean_year + 8

        # --- Parâmetros de Variação Diária ---
        sunrise, sunset = self.day_length(day)
        tmax_hour = 14.5  # Pico de calor tipicamente entre 14h e 15h

        # A temperatura mínima ocorre pouco antes do nascer do sol
        T_min = T_min_day
        # A temperatura máxima ocorre no tmax_hour
        T_max = T_max_day

        # --- Modelo de Variação Diária (Mais Realista) ---
        
        # 1. Período de Aquecimento (Nascer do Sol até Pico de Calor)
        if sunrise <= hour <= tmax_hour:
            # Curva senoidal modificada para um aumento mais rápido
            h_norm = (hour - sunrise) / (tmax_hour - sunrise)
            temperature = T_min + (T_max - T_min) * np.sin(np.pi * h_norm / 2)
            
        # 2. Período de Arrefecimento Lento (Pico de Calor até Pôr do Sol)
        elif tmax_hour < hour <= sunset:
            # Arrefecimento suave
            h_norm = (hour - tmax_hour) / (sunset - tmax_hour)
            T_tmax = T_max
            # T_sunset é a temperatura ao pôr do sol (exemplo: 30% da amplitude diária acima de T_min)
            T_sunset_calc = T_min + (T_max - T_min) * 0.3 
            
            temperature = T_sunset_calc + (T_tmax - T_sunset_calc) * np.cos(np.pi * h_norm / 2)
            
        # 3. Período Noturno (Pôr do Sol até Nascer do Sol)
        else:
            # Calcula a diferença de tempo desde o pôr do sol
            if hour > sunset:
                delta_h = hour - sunset
            else:
                delta_h = (24 - sunset) + hour
            
            # Temperatura ao pôr do sol (usada como ponto de partida para o arrefecimento)
            T_sunset_calc = T_min + (T_max - T_min) * 0.3
            
            # Resfriamento exponencial em direção a T_min
            temperature = T_min + (T_sunset_calc - T_min) * np.exp(-delta_h / 5)

        # Ruído leve (condições atmosféricas)
        temperature += np.random.normal(0, 0.3)

        return round(temperature, 2)