# Multi Agent Precision Agriculture and Farm Resource Management System

## Descrição

Sistema multi-agente desenvolvido para gestão automatizada de operações agrícolas, incluindo irrigação, fertilização, colheita, logística e monitorização de condições ambientais.

## Estrutura do Projeto
```
TB_Sistemas/
├── main.py                             # Ponto de entrada principal
├── config.py                           # Configurações gerais
├── config_agents.py                    # Configurações dos agentes
├── environment_agent.py                # Agente de ambiente
├── human_agent.py                      # Interface com utilizador humano
├── requirements.txt                    # Dependências do projeto
├── server.db                           # Base de dados SQLite
├── agentes.log                         # Logs do sistema
├── Agetnes_Diagrama.drawio.html        # Diagrama de interações entre agentes
│
├── Docs/                      # Módulo de com a documentação em docstrings feita pela biblioteca pdoc
├── agents/                    # Módulo de agentes
│   ├── drone_agent.py         # Agente drone
│   ├── fertilizer_agent.py    # Agente de fertilização
│   ├── harvester_agent.py     # Agente de colheita
│   ├── irrigation_agent.py    # Agente de irrigação
│   ├── logistics_agent.py     # Agente de logística
│   ├── soil_sensor_agent.py   # Agente sensor de solo
│   ├── storage_agent.py       # Agente de armazenamento
│   └── message.py             # Sistema de mensagens
│
├── environment/              # Módulo de ambiente
│   ├── crop.py               # Gestão de culturas
│   ├── field.py              # Gestão de campos
│   ├── moisture.py           # Monitorização de humidade
│   ├── nutrients.py          # Gestão de nutrientes
│   └── temperature.py        # Monitorização de temperatura
│
└── events/                  # Módulo de eventos
    ├── pest_event.py        # Eventos de pragas
    └── rain_event.py        # Eventos de chuva
```

## Requisitos do Sistema

- Python 3.12.12
- Anaconda ou Miniconda

##  Setup e Instalação

### 1. Criar Ambiente Conda

Crie um novo ambiente conda com a versão específica do Python:
```bash
conda create -n nome_do_projeto python=3.12.12
```

### 2. Ativar o Ambiente
```bash
conda activate nome_do_projeto
```

### 3. Instalar Dependências

Instale todos os pacotes necessários a partir do ficheiro `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 4. Executar o Projeto

Execute num terminal o seguinte comando:
```bash
spade run
```

Execute o ficheiro principal noutro terminal:
```bash
python main.py
```

### 5. Verificar Instalação

Para verificar se o ambiente está configurado corretamente:
```bash
python --version  # Deve mostrar Python 3.12.12
pip list          # Lista todos os pacotes instalados
```

##  Importante

O sistema requer **dois terminais** em execução simultânea:
1. **Terminal 1**: `spade run` (servidor SPADE)
2. **Terminal 2**: `python main.py` (aplicação principal)

Certifique-se de que ambos os terminais estão com o ambiente conda ativado.

## Agentes do Sistema

### Agentes Operacionais
- **Drone Agent**: Monitorização aérea e recolha de dados
- **Fertilizer Agent**: Gestão de fertilização
- **Harvester Agent**: Controlo de colheita
- **Irrigation Agent**: Sistema de irrigação automatizada
- **Logistics Agent**: Coordenação logística
- **Soil Sensor Agent**: Sensores de solo
- **Storage Agent**: Gestão de armazenamento

### Agentes de Controlo
- **Environment Agent**: Monitorização ambiental
- **Human Agent**: Interface com operador humano

##  Componentes do Ambiente

- **Crop**: Gestão e estado das culturas
- **Field**: Representação e gestão dos campos
- **Moisture**: Monitorização de humidade do solo
- **Nutrients**: Gestão de nutrientes 
- **Temperature**: Controlo de temperatura

##  Eventos do Sistema

- **Pest Event**: Gestão de eventos de pragas
- **Rain Event**: Gestão de eventos meteorológicos
- **Drought Event**: Gestão de enventos de seca

##  Documentação Adicional

- `protocolos.md` - Protocolos de comunicação entre agentes
- `protocolos_environment.md` - Protocolos ambientais

## Comandos Úteis

### Desativar o ambiente
```bash
conda deactivate
```

### Listar ambientes conda
```bash
conda env list
```

### Remover o ambiente
```bash
conda env remove -n nome_do_projeto
```

### Verificar a versão do Python
```bash
python --version
```

## Base de Dados

O sistema utiliza SQLite (`server.db`) para persistência de dados. A base de dados é criada automaticamente na primeira execução.


### Verificar Instalação

Para verificar se o ambiente está configurado corretamente:
```bash
python --version  # Deve mostrar Python 3.12.12
pip list          # Lista todos os pacotes instalados
```

## Configuração

- `config.py`: Configurações gerais do sistema
- `config_agents.py`: Configurações específicas de cada agente

## Notas

- Certifique-se de que está sempre com o ambiente conda ativado antes de executar o projeto
- Mantenha o `requirements.txt` atualizado quando adicionar novas dependências
- Consulte os ficheiros de protocolos para entender a comunicação entre agentes
