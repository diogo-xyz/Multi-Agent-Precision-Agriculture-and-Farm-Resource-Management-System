import numpy as np

from .moisture import Moisture
from .temperature import Temperature
from .moisture import Moisture
from .nutrients import Nutrients
from .crop import Crop
from ..events.pest_event import Pest
from ..events.rain_event import Rain
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
        self.nutrients = Nutrients(ROWS,COLS)
        self.crop = Crop(ROWS,COLS)

        self.drought = 0

        self.isPestActive = 0
        self.pest = Pest(ROWS,COLS)

        self.rain = Rain()

    def step(self):
        self.hours = (self.hours + 1) % 24
        self.day = (self.day % 365) + (1 if self.hours == 0 else 0)
    
        self.temperature.temperature = self.temperature.update_temperature(self.day,self.hours)

        self.rain.update_rain(self.day,self.drought,TICK_HOURS)

        self.moisture.moisture, 
        self.nutrients.nutrients = self.moisture.update_moisture(self.rain.rain,
                                                                self.temperature.temperature,
                                                                self.nutrients.nutrients,
                                                                self.crop.crop_stage,
                                                                self.crop.crop_type,
                                                                TICK_HOURS)

        self.nutrients.nutrients = self.nutrients.update_nutrients(self.drought,
                                                                   self.temperature.temperature,
                                                                   self.moisture.moisture,
                                                                   self.crop.crop_type,
                                                                   self.crop.crop_stage,
                                                                   TICK_HOURS)

        self.pest.update_pest()

        self.crop.update_crop(
            self.moisture.moisture,
            self.nutrients.nutrients,
            self.temperature.temperature,
            self.pest.pest,
            TICK_HOURS)

    def aply_rain(self,intensity):
        self.rain.aply_rain(intensity)
    
    def toggle_drought(self):
        self.drought = 0 if self.drought == 1 else 1

    def aply_pest(self):
        self.isPestActive = 1
        row = np.random.randint(0, ROWS)
        col = np.random.randint(0, COLS)
        self.pest.pest[row,col] = 1

    def remove_pest(self):
        self.isPestActive = 0
        self.pest.pest = np.zeros((ROWS,COLS))

    def aply_pesticide(self,row,col):
        self.pest.apply_pesticide(row,col,neighbor_effect= 0.75)

    def aply_irrigation(self,row,col,flow_rate_lph):
        pass

    def aply_fertilize(self,row,col,fertilzer_kg):
        pass
    
    def get_drone(self,row,col):
        return [self.crop.crop_stage[row,col],self.pest.pest[row,col]]

    def get_soil(self,row,col):
        return [self.temperature.temperature,self.nutrients.nutrients[row,col],self.moisture.moisture[row,col]]
    
    def teste_plantar(self,row,col,id_planta):
        pass

    def teste_colher(self,row,col):
        pass