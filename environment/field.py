"""
Módulo Field para gestão integrada do ambiente agrícola.

Este módulo implementa a classe principal que integra todos os componentes
do ambiente agrícola (humidade, nutrientes, temperatura, culturas, pragas e chuva)
e coordena a sua atualização temporal.
"""

import numpy as np

from .moisture import Moisture
from .temperature import Temperature
from .moisture import Moisture
from .nutrients import Nutrients
from .crop import Crop
from ..events.pest_event import Pest
from ..events.rain_event import Rain
from ..config import TICK_HOURS,ROWS,COLS

class Field:
    """
    Simula o estado completo do campo agrícola e coordena todos os subsistemas.
    
    Esta classe é o componente central da simulação, integrando e coordenando:
    - Estado temporal (dia e hora)
    - Condições ambientais (temperatura, humidade, nutrientes)
    - Culturas e seu crescimento
    - Eventos dinâmicos (chuva, seca, pragas)
    - Atuações de gestão (irrigação, fertilização, pesticidas)
    
    Attributes:
        day (int): Dia atual do ano (1-365).
        hours (int): Hora atual do dia (0-23).
        temperature (Temperature): Gestor de temperatura do ambiente.
        moisture (Moisture): Gestor de humidade do solo.
        nutrients (Nutrients): Gestor de nutrientes do solo.
        crop (Crop): Gestor das culturas plantadas.
        drought (int): Estado de seca (0=inativo, 1=ativo).
        isPestActive (int): Estado de ativação de pragas (0=inativo, 1=ativo).
        pest (Pest): Gestor de propagação de pragas.
        rain (Rain): Gestor de eventos de chuva.
    """

    def __init__(self):
        """
        Inicializa o campo agrícola e todos os seus subsistemas.
        
        Cria instâncias de todos os gestores de subsistemas (temperatura, humidade,
        nutrientes, culturas, pragas e chuva) e define o estado temporal inicial.
        """
        self.day = 183 # 5 inverno, 183 verão
        self.hours = 10

        self.temperature = Temperature(self.day,self.hours)
        self.moisture = Moisture(ROWS,COLS)
        self.nutrients = Nutrients(ROWS,COLS)
        self.crop = Crop(ROWS,COLS)

        self.drought = 0

        self.isPestActive = 0
        self.pest = Pest(ROWS,COLS)

        self.rain = Rain()

    def step(self):
        """
        Avança a simulação em um passo temporal (tick).
        
        Este método coordena a atualização sequencial de todos os subsistemas:
        1. Avança o tempo (hora e dia)
        2. Atualiza a temperatura
        3. Atualiza os eventos de chuva
        4. Atualiza humidade do solo (considera chuva, temperatura, consumo das plantas)
        5. Atualiza nutrientes do solo (considera seca, temperatura, consumo das plantas)
        6. Atualiza propagação de pragas (se ativas)
        7. Atualiza estado das culturas (crescimento, saúde, morte)
        
        Note:
            - O tempo avança em incrementos de TICK_HOURS (definido em config)
            - A ordem de atualização é importante para manter consistência
            - Cada subsistema recebe os estados atualizados dos outros quando necessário
        """
        self.hours = (self.hours + TICK_HOURS) % 24
        self.day = (self.day % 365) + (1 if self.hours == 0 else 0)
    
        self.temperature.temperature = self.temperature.update_temperature(self.day,self.hours)

        self.rain.update_rain(self.day,self.drought,TICK_HOURS)

        self.moisture.moisture, self.nutrients.nutrients = self.moisture.update_moisture(self.rain.rain,
                                                                self.temperature.temperature,
                                                                self.nutrients.nutrients,
                                                                self.crop.crop_stage,
                                                                self.crop.crop_type,
                                                                TICK_HOURS)

        self.nutrients.nutrients = self.nutrients.update_nutrients(self.drought,
                                                                   self.temperature.temperature,
                                                                   self.moisture.moisture,
                                                                   self.crop.crop_type,
                                                                   self.crop.crop_stage,
                                                                   self.pest.pest,
                                                                   TICK_HOURS)

        if (self.isPestActive): 
            on_or_off = self.pest.update_pest()
            self.isPestActive = 1 if on_or_off > 0 else 0

        self.crop.update_crop(
            self.moisture.moisture,
            self.nutrients.nutrients,
            self.temperature.temperature,
            self.pest.pest,
            TICK_HOURS)

    def apply_rain(self,intensity):
        """
        Aplica um evento de chuva manual com intensidade específica.
        
        Args:
            intensity (int): Intensidade da chuva (1=fraca, 2=normal, 3=forte).
            
        Note:
            Este método permite controlo manual de eventos de chuva,
            sobrescrevendo a geração automática de chuva.
        """
        self.rain.apply_rain(intensity,self.day)

    def stop_rain(self):
        """
        Para imediatamente qualquer evento de chuva em curso.
        
        Note:
            Se não estiver a chover (rain=0), o método não tem efeito.
        """
        if (self.rain.rain == 0): return
        self.rain.rain = 0
        self.rain._rain_hours_remaining = 0.0

    def toggle_drought(self):
        """
        Alterna o estado de seca do ambiente.
        
        Muda entre seca ativa (1) e seca inativa (0). A seca afeta:
        - Probabilidade e duração de eventos de chuva
        - Disponibilidade de nutrientes no solo
        - Crescimento das culturas
        
        Note:
            A seca é um estado binário que modifica vários subsistemas.
        """
        self.drought = 0 if self.drought == 1 else 1

    def apply_pest(self):
        """
        Ativa pragas numa célula aleatória do campo.
        
        Escolhe aleatoriamente uma posição e inicia uma infestação de pragas
        que pode propagar-se para células vizinhas nos próximos ticks.
        
        Note:
            - A propagação ocorre automaticamente através de update_pest()
            - Define isPestActive=1 para ativar o sistema de propagação
        """
        self.isPestActive = 1
        row = np.random.randint(0, ROWS)
        col = np.random.randint(0, COLS)
        self.pest.pest[row,col] = 1

    def remove_pest(self):
        """
        Remove todas as pragas do campo.
        
        Limpa completamente a matriz de pragas e desativa o sistema de propagação.
        
        Note:
            Este método elimina instantaneamente todas as infestações,
            útil para eventos de controlo ou reset do ambiente.
        """
        self.isPestActive = 0
        self.pest.pest = np.zeros((ROWS,COLS))

    def apply_pesticide(self,row,col):
        """
        Aplica pesticida numa célula específica.
        
        Elimina completamente a praga na célula alvo e tem 75% de probabilidade
        de eliminar pragas nas células vizinhas.
        
        Args:
            row (int): Índice da linha onde aplicar o pesticida.
            col (int): Índice da coluna onde aplicar o pesticida.
            
        Note:
            O efeito nos vizinhos é probabilístico (neighbor_effect=0.75).
        """
        self.pest.apply_pesticide(row,col,neighbor_effect= 0.75)

    def apply_irrigation(self,row,col,flow_rate_lph):
        """
        Aplica irrigação numa coluna completa do campo.
        
        Irriga todas as células da coluna especificada com a taxa de fluxo dada.
        
        Args:
            row (int): Não utilizado (mantido para compatibilidade de interface).
            col (int): Índice da coluna a irrigar.
            flow_rate_lph (float): Taxa de fluxo de agua.
            
        Note:
            A irrigação é aplicada a TODAS as linhas da coluna especificada,
            independentemente do parâmetro row.
        """
        for i in range(ROWS):
            self.moisture.apply_irrigation(i,col,flow_rate_lph)

    def apply_fertilize(self,row,col,fertilzer_kg):
        """
        Aplica fertilizante numa coluna completa do campo.
        
        Fertiliza todas as células da coluna especificada com a quantidade dada.
        
        Args:
            row (int): Não utilizado (mantido para compatibilidade de interface).
            col (int): Índice da coluna a fertilizar.
            fertilzer_kg (float): Quantidade de fertilizante em quilogramas.
            
        Note:
            A fertilização é aplicada a TODAS as linhas da coluna especificada,
            independentemente do parâmetro row.
        """
        for i in range(ROWS):
            self.nutrients.apply_fertilize(i,col,fertilzer_kg)
            
    def get_drone(self,row,col):
        """
        Obtém dados observáveis por drone numa célula específica.
        
        Simula a perceção de um drone que sobrevoa o campo, capturando
        informações visíveis sobre as culturas e pragas.
        
        Args:
            row (int): Índice da linha a observar.
            col (int): Índice da coluna a observar.
            
        Returns:
            list: Lista com [estágio_cultura, tipo_cultura, nível_pragas].
                - estágio_cultura (int): 0-4
                - tipo_cultura (int): 0-5
                - nível_pragas (int): 0 ou 1
                
        Note:
            Representa dados que podem ser obtidos por observação visual aérea.
        """
        return [self.crop.crop_stage[row,col], self.crop.crop_type[row,col], self.pest.pest[row,col]]

    def get_soil(self, row, col):
        """
        Obtém dados médios de sensores de solo numa coluna.
        
        Simula a perceção de sensores de solo que medem condições subterrâneas.
        Calcula médias de toda a coluna para representar leituras agregadas.
        
        Args:
            row (int): Não utilizado (mantido para compatibilidade de interface).
            col (int): Índice da coluna a medir.
            
        Returns:
            tuple: Tupla com (temperatura_média, nutrientes_médios, humidade_média).
                - temperatura_média (float): Temperatura em °C
                - nutrientes_médios (float): Percentagem de nutrientes (0-100)
                - humidade_média (float): Percentagem de humidade (0-100)
                
        Note:
            Os valores são médias de todas as linhas da coluna especificada,
            simulando sensores distribuídos verticalmente.
        """
        total_temp = 0
        total_nutr = 0
        total_mois = 0
        
        for i in range(ROWS):
            temp = self.temperature.temperature
            nutr = self.nutrients.nutrients[i, col]
            mois = self.moisture.moisture[i, col]
            total_temp += temp
            total_nutr += nutr
            total_mois += mois
        
        avg_temp = total_temp / ROWS
        avg_nutr = total_nutr / ROWS
        avg_mois = total_mois / ROWS

        return avg_temp, avg_nutr, avg_mois

    def plant_seed(self, row, col, plant_type):
        """
        Planta uma semente numa posição específica.
        
        Args:
            row (int): Índice da linha onde plantar.
            col (int): Índice da coluna onde plantar.
            plant_type (int): Tipo de planta a plantar (0-5).
            
        Returns:
            bool: True se a plantação foi bem-sucedida.
            
        Note:
            Delega a operação para o gestor de culturas.
        """
        return self.crop.plant_seed(row, col, plant_type)

    def harvest(self, row, col):
        """
        Colhe a planta numa posição específica.
        
        Args:
            row (int): Índice da linha onde colher.
            col (int): Índice da coluna onde colher.
            
        Returns:
            float: Saúde da planta colhida (0-100%), representando o rendimento.
            
        Note:
            Delega a operação para o gestor de culturas.
        """
        return self.crop.harvest(row, col)