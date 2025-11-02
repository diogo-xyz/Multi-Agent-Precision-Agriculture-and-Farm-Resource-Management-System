import numpy as np
import sys
import os

# Adicionar o diretório pai ao path para imports relativos
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from TB_Sistemas.environment.field import Field

def display_matrix(field):

    print("\n==================================================================")
    print("==================================================================")
    print("==================================================================\n")
    print(f"Day: {field.day} \t Hour: {field.hours}")
    print(f"Temperatura: {field.temperature.temperature}")
    print(f"Rain: {field.rain.rain}")
    print("Humidade:")
    print(np.array2string(field.moisture.moisture, precision=2, separator=', ', suppress_small=True))
    print("\nNutrientes:")
    print(np.array2string(field.nutrients.nutrients, precision=2, separator=', ', suppress_small=True))
    print("\nCrop_stage:")
    print(np.array2string(field.crop.crop_stage, precision=2, separator=', ', suppress_small=True))
    print("\nCrop_type:")
    print(np.array2string(field.crop.crop_type, precision=2, separator=', ', suppress_small=True))
    print("\nCrop_health:")
    print(np.array2string(field.crop.crop_health, precision=2, separator=', ', suppress_small=True))
    print("\nPest:")
    print(np.array2string(field.pest.pest, precision=2, separator=', ', suppress_small=True))


def aply(field):
    print("0: Peste \t 1: Remove Peste \t 2: Seca \t 3: Regar \t 4: Fertilizar \n5: Plantar \t 6: Colher \t\t 7: Chuva \t 8: Para chuvas:")
    escolha = int(input("Escolha:"))
    match (escolha):
        case 0:
            field.apply_pest()
        case 1: 
            field.remove_pest()
        case 2:
            field.toggle_drought()
        case 3:
            row,col = map(int, input("Row, Col: ").split())
            field.apply_irrigation(row,col)
        case 4:
            row,col = map(int, input("Row, Col: ").split())
            field.apply_fertilize(row,col)            
        case 5:
            row,col = map(int, input("Row, Col: ").split())
            plant_type = int(input("Tipo de planta :"))
            field.plant_seed(row,col,plant_type) 
        case 6:
            row,col = map(int, input("Row, Col: ").split())
            field.harvest(row,col)   
        case 7:
            intensity = int(input("Intesidade [1,2,3] :"))
            field.apply_rain(intensity)  
        case 8: 
            field.stop_rain() 
        case _:
            pass
    
    return

def run_simulation():
    field = Field()

    display_matrix(field)

    aply(field)

    display_matrix(field)
    #field.step()
    #display_matrix(field)
    aply(field)

    display_matrix(field)


if __name__ == "__main__":
    run_simulation()
