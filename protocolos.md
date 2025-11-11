# 1.Inform Crop 

O Drone envia um inform ao agente Logistic a dizer se é preciso colher ou plantar

**Performative:** `inform_crop` 

```json
{   
    "sender_id",
    "receiver_id",

    "inform_id": "inform_crop_time.time()",
    "zone": [1,1],
    "crop_type": crop_type,
    "state": "0 -> not planted      1 -> Ready for harvasting",
    "checked_at": "time.time()"
}
```

**Performative:** `inform_harvest`

```json
{   
    "sender_id",
    "receiver_id",

    "inform_id": "inform_harvest_time.time()",
    "amount_type":[
        {"seed_type": 0 ,"amount", 1 (KG)},
        {"seed_type": 1 ,"amount", 1 (KG)},
        {"seed_type": 2 ,"amount", 1 (KG)},
        {"seed_type": 3 ,"amount", 1 (KG)},
        {"seed_type": 4 ,"amount", 1 (KG)},
        {"seed_type": 5 ,"amount", 1 (KG)},
    ],
    "checked_at": "time.time()"
}
```

**Performative:** `inform_received`

```json
{   
    "sender_id",
    "receiver_id",

    "inform_id": "inform_received_time.time()",
    "details" : [{"seed_type": 0, "amount": 1}
                ... 
    ],
    "checked_at": "time.time()"
}
```

# 2. CFP (Call For Proposal)

Usado por agentes de monitorização (Drone, SoilSensor) e pelo agente Logistic para solicitar a execução de uma tarefa 

**Performative:** `cfp_task`


``` json
{
    "sender_id",
    "receiver_id",

    "cfp_id": "cfp_task_time.time()",
    "task_type": "irrigation_aplication", // enum: irrigation_application | fertilize_application |harvest_application | plant_application
    "seed_type": 1, // int que identifica o tipo de seed
    "zone": [1,1],
    "required_resources": [
        {"type":"water", "amount":120 (L)},
        {"type":"fertilizer", "amount": 1.5 (KG)}
        {"type":"seed", "amount":5 (g)}
        {"type":"storage", "amount": 5 (KG)}],
    "priority": "High", // ou Medium, Low, Urgent
}
``` 

Usado pelos agentes Drone, SoilSensor, Fertelizer, Irrigation e Harvester para solicitar reabastecimento

**Performative:** `cfp_recharge`


``` json
{
    "sender_id",
    "receiver_id",

    "cfp_id": "cfp_recharge_time.time()",
    "task_type": "water", // enum: battery | fuel | seeds | pesticides | fertilizer | water
    "required_resources": 10, //enum: 80 mA  | 20 L | 10 g  |   1 KG     |   1 Kg     | 10 L
    "position": (1,1), // tupla
    "seed_type": 1, // int que identifica o tipo de seed
    "priority": "High", // ou Medium, Low, Urgent
}
```


# 3. Propose 

Usado por agentes executores (Irrigation, Harvester, Fertilizer) para responder a um CFP

**Performative:** `propose_task`


```json
{
    "sender_id",
    "receiver_id",

    "cfp_id": "cfp_propose_task_time.time()",
    "eta_ticks": 6 (Estimated Time of Arrival),
    "battery_lost": 10 ,  //  fuel_cost
}
```


Usado pelo Agente Logistic para responder a um CFP de reabastecimento

**Performative:** `propose_recharge`


```json
{
    "sender_id",
    "receiver_id",

    "cfp_id": "cfp_propose_recharge_time.time()",
    "eta_ticks": 6 (Estimated Time of Arrival),
    "resources": 10,
    "priority": "High", // ou Medium, Low, Urgent
}
```


# 3. Accept / Reject Proposal

Usado pelos agentes para aceitar ou rejeitar uma proposta.

**Performative:** `accept-proposal`


```json
{
    "sender_id",
    "receiver_id",


    "cfp_id": "cfp_accept_time.time()",
    "decision": "accept",  
}
```

**Performative:** `reject-proposal`


```json
{
    "sender_id",
    "receiver_id",

    "cfp_id": "cfp_reject_time.time()",
    "decision": "reject",
}
```

# 4. Done / Failure

Usado por agentes executores para informar o sobre a conclusão ou falha da tarefa.

**Performative:** `Done`


```json
{
    "sender_id",
    "receiver_id",

    "cfp_id": "cfp_done_time.time()",
    "status": "done",
    "seed_type": 0,
    "details": {"amount_delivered": 50}
}
```

**Performative:** `failure`


```json
{
    "sender_id",
    "receiver_id",

    "cfp_id": "cfp_failure_time.time()",
    "status": "failed",
}
```
