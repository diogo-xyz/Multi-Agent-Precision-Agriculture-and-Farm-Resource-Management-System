import time
import json
import random
from ..environment.field.py import Field # Assuming Field is available for apply_fertilize
from ..config import MAX_FERTILIZER_KG, FERTILIZER_RECHARGE_THRESHOLD_KG

# Placeholder for config variables if config.py is not available
try:
    from config import MAX_FERTILIZER_KG, FERTILIZER_RECHARGE_THRESHOLD_KG
except ImportError:
    MAX_FERTILIZER_KG = 500.0
    FERTILIZER_RECHARGE_THRESHOLD_KG = 50.0

class FertilizerAgent:
    """
    Receives fertilization requests (CFPs), manages fertilizer stock and energy,
    proposes tasks, executes fertilization, and communicates with the LogisticsAgent
    for resource and energy recharge.
    """
    def __init__(self, field: Field, agent_id: str = "FertilizerAgent"):
        self.field = field
        self.agent_id = agent_id
        self.energy = 100
        self.fertilizer_stock_kg = MAX_FERTILIZER_KG
        self.max_fertilizer_kg = MAX_FERTILIZER_KG
        self.fertilizer_recharge_threshold_kg = FERTILIZER_RECHARGE_THRESHOLD_KG
        self.energy_recharge_threshold = 30
        self.energy_loss_range = (4, 5)
        self.logistics_agent_id = "LogisticsAgent"
        self.pending_tasks = {} # To store CFPs awaiting acceptance

    def receive_cfp(self, cfp_message: dict):
        """
        Processes a CFP message from a monitoring agent (e.g., SoilAgent).
        Responds with a propose_task message or a rejection (not implemented here).
        """
        sender_id = cfp_message.get("sender_id")
        cfp_id = cfp_message.get("cfp_id")
        task_type = cfp_message.get("task_type")
        required_resources = cfp_message.get("required_resources", [])
        
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
        proposal = self._create_propose_task(cfp_id, sender_id, required_fertilizer)
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

    def _create_propose_task(self, cfp_id: str, receiver_id: str, required_fertilizer: float) -> dict:
        """Creates the propose_task message."""
        # Estimate battery loss based on a fixed value for simplicity
        estimated_battery_loss = random.randint(*self.energy_loss_range)
        
        # Estimate ETA (e.g., 5 ticks for travel and execution)
        eta_ticks = 5 
        
        return {
            "sender_id": self.agent_id,
            "receiver_id": receiver_id,
            "cfp_id": cfp_id,
            "eta_ticks": eta_ticks,
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
        # Energy loss is already calculated in _create_propose_task and stored in the proposal,
        # but for simplicity and to match the user's request of losing energy when processing,
        # we will use a new random loss here.
        energy_lost = random.randint(*self.energy_loss_range)
        self.energy = max(0, self.energy - energy_lost)
        self.fertilizer_stock_kg -= required_fertilizer
        
        # 2. Execute Field Action (Simulated)
        # The SoilAgent sends the bottom-left corner of the 2x2 area.
        # For simplicity in this mock, we'll assume the executor agent handles the 2x2 area
        # by calling apply_fertilize for each of the 4 blocks.
        # Since field.py only has apply_fertilize(row, col, amount), we'll call it 4 times.
        
        r, c = zone[0], zone[1]
        fertilizer_per_block = required_fertilizer / 4.0
        
        area_coords = [
            (r, c),       # Bottom-Left
            (r - 1, c),   # Top-Left
            (r, c + 1),   # Bottom-Right
            (r - 1, c + 1) # Top-Right
        ]
        
        executed_blocks = 0
        for row, col in area_coords:
            # Check if the block is within the field boundaries (assuming Field has ROWS/COLS)
            # In a real system, the Field object would handle boundary checks.
            # For this mock, we'll assume the Field.apply_fertilize handles it or we'll mock it.
            try:
                self.field.apply_fertilize(row, col, fertilizer_per_block)
                executed_blocks += 1
            except AttributeError:
                # Mock field might not have apply_fertilize, so we just print
                print(f"[{self.agent_id}] Executing apply_fertilize at ({row}, {col}) with {fertilizer_per_block:.2f} KG.")
                executed_blocks += 1
            except IndexError:
                # Handle out-of-bounds if the mock field is more realistic
                pass
        
        print(f"[{self.agent_id}] Task {cfp_id} executed. {executed_blocks} blocks fertilized.")

        # 3. Report Completion
        done_message = self._create_done_message(cfp_id, cfp_message["sender_id"], energy_lost, required_fertilizer)
        print(f"[{self.agent_id}] Reporting 'Done' to {cfp_message['sender_id']}: \n{json.dumps(done_message, indent=4)}")
        
        # Check for recharges after execution
        self._check_energy()
        self._check_fertilizer_stock()

    def _create_done_message(self, cfp_id: str, receiver_id: str, energy_used: int, fertilizer_used: float) -> dict:
        """Creates the Done message."""
        return {
            "sender_id": self.agent_id,
            "receiver_id": receiver_id,
            "cfp_id": cfp_id,
            "status": "done",
            "details": {
                "energy_used": energy_used,
                "fertilizer_used": fertilizer_used,
                "time_taken": 5 # Assuming 5 ticks from proposal
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
        """Sends a CFP to the LogisticsAgent for a given resource."""
        if resource_type == "battery":
            required_amount = 100 - self.energy
            priority = "Urgent"
        elif resource_type == "fertilizer":
            required_amount = self.max_fertilizer_kg - self.fertilizer_stock_kg
            priority = "High"
        else:
            return

        cfp_message = {
            "sender_id": self.agent_id,
            "receiver_id": self.logistics_agent_id,
            "cfp_id": f"cfp_recharge_{resource_type}_{time.time()}",
            "task_type": resource_type,
            "required_resources": required_amount,
            "seed_type": 0,
            "priority": priority,
        }
        
        print(f"[{self.agent_id}] CFP to {self.logistics_agent_id} ({resource_type.capitalize()} Recharge): \n{json.dumps(cfp_message, indent=4)}")

    def recharge_complete(self, resource_type: str, amount: float):
        """Simulates the completion of a recharge task by the LogisticsAgent."""
        if resource_type == "battery":
            self.energy = min(100, self.energy + amount)
            print(f"[{self.agent_id}] Battery recharged by {amount}. Energy is now {self.energy}.")
        elif resource_type == "fertilizer":
            self.fertilizer_stock_kg = min(self.max_fertilizer_kg, self.fertilizer_stock_kg + amount)
            print(f"[{self.agent_id}] Fertilizer recharged by {amount:.2f} KG. Stock is now {self.fertilizer_stock_kg:.2f} KG.")
        
# --- Example Usage (for testing purposes) ---
# This part is for demonstration and would typically be run in the main simulation loop.
# try:
#     # Assuming Field and config are correctly set up
#     # field_instance = Field()
#     # fertilizer_agent = FertilizerAgent(field_instance)
#     # fertilizer_agent.receive_cfp(...)
#     pass
# except NameError:
#     print("Note: Example usage is commented out as dependencies (Field, config) are not fully available in this script's context.")
#     pass
