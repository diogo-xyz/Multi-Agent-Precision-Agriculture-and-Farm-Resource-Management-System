"""
Módulo Rain para simulação de eventos de precipitação em ambientes agrícolas.

Este módulo implementa a lógica de geração e gestão de eventos de chuva,
considerando sazonalidade, intensidade, duração e condições de seca.
"""

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
    Simula eventos de chuva com sazonalidade e dinâmica temporal.
    
    Esta classe modela a ocorrência, intensidade e duração de eventos de chuva,
    considerando:
    - Variação sazonal das probabilidades de chuva
    - Diferentes intensidades (fraca, normal, forte)
    - Efeitos de condições de seca
    - Durações variáveis e transições de estado
    
    Attributes:
        rain (int): Intensidade atual da chuva.
            0 = não está a chover
            1 = chuva fraca
            2 = chuva normal
            3 = chuva forte
        _rain_hours_remaining (float): Horas restantes do episódio de chuva atual.
    
    Note:
        As probabilidades e durações são ajustadas automaticamente com base
        na estação do ano e presença de seca.
    """

    def __init__(self):
        """
        Inicializa o sistema de chuva.
        
        O estado inicial é sem chuva (rain=0) e sem duração restante.
        """
        # 0: não está a chover | 1: chuva fraca | 2: chuva normal | 3: chuva forte
        self.rain = 0
        self._rain_hours_remaining = 0.0

    def apply_rain(self,intensity,day):
        """
        Aplica um evento de chuva manual com intensidade específica.
        
        Este método permite forçar um evento de chuva (por exemplo, através
        de controlo humano), definindo a intensidade e calculando uma duração
        apropriada baseada na estação atual.
        
        Args:
            intensity (int): Intensidade da chuva a aplicar (1=fraca, 2=normal, 3=forte).
            day (int): Dia do ano para determinar a estação.
            
        Nota:
            A duração é amostrada de uma distribuição exponencial com média
            dependente da estação e intensidade.
        """

        self.rain = intensity
        mean_h = MEAN_DURATION_HOURS_BASE[self.season_from_day(day)][intensity]
        self._rain_hours_remaining = max(1.0, np.random.exponential(scale=mean_h))

    def season_from_day(self, day: int) -> str:
        """
        Determina a estação do ano a partir do dia.
        
        Utiliza um mapeamento simplificado baseado no Hemisfério Norte:
        - Primavera (spring): dias 80-171 (Março-Maio)
        - Verão (summer): dias 172-263 (Junho-Agosto)
        - Outono (autumn): dias 264-355 (Setembro-Novembro)
        - Inverno (winter): dias 1-79 (Dezembro-Fevereiro)
        
        Args:
            day (int): Dia do ano (1-365, considerando anos bissextos).
            
        Returns:
            str: Nome da estação ('spring', 'summer', 'autumn', ou 'winter').
            
        Note:
            Ajustado para considerar anos bissextos.
        """

        if 80 <= day < 172:
            return "Spring"
        elif 172 <= day < 264:
            return "Summer"
        elif 264 <= day < 355:
            return "Autumn"
        else:
            return "Winter"    

    def _short_rain_duration(self, mean_h: float) -> float:
        """
        Calcula duração reduzida para episódios de chuva durante seca.
        
        Durante períodos de seca, os episódios de chuva tendem a ser mais curtos.
        Este método reduz a duração média e garante um mínimo.
        
        Args:
            mean_h (float): Duração média em horas para condições normais.
            
        Returns:
            float: Duração ajustada em horas (mínimo 0.5 horas).
            
        Note:
            A duração é reduzida pelo fator DROUGHT_DURATION_FACTOR e amostrada
            de uma distribuição exponencial.
        """

        # Reduz a média e garante um mínimo de 0.5 horas
        return max(0.5, np.random.exponential(scale=max(1.0, mean_h / DROUGHT_DURATION_FACTOR)))

    def update_rain(self, day: int, drought: bool, dt_hours: float = 1.0):
        """
        Atualiza o estado da chuva considerando sazonalidade, seca e transições.
        
        Este método é o núcleo da simulação de chuva, gerindo:
        1. Continuação de episódios em curso (decremento do tempo restante)
        2. Possibilidade de parar cedo (mais provável durante seca)
        3. Início de novos episódios quando o tempo restante expira
        4. Ajustes de probabilidade baseados na estação e seca
        5. Eventos extremos raros (chuvas fortes fora de época)
        
        O processo de transição:
        - Se está a chover e há tempo restante: pode continuar ou parar cedo
        - Se o tempo expirou ou não está a chover: amostra novo estado
        - Probabilidades ajustadas pela estação e condição de seca
        - Durações amostradas de distribuições exponenciais
        
        Args:
            day (int): Dia do ano atual para determinar a estação.
            drought (bool): Se há condições de seca ativas.
            dt_hours (float, optional): Incremento de tempo em horas. Defaults to 1.0.
            
        Note:
            - Durante seca: probabilidade de chuva reduzida, durações mais curtas,
              maior chance de parar cedo
            - Eventos extremos: pequena chance de chuva forte no verão
            - Usa distribuições exponenciais para durações realistas
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