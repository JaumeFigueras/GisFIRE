from .Constants import *

FuelModels = {}
#Model #1
FuelModels[1] = {
    'fuel_load_1_h': 0.74 * TONS_ACRE_2_LB_FT2,
    'fuel_load_10_h': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_100_h': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_herb': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_wood': 0 * TONS_ACRE_2_LB_FT2,
    'sav_ratio_1_h': 3500,
    'sav_ratio_10_h': 109,
    'sav_ratio_100_h': 30,
    'sav_ratio_live_herb': 0,
    'sav_ratio_live_wood': 0,
    'fuel_bed_depth': 1,
    'moisture_of_extinction': 0.12,
    'sav_ratio': 3500,
    'bulk_density': 0.03,
    'relative_packing_ratio': 0.25
}
#Model #2
FuelModels[2] = {
    'fuel_load_1_h': 2 * TONS_ACRE_2_LB_FT2,
    'fuel_load_10_h': 1 * TONS_ACRE_2_LB_FT2,
    'fuel_load_100_h': 0.5 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_herb': 0.5 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_wood': 0 * TONS_ACRE_2_LB_FT2,
    'sav_ratio_1_h': 3000,
    'sav_ratio_10_h': 109,
    'sav_ratio_100_h': 30,
    'sav_ratio_live_herb': 1500,
    'sav_ratio_live_wood': 0,
    'fuel_bed_depth': 1,
    'moisture_of_extinction': 0.15,
    'sav_ratio': 2784,
    'bulk_density': 0.18,
    'relative_packing_ratio': 1.14
}
#Model #3
FuelModels[3] = {
    'fuel_load_1_h': 3 * TONS_ACRE_2_LB_FT2,
    'fuel_load_10_h': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_100_h': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_herb': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_wood': 0 * TONS_ACRE_2_LB_FT2,
    'sav_ratio_1_h': 1500,
    'sav_ratio_10_h': 109,
    'sav_ratio_100_h': 30,
    'sav_ratio_live_herb': 0,
    'sav_ratio_live_wood': 0,
    'fuel_bed_depth': 2.5,
    'moisture_of_extinction': 0.25,
    'sav_ratio': 1500,
    'bulk_density': 0.06,
    'relative_packing_ratio': 0.21
}
#Model #4
FuelModels[4] = {
    'fuel_load_1_h': 5 * TONS_ACRE_2_LB_FT2,
    'fuel_load_10_h': 4 * TONS_ACRE_2_LB_FT2,
    'fuel_load_100_h': 2 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_herb': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_wood': 5 * TONS_ACRE_2_LB_FT2,
    'sav_ratio_1_h': 2000,
    'sav_ratio_10_h': 109,
    'sav_ratio_100_h': 30,
    'sav_ratio_live_herb': 0,
    'sav_ratio_live_wood': 1500,
    'fuel_bed_depth': 6,
    'moisture_of_extinction': 0.2,
    'sav_ratio': 1739,
    'bulk_density': 0.12,
    'relative_packing_ratio': 0.52
}
#Model #5
FuelModels[5] = {
    'fuel_load_1_h': 1 * TONS_ACRE_2_LB_FT2,
    'fuel_load_10_h': 0.5 * TONS_ACRE_2_LB_FT2,
    'fuel_load_100_h': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_herb': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_wood': 2 * TONS_ACRE_2_LB_FT2,
    'sav_ratio_1_h': 2000,
    'sav_ratio_10_h': 109,
    'sav_ratio_100_h': 30,
    'sav_ratio_live_herb': 0,
    'sav_ratio_live_wood': 1500,
    'fuel_bed_depth': 2,
    'moisture_of_extinction': 0.2,
    'sav_ratio': 1683,
    'bulk_density': 0.08,
    'relative_packing_ratio': 0.33
}
#Model #6
FuelModels[6] = {
    'fuel_load_1_h': 1.5 * TONS_ACRE_2_LB_FT2,
    'fuel_load_10_h': 2.5 * TONS_ACRE_2_LB_FT2,
    'fuel_load_100_h': 2 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_herb': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_wood': 0 * TONS_ACRE_2_LB_FT2,
    'sav_ratio_1_h': 1750,
    'sav_ratio_10_h': 109,
    'sav_ratio_100_h': 30,
    'sav_ratio_live_herb': 0,
    'sav_ratio_live_wood': 0,
    'fuel_bed_depth': 2.5,
    'moisture_of_extinction': 0.25,
    'sav_ratio': 1564,
    'bulk_density': 0.11,
    'relative_packing_ratio': 0.43
}
#Model #7
FuelModels[7] = {
    'fuel_load_1_h': 1.1 * TONS_ACRE_2_LB_FT2,
    'fuel_load_10_h': 1.9 * TONS_ACRE_2_LB_FT2,
    'fuel_load_100_h': 1.5 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_herb': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_wood': 0.37 * TONS_ACRE_2_LB_FT2,
    'sav_ratio_1_h': 1750,
    'sav_ratio_10_h': 109,
    'sav_ratio_100_h': 30,
    'sav_ratio_live_herb': 0,
    'sav_ratio_live_wood': 1500,
    'fuel_bed_depth': 2.5,
    'moisture_of_extinction': 0.4,
    'sav_ratio': 1552,
    'bulk_density': 0.09,
    'relative_packing_ratio': 0.34
}
#Model #8
FuelModels[8] = {
    'fuel_load_1_h': 1.5 * TONS_ACRE_2_LB_FT2,
    'fuel_load_10_h': 1 * TONS_ACRE_2_LB_FT2,
    'fuel_load_100_h': 2.5 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_herb': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_wood': 0 * TONS_ACRE_2_LB_FT2,
    'sav_ratio_1_h': 2000,
    'sav_ratio_10_h': 109,
    'sav_ratio_100_h': 30,
    'sav_ratio_live_herb': 0,
    'sav_ratio_live_wood': 0,
    'fuel_bed_depth': 0.2,
    'moisture_of_extinction': 0.3,
    'sav_ratio': 1889,
    'bulk_density': 1.15,
    'relative_packing_ratio': 5.17
}
#Model #9
FuelModels[9] = {
    'fuel_load_1_h': 2.9 * TONS_ACRE_2_LB_FT2,
    'fuel_load_10_h': 0.41 * TONS_ACRE_2_LB_FT2,
    'fuel_load_100_h': 0.15 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_herb': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_wood': 0 * TONS_ACRE_2_LB_FT2,
    'sav_ratio_1_h': 2500,
    'sav_ratio_10_h': 109,
    'sav_ratio_100_h': 30,
    'sav_ratio_live_herb': 0,
    'sav_ratio_live_wood': 0,
    'fuel_bed_depth': 0.2,
    'moisture_of_extinction': 0.25,
    'sav_ratio': 2484,
    'bulk_density': 0.8,
    'relative_packing_ratio': 4.5
}
#Model #10
FuelModels[10] = {
    'fuel_load_1_h': 3 * TONS_ACRE_2_LB_FT2,
    'fuel_load_10_h': 2 * TONS_ACRE_2_LB_FT2,
    'fuel_load_100_h': 5 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_herb': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_wood': 2 * TONS_ACRE_2_LB_FT2,
    'sav_ratio_1_h': 2000,
    'sav_ratio_10_h': 109,
    'sav_ratio_100_h': 30,
    'sav_ratio_live_herb': 0,
    'sav_ratio_live_wood': 1500,
    'fuel_bed_depth': 1,
    'moisture_of_extinction': 0.25,
    'sav_ratio': 1764,
    'bulk_density': 0.55,
    'relative_packing_ratio': 2.35
}
#Model #11
FuelModels[11] = {
    'fuel_load_1_h': 1.5 * TONS_ACRE_2_LB_FT2,
    'fuel_load_10_h': 4.5 * TONS_ACRE_2_LB_FT2,
    'fuel_load_100_h': 5.5 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_herb': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_wood': 0 * TONS_ACRE_2_LB_FT2,
    'sav_ratio_1_h': 1500,
    'sav_ratio_10_h': 109,
    'sav_ratio_100_h': 30,
    'sav_ratio_live_herb': 0,
    'sav_ratio_live_wood': 0,
    'fuel_bed_depth': 1,
    'moisture_of_extinction': 0.15,
    'sav_ratio': 1182,
    'bulk_density': 0.53,
    'relative_packing_ratio': 1.62
}
#Model #12
FuelModels[12] = {
    'fuel_load_1_h': 4 * TONS_ACRE_2_LB_FT2,
    'fuel_load_10_h': 14 * TONS_ACRE_2_LB_FT2,
    'fuel_load_100_h': 16.5 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_herb': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_wood': 0 * TONS_ACRE_2_LB_FT2,
    'sav_ratio_1_h': 1500,
    'sav_ratio_10_h': 109,
    'sav_ratio_100_h': 30,
    'sav_ratio_live_herb': 0,
    'sav_ratio_live_wood': 0,
    'fuel_bed_depth': 2.3,
    'moisture_of_extinction': 0.2,
    'sav_ratio': 1145,
    'bulk_density': 0.69,
    'relative_packing_ratio': 2.06
}
#Model #13
FuelModels[13] = {
    'fuel_load_1_h': 7 * TONS_ACRE_2_LB_FT2,
    'fuel_load_10_h': 23 * TONS_ACRE_2_LB_FT2,
    'fuel_load_100_h': 28 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_herb': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_wood': 0 * TONS_ACRE_2_LB_FT2,
    'sav_ratio_1_h': 1500,
    'sav_ratio_10_h': 109,
    'sav_ratio_100_h': 30,
    'sav_ratio_live_herb': 0,
    'sav_ratio_live_wood': 0,
    'fuel_bed_depth': 3,
    'moisture_of_extinction': 0.25,
    'sav_ratio': 1159,
    'bulk_density': 0.89,
    'relative_packing_ratio': 2.68
}
#Model #GR1
FuelModels[101] = {
    'fuel_load_1_h': 7 * TONS_ACRE_2_LB_FT2,
    'fuel_load_10_h': 23 * TONS_ACRE_2_LB_FT2,
    'fuel_load_100_h': 28 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_herb': 0 * TONS_ACRE_2_LB_FT2,
    'fuel_load_live_wood': 0 * TONS_ACRE_2_LB_FT2,
    'sav_ratio_1_h': 1500,
    'sav_ratio_10_h': 109,
    'sav_ratio_100_h': 30,
    'sav_ratio_live_herb': 0,
    'sav_ratio_live_wood': 0,
    'fuel_bed_depth': 3,
    'moisture_of_extinction': 0.25,
    'sav_ratio': 1159,
    'bulk_density': 0.89,
    'relative_packing_ratio': 2.68
}

FuelModels['1'] = FuelModels[1]
FuelModels['2'] = FuelModels[2]
FuelModels['3'] = FuelModels[3]
FuelModels['4'] = FuelModels[4]
FuelModels['5'] = FuelModels[5]
FuelModels['6'] = FuelModels[6]
FuelModels['7'] = FuelModels[7]
FuelModels['8'] = FuelModels[8]
FuelModels['9'] = FuelModels[9]
FuelModels['10'] = FuelModels[10]
FuelModels['11'] = FuelModels[11]
FuelModels['12'] = FuelModels[12]
FuelModels['13'] = FuelModels[13]
#FuelModels['GR1'] = FuelModels[101]
