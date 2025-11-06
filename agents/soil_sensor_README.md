# Soil Agent

The `SoilAgent` is responsible for monitoring the soil conditions (nutrients and moisture) in a 2x2 area, managing its own energy, and initiating requests for corrective actions when necessary.

## Functionality

1.  **Initialization:** The agent is initialized with its position (`row`, `col`), which serves as the **bottom-left corner** of its 2x2 monitoring area.
2.  **Energy Management:**
    *   Starts with **100** energy.
    *   Loses a random amount of energy between **2 and 4** with every monitoring cycle.
    *   If energy drops to **40 or below**, it sends a **CFP** to the `LogisticsAgent` for recharge.
3.  **2x2 Area Monitoring:**
    *   The agent monitors a 2x2 block area defined by the coordinates:
        *   `(row, col)` (Bottom-Left - The block he is in)
        *   `(row - 1, col)` (Top-Left - The block above)
        *   `(row, col + 1)` (Bottom-Right - The block to the right)
        *   `(row - 1, col + 1)` (Top-Right - The upper right diagonal)
    *   It uses `field.get_soil(r, c)` for each block.
    *   **Out-of-bounds** blocks are ignored and do not contribute to the mean calculation.
4.  **Threshold Check:** It calculates the **mean** of the nutrient and moisture levels across the valid blocks in its 2x2 area. If the mean drops below **60**, it triggers an action for the entire 2x2 area.
5.  **Communication:**
    *   If **Mean Nutrients** are below the threshold, it sends a **Call For Proposal (CFP)** with the `task_type: "fertilize_application"` to the `FertilizerAgent`.
    *   If **Mean Moisture** is below the threshold, it sends a **Call For Proposal (CFP)** with the `task_type: "irrigation_aplication"` to the `IrrigationAgent`.

## Communication Protocol (CFP)

The agent uses the `cfp_task` and `cfp_recharge` performatives as defined in `protocolos.md`.

### CFP for Fertilization (2x2 Area)

```json
{
    "sender_id": "SoilAgent_r_c",
    "receiver_id": "FertilizerAgent",
    "cfp_id": "cfp_fertilize_time.time()",
    "task_type": "fertilize_application",
    "seed_type": 0,
    "zone": [r, c],
    "area_size": "2x2",
    "required_resources": [
        {"type": "fertilizer", "amount": 4.0, "unit": "KG"}
    ],
    "priority": "High"
}
```

### CFP for Irrigation (2x2 Area)

```json
{
    "sender_id": "SoilAgent_r_c",
    "receiver_id": "IrrigationAgent",
    "cfp_id": "cfp_irrigation_time.time()",
    "task_type": "irrigation_aplication",
    "seed_type": 0,
    "zone": [r, c],
    "area_size": "2x2",
    "required_resources": [
        {"type": "water", "amount": 400.0, "unit": "L"}
    ],
    "priority": "High"
}
```

### CFP for Energy Recharge

```json
{
    "sender_id": "SoilAgent_r_c",
    "receiver_id": "LogisticsAgent",
    "cfp_id": "cfp_recharge_time.time()",
    "task_type": "battery",
    "required_resources": 60, // Example: amount needed to reach 100
    "seed_type": 0,
    "priority": "Urgent"
}
```
