# `environment/moisture.py`

Este ficheiro define a classe `Moisture`, que simula a **dinâmica da humidade do solo** em cada célula do campo. É um modelo de balanço hídrico que considera a entrada de água (chuva, irrigação), a perda (evaporação, absorção pelas plantas) e a redistribuição (difusão, lixiviação).

## Classe `Moisture`

A classe `Moisture` gere a humidade do solo.

| Atributo | Descrição | Tipo |
| :--- | :--- | :--- |
| `self.moisture` | Matriz 2D com a percentagem de humidade do solo (0-100%). | `numpy.ndarray` (float) |

### Métodos Principais

| Método | Descrição |
| :--- | :--- |
| `update_moisture(...)` | **Principal método de atualização**. Calcula a nova humidade do solo com base na precipitação, evaporação, absorção pelas plantas, difusão espacial e lixiviação/escoamento. |
| `aply_irrigation(self, row, col, amount)` | **Ação de Irrigação**. Adiciona uma quantidade de água (`amount` em mm) à humidade de uma célula específica, convertendo milímetros para percentagem de humidade (`MM_TO_PCT`). |
| `_rain_mm_per_hour(self, nivel_chuva)` | Mapeia o nível de intensidade da chuva para a taxa de precipitação em milímetros por hora (mm/h). |
| `_calculate_stress_plant(...)` | Calcula o fator de stress hídrico que afeta a absorção de água pelas plantas. |

---

## Balanço Hídrico e Intervenção

A principal alteração é a adição do método `aply_irrigation`, que permite a intervenção direta dos agentes no ambiente:

*   **Balanço Natural:** O método `update_moisture` simula o ciclo natural da água.
*   **Intervenção:** O método `aply_irrigation` permite que o Agente Irrigation aumente a humidade do solo numa célula específica, simulando uma ação de irrigação. O excesso de água resultante desta ação será tratado pelo mecanismo de lixiviação na próxima chamada a `update_moisture`.

Este modelo garante que a humidade do solo é um fator dinâmico e espacialmente variável, crucial para o crescimento das culturas. O método `update_moisture` também retorna a matriz de nutrientes atualizada, pois a lixiviação de água causa a perda de nutrientes.
