import time
import json
import numpy as np
import random
import uuid
from typing import List, Dict, Any

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
    based on its position, manages its energy, and initiates the Contract Net Protocol
    for fertilization requests.
    """
    def __init__(self, field, row: int, col: int, agent_id: str, fertilizer_agents: List[str]):
        self.field = field
        self.agent_id = agent_id
        self.row = row  # The bottom-left corner of the 2x2 area
        self.col = col  # The bottom-left corner of the 2x2 area
        self.monitoring_threshold = 60
        self.energy = 100
        self.energy_recharge_threshold = 40
        self.energy_loss_range = (2, 4)
        
        # NOTE: fertilizer_agents is a list of all FertilizerAgent IDs for the Contract Net Protocol
        self.fertilizer_agents = fertilizer_agents 
        self.irrigation_agent_id = "IrrigationAgent"
        self.logistics_agent_id = "LogisticsAgent"
        
        self.rows = ROWS
        self.cols = COLS
        
        # Store proposals received during the negotiation phase
        self.proposals: Dict[str, Dict[str, Any]] = {}

    def monitor_and_act(self):
        """
        Performs energy check, monitors the 2x2 area, calculates mean conditions,
        and initiates the Contract Net Protocol for fertilization if needed.
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

        # 3. Check Nutrients and initiate Contract Net Protocol
        if mean_nutrients < self.monitoring_threshold:
            print(f"[{self.agent_id}] Mean Nutrients low ({mean_nutrients:.2f}). Initiating Contract Net Protocol for fertilization.")
            self._initiate_contract_net("fertilize_application")

        # 4. Check Moisture and request irrigation (Assuming simple request for IrrigationAgent for now)
        if mean_moisture < self.monitoring_threshold:
            print(f"[{self.agent_id}] Mean Moisture low ({mean_moisture:.2f}). Requesting irrigation for 2x2 area.")
            self._send_cfp_irrigation()

    def _initiate_contract_net(self, task_type: str):
        """
        Sends CFP to all FertilizerAgents, simulates proposal collection, and selects the best one.
        """
        cfp_id = f"cfp_{task_type}_{uuid.uuid4()}"
        self.proposals = {} # Clear previous proposals
        
        # 1. Send CFP to all Fertilizer Agents
        for agent_id in self.fertilizer_agents:
            self._send_cfp_task(agent_id, task_type, cfp_id)
            
        # 2. Simulate Proposal Collection (In a real system, this would be a waiting loop)
        # For simulation, we assume the proposals are collected immediately.
        # This part will be handled by the simulation script calling a mock receive_proposal method.
        
        # 3. Select Best Proposal (This is where the simulation script will call this method)
        # We will implement the selection logic in a separate method for clarity.
        
    def receive_proposal(self, proposal_message: Dict[str, Any]):
        """Simulates receiving a proposal from a FertilizerAgent."""
        cfp_id = proposal_message.get("cfp_id")
        sender_id = proposal_message.get("sender_id")
        
        # NOTE: We only store the proposal if it's a response to an active CFP (not fully implemented here)
        # For simulation, we just store it.
        self.proposals[sender_id] = proposal_message
        print(f"[{self.agent_id}] Received proposal from {sender_id} for CFP {cfp_id}. ETA: {proposal_message.get('eta_ticks')}")

    def select_and_respond(self, cfp_id: str):
        """
        Selects the best proposal based on ETA and sends Accept/Reject messages.
        """
        if not self.proposals:
            print(f"[{self.agent_id}] No proposals received for CFP {cfp_id}. Task failed.")
            return

        # Find the best proposal (lowest ETA)
        best_proposal = None
        min_eta = float('inf')
        
        # NOTE: If ETAs are equal, the first one found is chosen, fulfilling the requirement.
        for agent_id, proposal in self.proposals.items():
            eta = proposal.get("eta_ticks", float('inf'))
            if eta < min_eta:
                min_eta = eta
                best_proposal = proposal
        
        if best_proposal:
            winner_id = best_proposal["sender_id"]
            
            # 1. Send Accept to Winner
            self._send_proposal_response(winner_id, cfp_id, "accept")
            
            # 2. Send Reject to Losers
            for agent_id in self.proposals.keys():
                if agent_id != winner_id:
                    self._send_proposal_response(agent_id, cfp_id, "reject")
        
        # Clear proposals after selection
        self.proposals = {}

    def _send_proposal_response(self, receiver_id: str, cfp_id: str, decision: str):
        """Sends an accept-proposal or reject-proposal message."""
        # Conforming to Accept/Reject Proposal structure from protocolos.md
        message = {
            "sender_id": self.agent_id,
            "receiver_id": receiver_id,
            "cfp_id": cfp_id,
            "decision": decision,
        }
        
        performative = "accept-proposal" if decision == "accept" else "reject-proposal"
        print(f"[{self.agent_id}] Sending {performative} to {receiver_id}: \n{json.dumps(message, indent=4)}")


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
        excluding out-of-bounds blocks. (Unchanged from previous version)
        """
        # ... (implementation remains the same)
        area_coords = [
            (self.row, self.col),       # Bottom-Left (The block he is in)
            (self.row - 1, self.col),   # Top-Left (The block above)
            (self.row, self.col + 1),   # Bottom-Right (The block to the right)
            (self.row - 1, self.col + 1) # Top-Right (The upper right diagonal)
        ]
        
        nutrients_list = []
        moisture_list = []
        
        for r, c in area_coords:
            if 0 <= r < self.rows and 0 <= c < self.cols:
                soil_data = self.field.get_soil(r, c)
                if soil_data is not None:
                    nutrients_list.append(soil_data[1])
                    moisture_list.append(soil_data[2])
            else:
                print(f"[{self.agent_id}] Skipping out-of-bounds block: ({r}, {c})")

        if not nutrients_list:
            return 0.0, 0.0

        mean_nutrients = np.mean(nutrients_list)
        mean_moisture = np.mean(moisture_list)
        
        return mean_nutrients, mean_moisture

    def _send_cfp_task(self, receiver_id: str, task_type: str, cfp_id: str):
        """Sends a CFP to a single executor agent."""
        # Required amount is an estimate for the 2x2 area
        required_amount = 4.0 if task_type == "fertilize_application" else 400.0
        resource_type = "fertilizer" if task_type == "fertilize_application" else "water"
        resource_unit = "KG" if task_type == "fertilize_application" else "L"
        zone = [self.row, self.col]
        
        # Conforming to CFP (cfp_task) structure from protocolos.md
        cfp_message = {
            "sender_id": self.agent_id,
            "receiver_id": receiver_id,
            "cfp_id": cfp_id,
            "task_type": task_type,
            "seed_type": 0, 
            "zone": zone,
            "required_resources": [
                {"type": resource_type, "amount": required_amount, "unit": resource_unit}
            ],
            "priority": "High",
        }
        
        print(f"[{self.agent_id}] CFP to {receiver_id}: \n{json.dumps(cfp_message, indent=4)}")

    def _send_cfp_fertilize(self):
        """Placeholder for old fertilization request, now handled by _initiate_contract_net."""
        # This method is now obsolete but kept for compatibility with the monitor_and_act structure
        # The actual logic is in _initiate_contract_net
        pass

    def _send_cfp_irrigation(self):
        """Sends a simple CFP to the IrrigationAgent (assuming no Contract Net for irrigation yet)."""
        self._send_cfp_task(self.irrigation_agent_id, "irrigation_aplication", f"cfp_irrigation_{time.time()}")

    def _send_cfp_recharge(self):
        """Sends a CFP to the LogisticsAgent for energy recharge."""
        required_amount = 100 - self.energy # Requesting to top up to 100
        
        # Conforming to CFP (cfp_recharge) structure from protocolos.md
        cfp_message = {
            "sender_id": self.agent_id,
            "receiver_id": self.logistics_agent_id,
            "cfp_id": f"cfp_recharge_{time.time()}",
            "task_type": "battery", # Matches enum from protocols.md
            "required_resources": required_amount, # Matches required_resources field (amount)
            "seed_type": 0, # Not applicable for this task
            "priority": "Urgent", # Energy is critical
        }
        
        print(f"[{self.agent_id}] CFP to {self.logistics_agent_id} (Recharge): \n{json.dumps(cfp_message, indent=4)}")
