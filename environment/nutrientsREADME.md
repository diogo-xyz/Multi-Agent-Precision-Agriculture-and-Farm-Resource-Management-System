# `environment/nutrients.py`

Este ficheiro define a classe `Nutrients`, que simula a **dinâmica dos nutrientes do solo** em cada célula do campo. O modelo considera o consumo pelas plantas, a mineralização natural, a perda por pragas, a redistribuição espacial e a **aplicação de fertilizante**.

## Classe `Nutrients`

A classe `Nutrients` gere os nutrientes do solo.

| Atributo | Descrição | Tipo |
| :--- | :--- | :--- |
| `self.nutrients` | Matriz 2D com a percentagem de nutrientes do solo (0-100%). | `numpy.ndarray` (float) |
| `self.soil_pests` | Matriz 2D que indica a presença/intensidade de pragas no solo. | `numpy.ndarray` (float) |

### Métodos Principais

| Método | Descrição |
| :--- | :--- |
| `update_nutrients(...)` | **Principal método de atualização**. Calcula a nova concentração de nutrientes com base no consumo pelas plantas, mineralização, perda por pragas e difusão espacial. |
| `aply_fertilize(self, row, col, amount)` | **Ação de Fertilização**. Adiciona uma quantidade de nutrientes (`amount` em %) à célula específica. O valor é limitado a 100%. |

---

## Dinâmica de Nutrientes e Intervenção

A principal alteração é a adição do método `aply_fertilize`, que permite a intervenção direta dos agentes no ambiente:

*   **Ciclo Natural:** O método `update_nutrients` simula o ciclo natural de nutrientes, onde o consumo e a mineralização são regulados pela humidade e temperatura.
*   **Intervenção:** O método `aply_fertilize` permite que o Agente Fertilizer aumente a concentração de nutrientes numa célula específica, simulando uma ação de fertilização.

O modelo de nutrientes é crucial, pois a sua concentração afeta o fator de stress nutricional das culturas (em `crop.py`), influenciando diretamente o crescimento e a saúde das plantas. A perda de nutrientes por lixiviação é tratada indiretamente através do método `update_moisture` em `moisture.py`.
