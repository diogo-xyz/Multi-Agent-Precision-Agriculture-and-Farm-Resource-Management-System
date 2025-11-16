"""
Módulo Pest para simulação de propagação de pragas em ambientes agrícolas.

Este módulo implementa a lógica de propagação e controlo de pragas numa grelha
2D, utilizando modelos probabilísticos de infeção e efeitos de pesticidas.
"""

import numpy as np
from scipy.signal import convolve2d

from ..config import P_SPREAD

class Pest:
    """
    Simula a propagação de pragas numa grelha 2D.
    
    Esta classe modela a dinâmica de propagação de pragas através de um sistema
    baseado em células, onde cada célula pode estar infetada (1) ou saudável (0).
    A propagação ocorre de forma probabilística para células vizinhas.
    
    Attributes:
        pest (np.ndarray): Matriz 2D de inteiros representando o estado das pragas.
            0 indica ausência de peste, 1 indica presença de peste.
    
    Note:
        A simulação utiliza condições de contorno periódicas (toroidais) para
        modelar um ambiente contínuo.
    """

    def __init__(self, rows, cols):
        """
        Inicializa a grelha de pragas.
        
        Cria uma matriz 2D inicialmente sem pragas (todos os valores a 0).
        
        Args:
            rows (int): Número de linhas da grelha.
            cols (int): Número de colunas da grelha.
        """
        self.pest = np.zeros((rows, cols), dtype=int)

    def update_pest(self):
        """
        Atualiza o estado das pragas através de propagação probabilística.
        
        A propagação segue os seguintes passos:
        1. Identifica células atualmente infetadas
        2. Conta vizinhos infetados para cada célula (8-vizinhança)
        3. Calcula probabilidade de infeção baseada no número de vizinhos infetados
        4. Aplica infeção probabilística às células saudáveis
        
        A probabilidade de infeção de uma célula com N vizinhos infetados é:
        P(infetar) = 1 - (1 - P_SPREAD)^N
        
        onde P_SPREAD é a probabilidade de propagação por cada vizinho infetado.
        
        Returns:
            int: Número total de células infetadas após a atualização.
            
        Note:
            - Células infetadas permanecem infetadas (peste permanente)
            - Utiliza condições de contorno periódicas (wrap)
            - A convolução 2D é usada para contagem eficiente de vizinhos
        """
        # 1. Identificar as células infetadas (valor 1)
        infected_cells = (self.pest == 1)

        # 2. Contar o número de vizinhos infetados para cada célula.
        # Usamos uma convolução com um kernel de 3x3 de uns (exceto o centro)
        # para contar os vizinhos infetados.
        kernel = np.array([[1, 1, 1],
                           [1, 0, 1],
                           [1, 1, 1]], dtype=int)

        # 'mode=same' garante que a matriz de saída tem o mesmo tamanho que a entrada.
        # 'boundary=wrap' implementa condições de contorno periódicas (toroidais),
        # o que é comum em simulações de grelha.
        # Se as condições de contorno forem diferentes (ex: zero-padding),
        # 'boundary' deve ser ajustado (ex: 'fill' com fillvalue=0).
        neighbor_infections = convolve2d(self.pest, kernel, mode='same', boundary='wrap')

        # 3. Identificar as células não infetadas (valor 0)
        uninfected_cells = (self.pest == 0)

        # 4. Calcular a probabilidade de infeção para as células não infetadas.
        # A probabilidade de infeção é 1 - (probabilidade de NÃO ser infetado por N vizinhos)
        # P(infetar) = 1 - P(não infetar)^N
        # Onde N é o número de vizinhos infetados.
        # P(não infetar) = 1 - P_SPREAD
        p_not_infected_by_one = 1.0 - P_SPREAD
        
        # Probabilidade de não ser infetado por N vizinhos é (1 - p_spread)^N
        p_not_infected_by_neighbors = np.power(p_not_infected_by_one, neighbor_infections)
        
        # Probabilidade total de infeção
        p_infection = 1.0 - p_not_infected_by_neighbors

        # 5. Gerar uma matriz de números aleatórios uniformes [0, 1)
        random_draw = np.random.rand(*self.pest.shape)

        # 6. Aplicar a infeção:
        # Uma célula não infetada torna-se infetada se o seu número aleatório
        # for menor que a sua probabilidade de infeção.
        new_infections = (random_draw < p_infection) & uninfected_cells

        # 7. Atualizar a grelha:
        # As células infetadas permanecem infetadas (se a peste for permanente).
        # As novas infeções são adicionadas.
        # Assumindo que a peste é permanente (uma vez 1, permanece 1):
        self.pest = self.pest | new_infections.astype(int)

        # Retorna o número de novas infeções para fins de monitorização
        return np.sum(self.pest)
    
    def apply_pesticide(self, row, col, neighbor_effect=0.75):
        """
        Aplica pesticida numa célula específica e afeta células vizinhas.
        
        O pesticida elimina completamente a peste na célula alvo e tem uma
        probabilidade de eliminar a peste nas células vizinhas (8-vizinhança).
        
        Args:
            row (int): Índice da linha da célula alvo.
            col (int): Índice da coluna da célula alvo.
            neighbor_effect (float, optional): Probabilidade de eliminar a peste
                em cada célula vizinha infetada. Defaults to 0.75 (75%).
                
        Note:
            - A célula central tem eliminação garantida (100%)
            - Cada vizinho infetado é tratado independentemente
            - Utiliza condições de contorno periódicas para identificar vizinhos
            
        Example:
            - pest = Pest(10, 10)
            - pest.apply_pesticide(5, 5, neighbor_effect=0.75)
            # Elimina peste em (5,5) e tem 75% de chance de eliminar em cada vizinho
        """

        rows, cols = self.pest.shape
        
        # 1. Eliminar a peste na célula central
        self.pest[row, col] = 0

        # 2. Identificar vizinhos (com contornos periódicos/toroidais)
        neighbor_offsets = [(-1, -1), (-1, 0), (-1, 1),
                            ( 0, -1),          ( 0, 1),
                            ( 1, -1), ( 1, 0), ( 1, 1)]

        for dr, dc in neighbor_offsets:
            r = (row + dr) % rows
            c = (col + dc) % cols

            # Se o vizinho tem peste, aplica probabilidade de eliminação
            if self.pest[r, c] == 1:
                if np.random.rand() < neighbor_effect:
                    self.pest[r, c] = 0