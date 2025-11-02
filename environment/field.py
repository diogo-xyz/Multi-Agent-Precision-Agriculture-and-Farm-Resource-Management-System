import numpy as np

from .moisture import Moisture
from .temperature import Temperature
from ..config import TICK_HOURS,ROWS,COLS

class Field:
    """
    Simula o estado do campo: humidade, nutrientes, plantação.
    Gera eventos climáticos e pestes
    """


    def __init__(self):
        self.day = 1
        self.hours = 9

        self.temperature = Temperature(self.day,self.hours)
        self.moisture = Moisture(ROWS,COLS)


        self.drought = 0

    def step(self):
        pass
    
    def aply_rain(self):
        pass
    
    def toggle_drought(self):
        self.drought = 0 if self.drought == 1 else 1

    def aply_pest(self):
        pass

    def aply_irrigation(self):
        pass

    def aply_fertilize(self):
        pass
    
    def get_drone(self):
        pass

    def get_soil(self):
        pass    