# `environment/temperature.py`

Este ficheiro define a classe `Temperature`, responsável por simular a **temperatura do ar** ao longo do tempo. O modelo incorpora variações anuais (sazonalidade) e variações diárias (ciclo dia/noite), baseadas em princípios de climatologia.

## Classe `Temperature`

A classe `Temperature` gere a temperatura ambiente.

| Atributo | Descrição | Tipo |
| :--- | :--- | :--- |
| `self.temperature` | Temperatura atual do ar em graus Celsius (°C). | `float` |

### Métodos Principais

| Método | Descrição |
| :--- | :--- |
| `__init__(self, day, hour)` | Inicializa a temperatura com base no dia e hora atuais. |
| `day_length(self, day)` | Calcula a hora do nascer e pôr do sol (em horas) para um determinado dia do ano, assumindo uma latitude fixa de 40° N (similar a Portugal). |
| `update_temperature(self, day, hour)` | **Principal método de atualização**. Calcula a temperatura atual com base em:
    1.  **Variação Anual:** Define uma temperatura média anual que varia sinusoidalmente ao longo do ano (pico em meados de julho).
    2.  **Variação Diária:** Modela o ciclo de aquecimento (do nascer do sol ao pico de calor, ~14:30h) e arrefecimento (do pico de calor ao nascer do sol), usando funções trigonométricas e exponenciais para simular um ciclo diário mais realista.
    3.  **Ruído:** Adiciona um pequeno ruído aleatório para simular flutuações atmosféricas. |

---

## Modelo de Variação Diária

O modelo de variação diária da temperatura é dividido em três períodos:

1.  **Aquecimento:** Do nascer do sol (`sunrise`) até ao pico de calor (`tmax_hour`), a temperatura aumenta de `T_min_day` para `T_max_day` seguindo uma curva senoidal modificada.
2.  **Arrefecimento Lento:** Do pico de calor até ao pôr do sol (`sunset`), a temperatura diminui suavemente.
3.  **Período Noturno:** Do pôr do sol ao nascer do sol, a temperatura arrefecimento exponencialmente em direção à temperatura mínima diária (`T_min_day`).

Este modelo garante que a temperatura é um fator dinâmico e sazonalmente variável no ambiente de simulação.
