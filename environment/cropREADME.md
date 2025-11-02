# `environment/crop.py`

Este ficheiro define a classe `Crop`, que simula o **estado, saúde e crescimento das culturas** em cada célula do campo. É o componente central para modelar a resposta das plantas às condições ambientais (humidade, nutrientes, temperatura) e a eventos de pragas.

## Classe `Crop`

A classe `Crop` gere o estado das culturas.

| Atributo | Descrição | Valores |
| :--- | :--- | :--- |
| `self.crop_stage` | Estágio de crescimento da planta. | `0` (Sem plantação), `1` (Semente), `2` (Germinar), `3` (Vegetação), `4` (Maduro) |
| `self.crop_type` | Tipo de planta cultivada. | `0` (Tomate), `1` (Pimento), `2` (Trigo), `3` (Couve), `4` (Alface), `5` (Cenoura) |
| `self.crop_health` | Saúde da planta (percentagem). | `0.0` a `100.0` |
| `self.crop_hours_remaining` | Horas restantes para a transição para o próximo estágio. | `float` |
| `self.crop_days_mature` | Dias desde que a planta atingiu a maturação (para calcular apodrecimento). | `float` |

### Métodos Principais

| Método | Descrição |
| :--- | :--- |
| `update_crop(...)` | **Principal método de atualização**. Executa a simulação do crescimento e saúde: calcula o stress combinado (hídrico, nutricional, térmico), aplica a perda de saúde e atualiza a progressão do estágio de crescimento, que é **retardada** pelo stress ambiental. |
| `aply_seed(self, row, col, seed_type)` | **Aplica semente** numa célula específica. Define o estágio para `1` (Semente), a saúde para `100%` e inicializa o tempo para o primeiro estágio. |
| `aply_harvest(self, row, col)` | **Colhe a cultura** numa célula específica. Só é efetuada se a cultura estiver no estágio `4` (Maduro), repondo a célula para o estado `0` (Sem plantação). |
| `_calculate_moisture_stress(...)` | Calcula o fator de stress hídrico (0.0 a 1.0). |
| `_calculate_nutrient_stress(...)` | Calcula o fator de stress por deficiência de nutrientes (0.0 a 1.0). |
| `_calculate_temperature_stress(...)` | Calcula o fator de stress térmico (0.0 a 1.0). |
| `_calculate_pest_damage(...)` | Calcula o dano causado por pestes. |

---

## Mecanismo de Crescimento e Stress

O crescimento e a saúde das culturas são regidos por:

1.  **Stress Combinado:** O fator de stress total é o produto dos fatores de stress individuais (`moisture_stress * nutrient_stress * temp_stress`).
2.  **Dano à Saúde:** A saúde diminui devido ao stress e ao dano direto das pragas.
3.  **Progressão de Estágio:** O crescimento é diretamente proporcional ao fator de stress combinado. Condições ótimas (stress = 1.0) resultam em crescimento normal, enquanto condições de stress (stress < 1.0) retardam o crescimento.
4.  **Apodrecimento:** Plantas maduras (`stage = 4`) começam a perder saúde após um número específico de dias (`DAYS_BEFORE_ROT`), simulando a deterioração.

As novas funções `aply_seed` e `aply_harvest` permitem que os agentes (como o Harvester ou o Logistic) interajam diretamente com o estado da cultura.
