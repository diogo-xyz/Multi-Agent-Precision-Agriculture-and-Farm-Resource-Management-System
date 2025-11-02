# `rain_event.py`

Este ficheiro define a classe `Rain`, que simula a ocorrência e a intensidade de eventos de chuva no ambiente de simulação. O modelo incorpora sazonalidade, duração variável e o impacto de condições de seca.

## Classe `Rain`

A classe `Rain` gere o estado da chuva.

| Atributo | Descrição | Tipo |
| :--- | :--- | :--- |
| `self.rain` | Nível de intensidade da chuva: `0` (sem chuva), `1` (fraca), `2` (normal), `3` (forte). | `int` |
| `self._rain_hours_remaining` | Horas restantes para o episódio de chuva atual. | `float` |

### Métodos Principais

| Método | Descrição |
| :--- | :--- |
| `__init__(self)` | Inicializa o estado da chuva como `0` (sem chuva) e o tempo restante como `0.0`. |
| `season_from_day(self, day: int)` | Mapeia o dia do ano para uma das quatro estações (`spring`, `summer`, `autumn`, `winter`), usando um modelo para o Hemisfério Norte. |
| `_short_rain_duration(self, mean_h: float)` | Calcula uma duração de chuva mais curta, usada durante períodos de seca, reduzindo a duração média pela constante `DROUGHT_DURATION_FACTOR`. |
| `_get_next_intensity(self, current_intensity: int, season: str)` | Determina a próxima intensidade de chuva (1, 2 ou 3) com base na `INTENSITY_TRANSITION_MATRIX` (definida em `config.py`), que modela a probabilidade de transição entre intensidades por estação. |
| `update_rain(self, day: int, drought: bool, dt_hours: float = 1.0)` | **Principal método de atualização**. Simula a progressão do evento de chuva:
    1.  Decrementa o tempo restante.
    2.  Se estiver a chover, calcula a probabilidade de **parar mais cedo** (`P_STOP_EARLY_PER_HOUR`) ou de **mudar de intensidade** (`P_CHANGE_INTENSITY_PER_HOUR`), com ajustes em caso de seca.
    3.  Se o episódio terminar, reavalia a probabilidade de começar um novo evento de chuva com base nas `SEASON_PROBS` e nos ajustes de seca (`DROUGHT_PROB_MOD`). |

---

## Modelagem da Chuva

O modelo de chuva é estocástico e dependente do tempo, incorporando:

*   **Sazonalidade:** As probabilidades de ocorrência e a duração média da chuva variam consoante a estação do ano (definidas em `config.py`).
*   **Duração Exponencial:** A duração dos eventos de chuva é amostrada a partir de uma distribuição exponencial, com média definida pela intensidade e estação.
*   **Seca:** A variável `drought` (seca) afeta o modelo, reduzindo a probabilidade de começar a chover e encurtando a duração dos episódios de chuva.
*   **Transição de Intensidade:** A intensidade da chuva pode mudar durante um episódio, seguindo uma matriz de transição probabilística.
