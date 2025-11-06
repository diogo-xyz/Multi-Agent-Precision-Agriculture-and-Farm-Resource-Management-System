import sys
import os
import time
import numpy as np
import random
import io
from contextlib import redirect_stdout

# Mock the config module since it might not be available in the test environment
class MockConfig:
    ROWS = 10
    COLS = 10

# Patch the import of config to use the mock
# This is a common pattern when testing modules that rely on a config file
try:
    from config import ROWS, COLS
except ImportError:
    ROWS = MockConfig.ROWS
    COLS = MockConfig.COLS

# Import the SoilAgent (assuming soil.py is in the same directory)
from soil_sensor_agent import SoilAgent

# --- Mock Field Class (Simplified for Simulation) ---
class MockField:
    """A mock class for the Field environment to control soil data."""
    def __init__(self, rows=ROWS, cols=COLS):
        self.rows = rows
        self.cols = cols
        # Initialize with default values
        self.nutrients = np.full((rows, cols), 70.0)
        self.moisture = np.full((rows, cols), 70.0)
        
        # Set a low spot for testing at (0, 0) - a boundary case
        # Area: (0, 0), (-1, 0), (0, 1), (-1, 1) -> only (0, 0) and (0, 1) are valid
        self.nutrients[0, 0] = 50.0
        self.nutrients[0, 1] = 50.0
        self.moisture[0, 0] = 50.0
        self.moisture[0, 1] = 50.0
        
    def get_soil(self, row, col):
        """Returns [temperature, nutrients, moisture] or None if out of bounds."""
        if 0 <= row < self.rows and 0 <= col < self.cols:
            # [temperature, nutrients, moisture]
            return [25.0, self.nutrients[row, col], self.moisture[row, col]]
        else:
            return None

# --- Simulation Function ---
def run_soil_agent_simulation(steps=30):
    print("--- Soil Agent Simulation: 2x2 Boundary Case & Energy Management ---")
    
    # 1. Setup Environment and Agent
    mock_field = MockField()
    # Agent placed at (0, 0) - a boundary case
    agent = SoilAgent(mock_field, row=0, col=0, agent_id="SoilAgent_0_0")
    
    # Set a fixed seed for predictable energy loss across simulation runs
    random.seed(100) 
    
    # 2. Simulation Loop
    for step in range(1, steps + 1):
        print(f"\n==================== TIME STEP {step} ====================")
        
        # Capture the output of monitor_and_act
        f = io.StringIO()
        with redirect_stdout(f):
            agent.monitor_and_act()
        
        output = f.getvalue()
        print(output.strip())
        
        # Check for key events
        if "Requesting recharge" in output:
            print(f"*** EVENT: Energy Recharge CFP Sent to LogisticsAgent ***")
            # Simulate the agent being recharged by the LogisticsAgent
            agent.energy = 100
            print(f"*** SIMULATION: Agent recharged. Energy is now {agent.energy} ***")
        
        if "Requesting fertilization" in output:
            print(f"*** EVENT: Fertilization CFP Sent to FertilizerAgent ***")
            # Simulate the field being fertilized
            # The agent monitors (0, 0) and (0, 1). Let's simulate the fix.
            mock_field.nutrients[0, 0] = 80.0
            mock_field.nutrients[0, 1] = 80.0
            print(f"*** SIMULATION: Field fertilized. Nutrients in 2x2 area are now healthy. ***")

        if "Requesting irrigation" in output:
            print(f"*** EVENT: Irrigation CFP Sent to IrrigationAgent ***")
            # Simulate the field being watered
            mock_field.moisture[0, 0] = 80.0
            mock_field.moisture[0, 1] = 80.0
            print(f"*** SIMULATION: Field watered. Moisture in 2x2 area is now healthy. ***")

# --- Run Simulation ---
if __name__ == "__main__":
    # The script will automatically create a minimal config.py if it doesn't exist
    # and check for soil.py.
    
    # Create a dummy config.py if it doesn't exist (to prevent import error)
    if not os.path.exists("config.py"):
        with open("config.py", "w") as f:
            f.write("ROWS = 10\nCOLS = 10\n")
            
    # Ensure numpy is available
    try:
        import numpy
    except ImportError:
        print("Error: numpy is required. Please install it using 'pip3 install numpy'")
        sys.exit(1)
            
    run_soil_agent_simulation(steps=30)
