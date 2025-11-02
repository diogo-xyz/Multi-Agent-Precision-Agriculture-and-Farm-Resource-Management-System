import numpy as np

class Temperature:
    def __init__(self, day, hour):
        self.temperature = self.update_temperature(day, hour)

    def day_length(self, day):
        """
        Calcula sunrise e sunset (em horas) ao longo do ano
        usando uma latitude fixa (~40° N, tipo Portugal)
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