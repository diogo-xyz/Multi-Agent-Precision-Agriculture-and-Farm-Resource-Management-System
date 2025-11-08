# Soil Sensor Agent (soil_sensor_agent_column.py)

## Visão Geral
O `Soil Sensor Agent` é responsável por monitorar as condições do solo (nutrientes e umidade) em uma coluna específica do campo. Ele atua como um agente de monitoramento, utilizando o protocolo **Contract Net Protocol (CNP)** para solicitar a intervenção de agentes executores (como o `Fertilizer Agent` ou o `Irrigation Agent`) quando as condições do solo caem abaixo de um limiar aceitável.

## Funcionalidades Principais
1.  **Monitoramento por Coluna:** Calcula a média das condições de nutrientes e umidade para todos os blocos em uma coluna designada.
2.  **Detecção de Necessidade:** Compara as médias calculadas com os limiares ideais.
3.  **Iniciação de CFP:** Se uma necessidade for detectada (por exemplo, baixo nutriente), o agente inicia um **Call For Proposal (CFP)** para a tarefa de aplicação de fertilizante ou irrigação, especificando a coluna inteira como a zona de ação.
4.  **Seleção de Proposta:** Recebe propostas dos agentes executores, seleciona a melhor (geralmente a com menor ETA) e envia uma mensagem de `accept-proposal`.
5.  **Confirmação de Conclusão:** Recebe a mensagem `Done` do agente executor após a conclusão da tarefa.

## Protocolo de Comunicação
O agente utiliza os seguintes performativos do protocolo de comunicação:

| Performative | Uso |
| :--- | :--- |
| `cfp_task` | Enviado para solicitar uma tarefa (e.g., `fertilize_application`) para a coluna monitorada. |
| `propose_task` | Recebido dos agentes executores em resposta ao `cfp_task`. |
| `accept-proposal` | Enviado para o agente executor com a melhor proposta. |
| `reject-proposal` | Enviado para os agentes executores com propostas não selecionadas. |
| `Done` | Recebido do agente executor após a conclusão da tarefa. |

## Estrutura da Zona
A zona de ação no `cfp_task` é definida como `[0, self.col]`, indicando que a tarefa se aplica a toda a coluna `self.col`, começando da linha 0.

## Dependências
- `config.py`: Para constantes como `ROWS` e limiares de nutrientes.
- `protocolos.md`: Para a estrutura das mensagens de comunicação.
- `Field`: Para interagir com o estado atual do campo (simulação).
