import time
import json
import numpy as np
import random
# Placeholder for ROWS and COLS if config.py is not directly importable in this context
try:
    from config import ROWS, COLS
except ImportError:
    print("Warning: Could not import ROWS and COLS from config. Using placeholders.")
    ROWS = 10  # Placeholder value
    COLS = 10  # Placeholder value


class SoilAgent:
    """
    Monitors soil conditions (nutrients and moisture) in a 2x2 area
    based on its position, manages its energy, and requests
    fertilization, irrigation, or energy recharge when needed.
    """
    def __init__(self, field, row: int, col: int, agent_id: str):
        self.field = field
        self.agent_id = agent_id
        self.row = row  # The bottom-left corner of the 2x2 area
        self.col = col  # The bottom-left corner of the 2x2 area
        self.monitoring_threshold = 60
        self.energy = 100
        self.energy_recharge_threshold = 40
        self.energy_loss_range = (2, 4)
        
        self.fertilizer_agent_id = "FertilizerAgent"
        self.irrigation_agent_id = "IrrigationAgent"
        self.logistics_agent_id = "LogisticsAgent"
        
        self.rows = ROWS
        self.cols = COLS

    def monitor_and_act(self):
        """
        Performs energy check, monitors the 2x2 area, calculates mean conditions,
        and sends CFP messages for fertilization or irrigation if needed.
        """
        print(f"[{self.agent_id}] Starting monitoring at zone ({self.row}, {self.col}). Energy: {self.energy}")
        
        # 1. Energy Check and Loss
        self._check_energy()
        if self.energy <= 0:
            print(f"[{self.agent_id}] Out of energy. Cannot monitor.")
            return

        # 2. Monitor 2x2 area and calculate mean
        mean_nutrients, mean_moisture = self._get_mean_soil_conditions()
        
        print(f"[{self.agent_id}] Mean Nutrients: {mean_nutrients:.2f}, Mean Moisture: {mean_moisture:.2f}")

        # 3. Check Nutrients and request fertilization
        if mean_nutrients < self.monitoring_threshold:
            print(f"[{self.agent_id}] Mean Nutrients low ({mean_nutrients:.2f}). Requesting fertilization for 2x2 area.")
            self._send_cfp_fertilize()

        # 4. Check Moisture and request irrigation
        if mean_moisture < self.monitoring_threshold:
            print(f"[{self.agent_id}] Mean Moisture low ({mean_moisture:.2f}). Requesting irrigation for 2x2 area.")
            self._send_cfp_irrigation()

    def _check_energy(self):
        """Manages energy loss and requests recharge if below threshold."""
        # Energy Loss
        loss = random.randint(*self.energy_loss_range)
        self.energy = max(0, self.energy - loss)
        print(f"[{self.agent_id}] Energy lost: {loss}. Remaining energy: {self.energy}")

        # Energy Recharge Request
        if self.energy <= self.energy_recharge_threshold and self.energy > 0:
            print(f"[{self.agent_id}] Energy low ({self.energy}). Requesting recharge.")
            self._send_cfp_recharge()

    def _get_mean_soil_conditions(self):
        """
        Calculates the mean nutrients and moisture for the 2x2 area,
        excluding out-of-bounds blocks.
        """
        # The 2x2 area is defined by the bottom-left corner (self.row, self.col)
        # and includes: (r, c), (r-1, c), (r, c+1), (r-1, c+1)
        area_coords = [
            (self.row, self.col),       # Bottom-Left (The block he is in)
            (self.row - 1, self.col),   # Top-Left (The block above)
            (self.row, self.col + 1),   # Bottom-Right (The block to the right)
            (self.row - 1, self.col + 1) # Top-Right (The upper right diagonal)
        ]
        
        nutrients_list = []
        moisture_list = []
        
        for r, c in area_coords:
            # Check if the coordinates are within the field boundaries
            if 0 <= r < self.rows and 0 <= c < self.cols:
                # get_soil returns [temperature, nutrients, moisture]
                soil_data = self.field.get_soil(r, c)
                # The mock field returns None if out of bounds, so we check for that too
                if soil_data is not None:
                    nutrients_list.append(soil_data[1])
                    moisture_list.append(soil_data[2])
            else:
                print(f"[{self.agent_id}] Skipping out-of-bounds block: ({r}, {c})")

        if not nutrients_list:
            return 0.0, 0.0 # Return 0 if no valid blocks were found

        mean_nutrients = np.mean(nutrients_list)
        mean_moisture = np.mean(moisture_list)
        
        return mean_nutrients, mean_moisture

    def _send_cfp_fertilize(self):
        """Sends a CFP to the FertilizerAgent for fertilization of the 2x2 area."""
        required_amount = 4.0 # Example: 1 KG per block * 4 blocks = 4 KG
        zone = [self.row, self.col]
        
        cfp_message = {
            "sender_id": self.agent_id,
            "receiver_id": self.fertilizer_agent_id,
            "cfp_id": f"cfp_fertilize_{time.time()}",
            "task_type": "fertilize_application",
            "seed_type": 0, 
            "zone": zone,
            "area_size": "2x2", # Explicitly state the area size
            "required_resources": [
                {"type": "fertilizer", "amount": required_amount, "unit": "KG"}
            ],
            "priority": "High",
        }
        
        print(f"[{self.agent_id}] CFP to {self.fertilizer_agent_id}: \n{json.dumps(cfp_message, indent=4)}")

    def _send_cfp_irrigation(self):
        """Sends a CFP to the IrrigationAgent for irrigation of the 2x2 area."""
        required_amount = 400.0 # Example: 100 L per block * 4 blocks = 400 L
        zone = [self.row, self.col]
        
        cfp_message = {
            "sender_id": self.agent_id,
            "receiver_id": self.irrigation_agent_id,
            "cfp_id": f"cfp_irrigation_{time.time()}",
            "task_type": "irrigation_aplication",
            "seed_type": 0, 
            "zone": zone,
            "area_size": "2x2", # Explicitly state the area size
            "required_resources": [
                {"type": "water", "amount": required_amount, "unit": "L"}
            ],
            "priority": "High",
        }
        
        print(f"[{self.agent_id}] CFP to {self.irrigation_agent_id}: \n{json.dumps(cfp_message, indent=4)}")

    def _send_cfp_recharge(self):
        """Sends a CFP to the LogisticsAgent for energy recharge."""
        required_amount = 100 - self.energy # Requesting to top up to 100
        
        cfp_message = {
            "sender_id": self.agent_id,
            "receiver_id": self.logistics_agent_id,
            "cfp_id": f"cfp_recharge_{time.time()}",
            "task_type": "battery", 
            "required_resources": required_amount, 
            "seed_type": 0, 
            "priority": "Urgent", 
        }
        
        print(f"[{self.agent_id}] CFP to {self.logistics_agent_id} (Recharge): \n{json.dumps(cfp_message, indent=4)}")
