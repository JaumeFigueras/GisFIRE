from math import exp
from math import pow
from math import tan
from math import sin
from math import cos
from math import atan2

from .Constants import *
from .Fuels import FuelModels

def ros(model, humidity, wind, slope):
    """Example function with types documented in the docstring.

    `PEP 484`_ type annotations are supported. If attribute, parameter, and
    return types are annotated according to `PEP 484`_, they do not need to be
    included in the docstring:

    Args:
        param1 (int): The first parameter.
        param2 (str): The second parameter.

    Returns:
        bool: The return value. True for success, False otherwise.

    .. _PEP 484:
        https://www.python.org/dev/peps/pep-0484/

    """

    # Argument checking
    if not(isinstance(model, (int, str))):
        raise ValueError("model argument must be integer")
    if not(model in FuelModels):
        raise ValueError("model argument must be a valid identifier")
    if not(isinstance(humidity, (list, tuple))):
        raise ValueError("humidity argument has to be a [[3], [2]] list")
    elif not(len(humidity) == 2):
        raise ValueError("humidity argument has to be a [[3], [2]] list")
    elif not(isinstance(humidity[0], (list, tuple)) and isinstance(humidity[1], (list, tuple))):
        raise ValueError("humidity argument has to be a [[3], [2]] list")
    elif not((len(humidity[0]) == 3) and (len(humidity[1]) == 2)):
        raise ValueError("humidity argument has to be a [[3], [2]] list")
    else:
        flatten = [item for sublist in humidity for item in sublist]
        for item in flatten:
            if not(isinstance(item, (int, float))):
                raise ValueError("humidity argument has to be a [[3], [2]] list of numbers")
    if not(isinstance(wind, (int, float))):
        if isinstance(wind, (list, tuple)):
            if len(wind) == 2:
                if not((isinstance(wind[0], (int, float))) and (isinstance(wind[1], (int, float)))):
                    raise ValueError("wind argument has to be a number or two numbers vector")
            else:
                raise ValueError("wind argument has to be a number or two numbers vector")
        else:
            raise ValueError("wind argument has to be a number or two numbers vector")
    #ros calculation
    sav_ratio = [0] * 2
    sav_ratio[0] = [0] * 3
    sav_ratio[1] = [0] * 2
    sav_ratio[0][0] = FuelModels[model]['sav_ratio_1_h']
    sav_ratio[0][1] = FuelModels[model]['sav_ratio_10_h']
    sav_ratio[0][2] = FuelModels[model]['sav_ratio_100_h']
    sav_ratio[1][0] = FuelModels[model]['sav_ratio_live_herb']
    sav_ratio[1][1] = FuelModels[model]['sav_ratio_live_wood']
    fuel_load = [0] * 2
    fuel_load[0] = [0] * 3
    fuel_load[1] = [0] * 2
    fuel_load[0][0] = FuelModels[model]['fuel_load_1_h']
    fuel_load[0][1] = FuelModels[model]['fuel_load_10_h']
    fuel_load[0][2] = FuelModels[model]['fuel_load_100_h']
    fuel_load[1][0] = FuelModels[model]['fuel_load_live_herb']
    fuel_load[1][1] = FuelModels[model]['fuel_load_live_wood']
    Aij = [0] * 2
    Aij[0] = [0] * 3
    Aij[1] = [0] * 2
    particle_density = FuelConstants['particle_density']
    for i in range(0, 2):
        for j in range(0, len(Aij[i])):
            Aij[i][j] = (sav_ratio[i][j] * fuel_load[i][j]) / particle_density
    Ai = [0] * 2
    Ai[0] = sum(Aij[0])
    Ai[1] = sum(Aij[1])
    At = sum(Ai)
    fij = [0] * 2
    fij[0] = [0] * 3
    fij[1] = [0] * 2
    for i in range(0, 2):
        for j in range(0, len(fij[i])):
            fij[i][j] = Aij[i][j] / Ai[i] if Ai[i] > 0 else 0
    fi = [0] * 2
    fi[0] = Ai[0] / At
    fi[1] = Ai[1] / At
    sav_ratio_i = [0] * 2
    sav_ratio_i[0] = fij[0][0] * sav_ratio[0][0] + fij[0][1] * sav_ratio[0][1] + fij[0][2] * sav_ratio[0][2]
    sav_ratio_i[1] = fij[1][0] * sav_ratio[1][0] + fij[1][1] * sav_ratio[1][1]
    mean_sav_ratio = fi[0] * sav_ratio_i[0] + fi[1] * sav_ratio_i[1]
    fuel_bed_depth = FuelModels[model]['fuel_bed_depth']
    mean_bulk_density = (sum(fuel_load[0]) + sum(fuel_load[1])) / fuel_bed_depth
    particle_density = FuelConstants['particle_density']
    mean_packing_ratio = mean_bulk_density / particle_density
    propagating_flux_ratio = exp((0.792 + 0.681 * pow(mean_sav_ratio, 0.5)) * (0.1 + mean_packing_ratio)) * pow((192 + 0.2595 * mean_sav_ratio), -1)
    A = 133 * pow(mean_sav_ratio, -0.7913)
    mean_optimal_packing_ratio = 3.348 * pow(mean_sav_ratio, -0.8189)
    mean_maximum_reaction_velocity = pow(mean_sav_ratio, 1.5) / (495 + 0.0594 * pow(mean_sav_ratio, 1.5))
    mean_optimal_reaction_velocity = mean_maximum_reaction_velocity * pow((mean_packing_ratio / mean_optimal_packing_ratio), A) * exp(A * (1 - (mean_packing_ratio / mean_optimal_packing_ratio)))
    mineral_content = FuelConstants['mineral_content']
    net_fuel_load = [0] * 2
    net_fuel_load[0] = [0] * 3
    net_fuel_load[1] = [0] * 2
    for i in range(0, len(net_fuel_load)):
        for j in range(0, len(net_fuel_load[i])):
            net_fuel_load[i][j] = fuel_load[i][j] * (1 - mineral_content)
    net_fuel_load_dead = fij[0][0] * net_fuel_load[0][0] + fij[0][1] * net_fuel_load[0][1] + fij[0][2] * net_fuel_load[0][2]
    net_fuel_load_live = net_fuel_load[1][0] + net_fuel_load[1][1]
    heat_content = FuelConstants['heat_content']
    heat_content_i = [0] * 2
    heat_content_i[0] = heat_content * sum(fij[0])
    heat_content_i[1] = heat_content * sum(fij[1])
    fuel_moisrute_i = [0] * 2
    fuel_moisrute_i[0] = fij[0][0] * humidity[0][0] + fij[0][1] * humidity[0][1] + fij[0][2] * humidity[0][2]
    fuel_moisrute_i[1] = fij[1][0] * humidity[1][0] + fij[1][1] * humidity[1][1]
    Wnum = 0
    for j in range(0, len(sav_ratio[0])):
        if sav_ratio[0][j] > 0:
            Wnum += fuel_load[0][j] * exp(-138 / sav_ratio[0][j])
    Wden = 0
    for j in range(0, len(sav_ratio[1])):
        if sav_ratio[1][j] > 0:
            Wden += fuel_load[1][j] * exp(-500 / sav_ratio[1][j])
    W = Wnum / Wden if Wden > 0 else 0
    Mfdead = ((humidity[0][0] * fuel_load[0][0] * exp(-138 / sav_ratio[0][0])) + (humidity[0][1] * fuel_load[0][1] * exp(-138 / sav_ratio[0][1])) + (humidity[0][2] * fuel_load[0][2] * exp(-138 / sav_ratio[0][2]))) / ((fuel_load[0][0] * exp(-138 / sav_ratio[0][0])) + (fuel_load[0][1] * exp(-138 / sav_ratio[0][1])) + (fuel_load[0][2] * exp(-138 / sav_ratio[0][2])))
    dead_moisture_of_extinction = FuelModels[model]['moisture_of_extinction']
    live_moisture_of_extinction = max(2.9 * W * (1 - (Mfdead / dead_moisture_of_extinction)) - 0.226, dead_moisture_of_extinction)
    moisture_relation_i = [0] * 2
    moisture_relation_i[0] = min(1, fuel_moisrute_i[0] / dead_moisture_of_extinction)
    moisture_relation_i[1] = min(1, fuel_moisrute_i[1] / live_moisture_of_extinction)
    moisture_damping_i = [0] * 2
    for i in range(0, 2):
        moisture_damping_i[i] = 1 - 2.59 * moisture_relation_i[i] + 5.11 * pow(moisture_relation_i[i], 2) - 3.52 * pow(moisture_relation_i[i], 3)
    effective_mineral_content = FuelConstants['effective_mineral_content']
    mineral_damping = min(1, 0.174 * pow(effective_mineral_content, -0.19))
    intensity_reaction_a = net_fuel_load_dead * heat_content_i[0] * moisture_damping_i[0] * mineral_damping
    intensity_reaction_b = net_fuel_load_live * heat_content_i[1] * moisture_damping_i[1] * mineral_damping
    intensity_reaction = mean_optimal_reaction_velocity * (intensity_reaction_a + intensity_reaction_b)
    heat_of_preignition_ij = [0] * 2
    heat_of_preignition_ij[0] = [0] * 3
    heat_of_preignition_ij[1] = [0] * 2
    for i in range(0, 2):
        for j in range(0, len(heat_of_preignition_ij[i])):
            heat_of_preignition_ij[i][j] = 250 + 1116 * humidity[i][j]
    heat_number_tmp = [0] * 2
    for i in range(0, len(heat_number_tmp)):
        heat_number_tmp[i] = fi[i] * sum([a * (exp(-138 / b) if b > 0 else 0) * c for a, b, c in zip(fij[i], sav_ratio[i], heat_of_preignition_ij[i])])
    heat_sink = mean_bulk_density * sum(heat_number_tmp)
    C = 7.47 * exp(-0.133 * pow(mean_sav_ratio, 0.55))
    B = 0.02526 * pow(mean_sav_ratio, 0.54)
    E = 0.715 * exp(-3.59e-4 * mean_sav_ratio)
    slope_factor = 5.275 * pow(mean_packing_ratio, -0.3) * pow(tan(slope), 2)
    if isinstance(wind, (int, float)):
        wind = wind * METER_SECOND_TO_FEET_MINUTE
        wind_factor = C * pow(wind, B) * pow(mean_packing_ratio / mean_optimal_packing_ratio, -E)
        rate_of_spread = (intensity_reaction * propagating_flux_ratio * (1 + wind_factor + slope_factor)) / (heat_sink)
        #print('{0}'.format(rate_of_spread * FEET_TO_METER))
        return (rate_of_spread * FEET_TO_METER)
    else:
        wind[0] = wind[0] * METER_SECOND_TO_FEET_MINUTE
        wind_factor = C * pow(wind[0], B) * pow(mean_packing_ratio / mean_optimal_packing_ratio, -E)
        rate_of_spread = (intensity_reaction * propagating_flux_ratio) / (heat_sink)
        Ds = rate_of_spread * slope_factor
        Dw = rate_of_spread * wind_factor
        DH = pow((Ds + Dw * cos(wind[1]))**2 + (Dw * sin(wind[1])**2), 0.5)
        composite_rate_of_spread = rate_of_spread + DH
        alpha = atan2(Dw * sin(wind[1]), Ds + Dw * cos(wind[1]))
        effective_wind_factor = (composite_rate_of_spread / rate_of_spread) - 1
        effective_wind_speed = pow(effective_wind_factor * pow(mean_packing_ratio / mean_optimal_packing_ratio, E) / C, 1 / B)
        #print('{0}, {1}'.format(composite_rate_of_spread * FEET_TO_METER, alpha))
        return (composite_rate_of_spread * FEET_TO_METER, alpha, effective_wind_speed * (1 / METER_SECOND_TO_FEET_MINUTE))
