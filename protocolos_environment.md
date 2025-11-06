# Formatos de Mensagens Esperados pelo `FarmEnvironmentAgent`

O `FarmEnvironmentAgent` foi concebido para interagir com outros agentes (como agentes de controlo de irrigação, fertilização, etc.) e com um sistema de controlo humano/teste através de mensagens baseadas no protocolo **FIPA** (Foundation for Intelligent Physical Agents), utilizando a biblioteca **SPADE**.

As mensagens são estruturadas da seguinte forma:

1.  **Corpo da Mensagem (`msg.body`):** Deve ser uma *string* **JSON** válida.
2.  **Campo Obrigatório no JSON:** O JSON deve conter obrigatoriamente o campo `"action"`, que define a operação a ser executada.
3.  **Metadados (`msg.metadata`):** O campo `"ontology"` é crucial para determinar o tipo de interação.
4.  **Performative (`msg.performative`):** Define a intenção da mensagem (e.g., pedido de dados, execução de uma ação).

---

## 1. Interações Baseadas na Ontologia

O agente suporta três ontologias principais, que definem o contexto da mensagem:

| Ontologia | Performatives Suportadas | Descrição | Função de Processamento |
| :--- | :--- | :--- | :--- |
| `ONTOLOGY_FARM_DATA` | `request` | Pedidos de **Perceção** (leitura de dados do ambiente). | `handle_agent_request` |
| `ONTOLOGY_FARM_ACTION` | `act` | Pedidos de **Atuação** (modificação do ambiente). | `handle_agent_request` |
| `ONTOLOGY_DYNAMIC_EVENT` | `request`, `inform`, `act` | Comandos de **Controlo** para simular eventos dinâmicos (chuva, seca, peste). | `handle_dynamic_event` |

---

## 2. Formatos de Mensagens Detalhados

### A. Pedidos de Perceção (`ONTOLOGY_FARM_DATA`)

Estes pedidos usam a performative **`request`** e a ontologia **`ONTOLOGY_FARM_DATA`**.

| Ação (`action`) | Parâmetros JSON Adicionais | Descrição |
| :--- | :--- | :--- |
| `get_soil` | `"row"`, `"col"` | Obtém dados do solo (temperatura, nutrientes, humidade) numa célula específica. |
| `get_drone` | `"row"`, `"col"` | Obtém dados de observação (fase da cultura, tipo de cultura, nível de pragas) numa célula específica. |

**Exemplo de Mensagem (JSON Body):**

```json
{
    "action": "get_soil",
    "row": 2,
    "col": 3
}
```

**Exemplo de Resposta (JSON Body, Performative `inform`):**

```json
{
    "status": "success",
    "action": "get_soil",
    "data": {
        "temperature": 25.5,
        "nutrients": 0.85,
        "moisture": 0.62
    }
}
```

### B. Pedidos de Atuação (`ONTOLOGY_FARM_ACTION`)

Estes pedidos usam a performative **`act`** e a ontologia **`ONTOLOGY_FARM_ACTION`**.

| Ação (`action`) | Parâmetros JSON Adicionais | Descrição |
| :--- | :--- | :--- |
| `apply_irrigation` | `"row"`, `"col"`, `"flow_rate"` | Aplica irrigação numa célula com uma determinada taxa de fluxo. |
| `apply_fertilize` | `"row"`, `"col"`, `"fertilizer_kg"` | Aplica fertilizante numa célula. |
| `apply_pesticide` | `"row"`, `"col"` | Aplica pesticida numa célula. |
| `plant_seed` | `"row"`, `"col"`, `"plant_type"` | Planta uma semente de um tipo específico numa célula. |
| `harvest` | `"row"`, `"col"` | Realiza a colheita numa célula. |

**Exemplo de Mensagem (JSON Body):**

```json
{
    "action": "apply_irrigation",
    "row": 5,
    "col": 5,
    "flow_rate": 0.15
}
```

**Exemplo de Resposta (JSON Body, Performative `inform`):**

```json
{
    "status": "success",
    "action": "apply_irrigation",
    "message": "Irrigação aplicada em (5,5) com taxa 0.15."
}
```

### C. Eventos Dinâmicos (`ONTOLOGY_DYNAMIC_EVENT`)

Estes comandos são tipicamente usados para controlo ou teste, e podem usar performatives como `request`, `inform` ou `act`.

| Ação (`action`) | Parâmetros JSON Adicionais | Descrição |
| :--- | :--- | :--- |
| `apply_rain` | `"intensity"` | Ativa a chuva com uma intensidade específica. |
| `stop_rain` | Nenhum | Para a chuva. |
| `toggle_drought` | Nenhum | Alterna o estado de seca (ativa/desativa). |
| `apply_pest` | Nenhum | Ativa uma praga numa célula aleatória. |
| `remove_pest` | Nenhum | Remove todas as pragas (limpa a grelha). |

**Exemplo de Mensagem (JSON Body):**

```json
{
    "action": "apply_rain",
    "intensity": 0.5
}
```

**Exemplo de Resposta (JSON Body, Performative `inform`):**

```json
{
    "status": "success",
    "action": "apply_rain",
    "message": "Chuva de intensidade 0.5 ativada."
}
```

---

## 3. Formato de Resposta Padrão

Todas as respostas do `FarmEnvironmentAgent` (após um pedido de perceção ou atuação) são enviadas com a performative **`inform`** e contêm um corpo JSON com a seguinte estrutura:

| Campo | Tipo | Descrição |
| :--- | :--- | :--- |
| `"status"` | *string* | O estado da operação: `"success"` ou `"error"`. |
| `"action"` | *string* | A ação que foi processada (eco do pedido). |
| `"message"` | *string* | Uma mensagem descritiva (presente em caso de sucesso ou erro). |
| `"data"` / `"yield"` | *object* / *float* | Dados específicos retornados (e.g., dados do solo para `get_soil`, rendimento para `harvest`). |
