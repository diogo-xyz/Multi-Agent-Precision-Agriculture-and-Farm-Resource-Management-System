# Fertilizer Agent (fertilizer_agent_column.py)

## Visão Geral
O `Fertilizer Agent` é um agente executor responsável por aplicar fertilizante em colunas inteiras do campo em resposta a um **Call For Proposal (CFP)** iniciado por um agente de monitoramento, como o `Soil Sensor Agent`.

## Funcionalidades Principais
1.  **Cálculo de ETA:** Calcula o **Estimated Time of Arrival (ETA)** para a zona de ação solicitada (uma coluna) com base na **distância de Manhattan** da sua posição atual, mais um tempo fixo para a execução da ação.
2.  **Proposta de Tarefa:** Responde a um `cfp_task` com uma mensagem `propose_task`, indicando o ETA, a perda de bateria estimada e os recursos disponíveis.
3.  **Gestão de Recursos:** Monitora o estoque de fertilizante e o nível de energia. Se estiverem abaixo de um limiar, envia um `cfp_recharge` para o `Logistics Agent`.
4.  **Movimentação (Novo):** Ao receber a aceitação da proposta, o agente **simula a movimentação** para a coluna alvo, atualizando sua posição interna (`self.row`, `self.col`). Esta movimentação é registrada no terminal para visibilidade.
5.  **Execução da Tarefa:** Aplica o fertilizante em **todos os blocos** da coluna alvo, conforme especificado no CFP.
6.  **Relatório de Conclusão:** Após a execução, envia uma mensagem `Done` ao agente solicitante, reportando os recursos e energia utilizados.

## Protocolo de Comunicação
O agente utiliza os seguintes performativos do protocolo de comunicação:

| Performative | Uso |
| :--- | :--- |
| `cfp_task` | Recebido do agente de monitoramento (e.g., `Soil Sensor Agent`). |
| `propose_task` | Enviado em resposta ao `cfp_task`. |
| `accept-proposal` | Recebido do agente de monitoramento para iniciar a execução. |
| `reject-proposal` | Recebido do agente de monitoramento quando a proposta não é selecionada. |
| `Done` | Enviado ao agente de monitoramento após a conclusão da tarefa. |
| `cfp_recharge` | Enviado ao `Logistics Agent` para solicitar reabastecimento de fertilizante ou energia. |

## Lógica de Movimentação
A lógica de movimentação é implementada no método `execute_task`. Antes de chamar a função de aplicação de fertilizante, o agente:
1.  Extrai a coluna alvo (`target_col`) da zona.
2.  Imprime uma mensagem no terminal indicando a movimentação de sua posição inicial para a coluna alvo.
3.  Atualiza seus atributos `self.row` e `self.col` para a nova posição.
4.  Imprime uma mensagem de chegada antes de iniciar a aplicação.

Isso garante que a mobilização do agente seja visível no terminal, conforme solicitado.
