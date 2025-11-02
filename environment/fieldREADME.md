# `environment/field.py`

Este ficheiro define a classe `Field`, que atua como o **ambiente de simulação central** para o sistema multi-agente. Agrega todos os componentes ambientais e coordena a sua atualização, além de fornecer métodos de interface para as ações dos agentes.

## Classe `Field`

A classe `Field` é o contentor do ambiente.

| Atributo | Descrição | Componente |
| :--- | :--- | :--- |
| `self.day`, `self.hours` | Contadores de tempo da simulação. | - |
| `self.temperature` | Simulação da temperatura do ar. | `Temperature` |
| `self.moisture` | Simulação da humidade do solo. | `Moisture` |
| `self.nutrients` | Simulação dos nutrientes do solo. | `Nutrients` |
| `self.crop` | Simulação do estado e crescimento das culturas. | `Crop` |
| `self.pest` | Simulação da propagação de pragas. | `Pest` |
| `self.rain` | Simulação de eventos de chuva. | `Rain` |

### Métodos Principais

| Método | Descrição |
| :--- | :--- |
| `step(self)` | **Principal método de simulação**. Avança o tempo e atualiza sequencialmente todos os componentes ambientais (temperatura, chuva, humidade, nutrientes, pragas, culturas). |
| `aply_irrigation(self, row, col, amount)` | **Ação do Agente Irrigation**. Aplica uma quantidade de água (`amount` em mm) numa célula específica, chamando o método correspondente em `Moisture`. |
| `aply_fertilize(self, row, col, amount)` | **Ação do Agente Fertilizer**. Aplica uma quantidade de fertilizante (`amount` em %) numa célula específica, chamando o método correspondente em `Nutrients`. |
| `aply_seed(self, row, col, seed_type)` | **Ação do Agente Harvester/Logistic**. Aplica semente numa célula específica, chamando o método correspondente em `Crop`. |
| `aply_harvest(self, row, col)` | **Ação do Agente Harvester**. Colhe a cultura numa célula específica, chamando o método correspondente em `Crop`. |
| `aply_pesticide(self, row, col)` | **Ação do Agente Drone**. Aplica pesticida numa célula específica. |
| `get_drone(self, row, col)` | **Leitura do Agente Drone**. Retorna o estágio da cultura e a presença de praga. |
| `get_soil(self, row, col)` | **Leitura do Agente Soil Sensor**. Retorna a temperatura, nutrientes e humidade. |

---

## Fluxo de Simulação e Interação com Agentes

O método `step()` simula a dinâmica natural do ambiente. Os novos métodos `aply_irrigation`, `aply_fertilize`, `aply_seed` e `aply_harvest` servem como a **interface de ação** que os agentes (definidos na pasta `agents/`) utilizam para intervir no ambiente de simulação, respondendo às condições lidas pelos métodos `get_drone` e `get_soil`.

Esta estrutura separa claramente a lógica de simulação ambiental da lógica de tomada de decisão dos agentes.
