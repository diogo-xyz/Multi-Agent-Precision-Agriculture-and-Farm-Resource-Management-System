# `pest_event.py`

Este ficheiro define a classe `Pest`, responsável por simular a **propagação de uma praga** (peste) no campo agrícola, modelado como uma grelha 2D. A simulação utiliza conceitos de autómato celular e probabilidade para determinar a infeção de células vizinhas.

## Classe `Pest`

A classe `Pest` gere o estado da praga no campo.

| Atributo | Descrição | Tipo |
| :--- | :--- | :--- |
| `self.pest` | Matriz 2D onde `0` representa ausência de peste e `1` representa presença de peste. | `numpy.ndarray` (int) |

### Métodos Principais

| Método | Descrição |
| :--- | :--- |
| `__init__(self, rows, cols)` | Inicializa a grelha da peste com dimensões `rows` x `cols`, preenchida com zeros (sem peste inicial). |
| `update_pest(self)` | **Atualiza o estado da peste**, simulando a sua propagação. Utiliza a função `scipy.signal.convoluve2d` com um *kernel* de 3x3 para contar os vizinhos infetados de cada célula. A probabilidade de infeção de uma célula não infetada é calculada com base no número de vizinhos infetados e na constante `P_SPREAD` (definida em `config.py`). |
| `apply_pesticide(self, row, col, neighbor_effect=0.75)` | Simula a **aplicação de pesticida** numa célula específica. Elimina a peste na célula central e tenta eliminar a peste nos 8 vizinhos com uma probabilidade definida por `neighbor_effect` (padrão: 75%). |

---

## Mecanismo de Propagação (`update_pest`)

O método de atualização segue os seguintes passos:

1.  **Identificação de Células Infetadas:** Localiza as células com valor `1`.
2.  **Contagem de Vizinhos:** Usa a convolução 2D para contar quantos dos 8 vizinhos de cada célula estão infetados.
3.  **Cálculo da Probabilidade de Infeção:** A probabilidade de uma célula não infetada ser infetada é dada por:
    $$P(\text{infetar}) = 1 - (1 - P_{\text{SPREAD}})^N$$
    Onde $N$ é o número de vizinhos infetados e $P_{\text{SPREAD}}$ é a probabilidade de propagação por um único vizinho.
4.  **Aplicação da Infeção:** Gera números aleatórios e compara-os com a probabilidade de infeção para determinar as novas células infetadas.
5.  **Atualização da Grelha:** As novas infeções são adicionadas à grelha, assumindo que a peste é permanente (uma vez infetada, a célula permanece `1` até ser tratada).
