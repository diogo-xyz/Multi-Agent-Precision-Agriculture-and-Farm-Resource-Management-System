import numpy as np

from ..config import (
    SEASON_PROBS,
    MEAN_DURATION_HOURS_BASE,
    P_STOP_EARLY_PER_HOUR,
    EXTREME_OVERRIDE_PROB,
    DROUGHT_PROB_MOD,
    DROUGHT_DURATION_FACTOR,
)


class Rain:
    """
    Simula eventos de chuva com base na estação do ano, intensidade e condições de seca.
    """

    def __init__(self):
        # 0: não está a chover | 1: chuva fraca | 2: chuva normal | 3: chuva forte
        self.rain = 0
        self._rain_hours_remaining = 0.0

    def apply_rain(self,intensity,day):
        self.rain = intensity
        mean_h = MEAN_DURATION_HOURS_BASE[self.season_from_day(day)][intensity]
        self._rain_hours_remaining = max(1.0, np.random.exponential(scale=mean_h))

    def season_from_day(self, day: int) -> str:
        """
        Mapa simples de dia do ano -> estação (Northern Hemisphere).
        Mar-May = spring, Jun-Aug = summer, Sep-Nov = autumn, Dec-Feb = winter
        """
        # Ajustado para considerar anos bissextos (dia 60 é 1 de Março)
        if 60 <= day <= 151:
            return "spring"
        elif 152 <= day <= 243:
            return "summer"
        elif 244 <= day <= 334:
            return "autumn"
        else:
            return "winter"

    def _short_rain_duration(self, mean_h: float) -> float:
        """Retorna duração curta para episódios de chuva em seca."""
        # Reduz a média e garante um mínimo de 0.5 horas
        return max(0.5, np.random.exponential(scale=max(1.0, mean_h / DROUGHT_DURATION_FACTOR)))

    def update_rain(self, day: int, drought: bool, dt_hours: float = 1.0):
        """
        Atualiza self.rain (0..3) com sazonalidade, duração e transições de intensidade.
        """

        season = self.season_from_day(day)
        
        # --- Atualizar tempo restante ---
        self._rain_hours_remaining -= dt_hours

        # --- Se ainda em episódio de chuva (self.rain > 0) ---
        if self._rain_hours_remaining > 0 and self.rain > 0:
            
            # Ajustes na probabilidade de parar/mudar devido à seca
            p_stop_early = P_STOP_EARLY_PER_HOUR
            ####p_change_intensity = P_CHANGE_INTENSITY_PER_HOUR
            
            if drought:
                # Aumentar a chance de parar mais cedo durante a seca
                p_stop_early *= 2.0 
                # Reduzir a chance de mudança de intensidade (chuvas mais estáveis, mas fracas)
                ####p_change_intensity *= 0.5 

            # Probabilidades ajustadas pelo tempo (dt_hours)
            prob_stop = 1 - (1 - p_stop_early) ** dt_hours
            ####prob_change = 1 - (1 - p_change_intensity) ** dt_hours

            # 1. Parar cedo?
            if np.random.random() < prob_stop:
                self._rain_hours_remaining = 0.0
                self.rain = 0

                        
            return  # Mantém episódio

        # --- Caso episódio tenha terminado (self._rain_hours_remaining <= 0) ou não esteja a chover (self.rain == 0) ---
        
        # O estado atual é 0 (não está a chover)
        self.rain = 0

        if self._rain_hours_remaining > 0: return
        
        # 1. Obter probabilidades base sazonais
        probs = SEASON_PROBS.get(season).copy()

        # 2. Ajustes para seca (se não estiver a chover)
        if drought:
            # Reduzir a probabilidade de começar a chover
            probs *= DROUGHT_PROB_MOD
            probs /= probs.sum()  # normalizar

        # 3. Amostrar o novo estado (0 a 3)
        new_state = int(np.random.choice(4, p=probs))

        # 4. Override extremo raro (chuvas fortes fora de época)
        if season == "summer" and np.random.random() < EXTREME_OVERRIDE_PROB:
            new_state = 3
            
        # 5. Aplicar novo estado e duração
        self.rain = new_state
        mean_h = MEAN_DURATION_HOURS_BASE[season][new_state]

        if new_state > 0:
            # Se começar a chover (new_state > 0)
            if drought:
                # Duração mais curta se começar a chover durante a seca
                self._rain_hours_remaining = self._short_rain_duration(mean_h)
            else:
                self._rain_hours_remaining = max(1.0, np.random.exponential(scale=mean_h))
        else:
            # Se continuar sem chover (new_state == 0)
            # A duração é o tempo até a próxima reavaliação (próximo evento de não-chuva)
            self._rain_hours_remaining = max(1.0, np.random.exponential(scale=mean_h))
            
        # Garantir que o tempo restante é pelo menos dt_hours para o próximo ciclo
        self._rain_hours_remaining = max(dt_hours, self._rain_hours_remaining)

        return