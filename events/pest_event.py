import numpy as np
from scipy.signal import convolve2d

from ..config import P_SPREAD

class Pest:
    """
    Simula a propagação de uma "peste" numa grelha 2D.
    0 representa ausência de peste, 1 representa presença de peste.
    """

    def __init__(self, rows, cols):
        """
        Inicializa a grelha da peste.
        """
        self.pest = np.zeros((rows, cols), dtype=int)

    def update_pest(self):
        """
        Atualiza o estado da peste.
        A peste propaga-se para vizinhos não infetados com a probabilidade p_spread.
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

        # Se a peste puder desaparecer, a lógica seria mais complexa,
        # mas para propagação simples, esta é a abordagem.

        # Retorna o número de novas infeções para fins de monitorização
        #return np.sum(new_infections)
        return