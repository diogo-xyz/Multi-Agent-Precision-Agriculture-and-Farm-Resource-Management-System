'''
Caso o soil agent peça fertilização numa coluna inteira, o fertilizer agent deve ser capaz de calcular o ETA
com base na distância Manhattan (número de blocos a percorrer) mais o tempo fixo de ação (5 ticks).
Além disso, ao executar a tarefa, o fertilizer agent deve aplicar o fertilizante em todos os blocos da coluna especificada.
Ao invés de aplicar fertilização numa área 2x2, ele deve aplicar em todos os blocos da coluna.
'''


import time
import json
import random
import math
from ..environment.field import Field # Assuming Field is available for apply_fertilize
from config import MAX_FERTILIZER_KG, FERTILIZER_RECHARGE_THRESHOLD_KG

# Placeholder for config variables if config.py is not available
try:
    from config import MAX_FERTILIZER_KG, FERTILIZER_RECHARGE_THRESHOLD_KG #Needs to be difined in config.py
except ImportError:
    MAX_FERTILIZER_KG = 500.0
    FERTILIZER_RECHARGE_THRESHOLD_KG = 50.0

class FertilizerAgent:
    """
    Receives fertilization requests (CFPs), manages fertilizer stock and energy,
    proposes tasks, executes fertilization, and communicates with the LogisticsAgent
    for resource and energy recharge.
    """
    # NOTE: Added row and col to the constructor to allow for ETA calculation.
    def __init__(self, field: Field, row: int, col: int, agent_id: str):
        self.field = field
        self.agent_id = agent_id
        self.row = row # Agent's current row position
        self.col = col # Agent's current col position
        self.energy = 100
        self.fertilizer_stock_kg = MAX_FERTILIZER_KG
        self.max_fertilizer_kg = MAX_FERTILIZER_KG
        self.fertilizer_recharge_threshold_kg = FERTILIZER_RECHARGE_THRESHOLD_KG
        self.energy_recharge_threshold = 30
        self.energy_loss_range = (4, 5)
        self.logistics_agent_id = "LogisticsAgent"
        self.pending_tasks = {} # To store CFPs awaiting acceptance

    def _calculate_eta(self, target_row: int, target_col: int) -> int:
        """
        Calculates the Estimated Time of Arrival (ETA) based on Manhattan distance
        plus a fixed time for the action (5 ticks).
        """
        # Manhattan distance (number of spaces away)
        distance = abs(self.row - target_row) + abs(self.col - target_col)
        
        # Time to perform the action
        ACTION_TIME = 5
        
        # ETA is travel time + action time
        eta = distance + ACTION_TIME
        
        return eta

    def receive_cfp(self, cfp_message: dict):
        """
        Processes a CFP message from a monitoring agent (e.g., SoilAgent).
        Responds with a propose_task message or a rejection (not implemented here).
        """
        sender_id = cfp_message.get("sender_id")
        cfp_id = cfp_message.get("cfp_id")
        task_type = cfp_message.get("task_type")
        required_resources = cfp_message.get("required_resources", [])
        zone = cfp_message.get("zone") # Get the target zone for ETA calculation
        
        if task_type != "fertilize_application":
            print(f"[{self.agent_id}] Received unknown task type: {task_type}. Ignoring.")
            return

        # 1. Check Energy
        if self.energy < self.energy_loss_range[0]:
            print(f"[{self.agent_id}] Energy too low ({self.energy}) to propose task {cfp_id}.")
            # In a real system, would send a rejection or an inform_busy
            return

        # 2. Check Fertilizer Stock
        required_fertilizer = next((res["amount"] for res in required_resources if res["type"] == "fertilizer"), 0)
        if self.fertilizer_stock_kg < required_fertilizer:
            print(f"[{self.agent_id}] Insufficient fertilizer stock ({self.fertilizer_stock_kg:.2f} KG) for task {cfp_id} (requires {required_fertilizer:.2f} KG).")
            # In a real system, would send a rejection or an inform_busy
            self._check_fertilizer_stock() # Trigger recharge request
            return

        # 3. Propose Task
        # NOTE: Pass the target zone to the proposal creation
        proposal = self._create_propose_task(cfp_id, sender_id, required_fertilizer, zone)
        print(f"[{self.agent_id}] Proposing task {cfp_id} to {sender_id}: \n{json.dumps(proposal, indent=4)}")
        
        # Store the CFP details while waiting for acceptance
        self.pending_tasks[cfp_id] = cfp_message
        
        # Energy loss for processing the CFP
        energy_lost = random.randint(*self.energy_loss_range)
        self.energy = max(0, self.energy - energy_lost)
        print(f"[{self.agent_id}] Energy lost for processing: {energy_lost}. Remaining energy: {self.energy}")

        # Check for recharges after processing the CFP
        self._check_energy()
        self._check_fertilizer_stock()

    def _create_propose_task(self, cfp_id: str, receiver_id: str, required_fertilizer: float, zone: list) -> dict:
        """Creates the propose_task message, conforming to protocolos.md."""
        # Estimate battery loss based on a fixed value for simplicity
        estimated_battery_loss = random.randint(*self.energy_loss_range)
        
        # Calculate ETA based on the agent's position and the target zone
        target_row, target_col = zone[0], zone[1]
        eta_ticks = self._calculate_eta(target_row, target_col)
        
        # Conforming to propose_task structure from protocolos.md
        return {
            "sender_id": self.agent_id,
            "receiver_id": receiver_id,
            "cfp_id": cfp_id,
            "eta_ticks": eta_ticks, # Now calculated based on distance
            "battery_lost": estimated_battery_loss,
            "available_resources": [
                {"type": "fertilizer", "amount": self.fertilizer_stock_kg, "unit": "KG"}
            ],
        }

    def execute_task(self, cfp_id: str):
        """
        Simulates the execution of the accepted task and reports completion.
        In a real system, this would be triggered by an 'accept-proposal' message.
        """
        if cfp_id not in self.pending_tasks:
            print(f"[{self.agent_id}] Error: Task {cfp_id} not found in pending list.")
            return

        cfp_message = self.pending_tasks.pop(cfp_id)
        zone = cfp_message.get("zone")
        required_resources = cfp_message.get("required_resources", [])
        required_fertilizer = next((res["amount"] for res in required_resources if res["type"] == "fertilizer"), 0)
        
        # 1. Deduct Resources and Energy
        # Energy loss for execution
        energy_lost = random.randint(*self.energy_loss_range)
        self.energy = max(0, self.energy - energy_lost)
        self.fertilizer_stock_kg -= required_fertilizer
        
        # 2. Move to Target Zone (Simulated)
        target_row, target_col = zone[0], zone[1]
        
        print(f"[{self.agent_id}] Moving from ({self.row}, {self.col}) to target column {target_col}...")
        
        # Simulate movement: update agent's position to the target column (e.g., row 0 of the column)
        # The time taken for movement is already accounted for in the ETA calculation.
        self.row = target_row
        self.col = target_col
        
        print(f"[{self.agent_id}] Arrived at ({self.row}, {self.col}). Starting fertilization.")
        
        # 3. Execute Field Action (Simulated)
        # The zone is now [0, col] for the entire column
        # start_row, col_to_fertilize = zone[0], zone[1] # Already extracted above
        col_to_fertilize = target_col
        
        # Determine the number of blocks in the column (assuming ROWS is available)
        try:
            from config import ROWS
        except ImportError:
            ROWS = 10 # Fallback
            
        num_blocks = ROWS
        fertilizer_per_block = required_fertilizer / num_blocks
        
        executed_blocks = 0
        for row in range(num_blocks):
            try:
                self.field.apply_fertilize(row, col_to_fertilize, fertilizer_per_block)
                executed_blocks += 1
            except AttributeError:
                # Mock field might not have apply_fertilize, so we just print
                print(f"[{self.agent_id}] Executing apply_fertilize at ({row}, {col_to_fertilize}) with {fertilizer_per_block:.2f} KG.")
                executed_blocks += 1
            except IndexError:
                # This should not happen if ROWS is correct, but kept for safety
                pass
        
        print(f"[{self.agent_id}] Task {cfp_id} executed. {executed_blocks} blocks fertilized in column {col_to_fertilize}.")

        # 3. Report Completion
        # 4. Report Completion
        # The time taken is the ETA calculated during the proposal phase, which includes travel and action time.
        # For the Done message, we can use the time_taken from the original ETA calculation.
        # Since the agent is now at the target location, the distance part of ETA is 0, so we use the action time.
        ACTION_TIME = 5 # Fixed action time from _calculate_eta
        time_taken = ACTION_TIME
        
        done_message = self._create_done_message(cfp_id, cfp_message["sender_id"], energy_lost, required_fertilizer, time_taken)
        print(f"[{self.agent_id}] Reporting 'Done' to {cfp_message['sender_id']}: \n{json.dumps(done_message, indent=4)}")
        
        # Check for recharges after execution
        self._check_energy()
        self._check_fertilizer_stock()

    def _create_done_message(self, cfp_id: str, receiver_id: str, energy_used: int, fertilizer_used: float, time_taken: int) -> dict:
        """Creates the Done message, conforming to protocolos.md."""
        # Conforming to Done structure from protocolos.md
        return {
            "sender_id": self.agent_id,
            "receiver_id": receiver_id,
            "cfp_id": cfp_id,
            "status": "done",
            "details": {
                "fertilizer_used": fertilizer_used,
                "energy_used": energy_used,
                "time_taken": time_taken # Now calculated based on distance
            }
        }

    def _check_energy(self):
        """Requests energy recharge if below threshold."""
        if self.energy <= self.energy_recharge_threshold:
            print(f"[{self.agent_id}] Energy low ({self.energy}). Requesting recharge.")
            self._send_cfp_recharge("battery")

    def _check_fertilizer_stock(self):
        """Requests fertilizer recharge if below threshold."""
        if self.fertilizer_stock_kg <= self.fertilizer_recharge_threshold_kg:
            print(f"[{self.agent_id}] Fertilizer stock low ({self.fertilizer_stock_kg:.2f} KG). Requesting recharge.")
            self._send_cfp_recharge("fertilizer")

    def _send_cfp_recharge(self, resource_type: str):
        """Sends a CFP to the LogisticsAgent for a given resource, conforming to cfp_recharge."""
        if resource_type == "battery":
            required_amount = 100 - self.energy
            priority = "Urgent"
        elif resource_type == "fertilizer":
            required_amount = self.max_fertilizer_kg - self.fertilizer_stock_kg
            priority = "High"
        else:
            return

        # Conforming to cfp_recharge structure from protocolos.md
        cfp_message = {
            "sender_id": self.agent_id,
            "receiver_id": self.logistics_agent_id,
            "cfp_id": f"cfp_recharge_{resource_type}_{time.time()}",
            "task_type": resource_type, # Matches enum from protocols.md
            "required_resources": required_amount, # Matches required_resources field (amount)
            "seed_type": 0, # Not applicable for this task
            "priority": priority,
        }
        
        print(f"[{self.agent_id}] CFP to {self.logistics_agent_id} ({resource_type.capitalize()} Recharge): \n{json.dumps(cfp_message, indent=4)}")

    def receive_proposal_response(self, response_message: dict):
        """
        Handles the accept-proposal or reject-proposal message from the SoilAgent.
        """
        cfp_id = response_message.get("cfp_id")
        decision = response_message.get("decision")
        
        if decision == "accept":
            print(f"[{self.agent_id}] Received ACCEPT for CFP {cfp_id}. Preparing to execute task.")
            # In a real system, this would trigger the task execution logic.
            # For simulation, we'll just log it.
            pass
        elif decision == "reject":
            if cfp_id in self.pending_tasks:
                self.pending_tasks.pop(cfp_id)
                print(f"[{self.agent_id}] Received REJECT for CFP {cfp_id}. Task removed from pending list.")
            else:
                print(f"[{self.agent_id}] Received REJECT for unknown CFP {cfp_id}.")
        else:
            print(f"[{self.agent_id}] Received unknown proposal response: {decision}.")
