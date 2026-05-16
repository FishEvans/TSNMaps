import random
import os, sbs
from NPC_Ships import NPC_ScanData

#Script object - created by the python script, using the classes (e.g. SpaceObject)
#Sim Object - created by the Cosmos game engine.

versionNo = "1a"

CommandCodes = {
    "Fleet Commander": ["Xav24", "FLT"],
    "CiC": ["GM"],
    "Captain": ["Cap1", "cap2", "Cap3"],
    "Streamer": ["STM"]
}

waypointDatabase = {}

terrainDatabase = {
    "Ast1. Blue": ["asteroid_crystal_blue"],
    "Ast2. Red": ["asteroid_crystal_red"],
    "Ast3. Gold": ["asteroid_crystal_yellow"],
    "Ast4. Silver": ["asteroid_crystal_silver"],
    "Ast5. Green": ["asteroid_crystal_green"],
    "Ast. Colour Rand": ["asteroid_crystal_blue", "asteroid_crystal_red", "asteroid_crystal_yellow", "asteroid_crystal_silver", "asteroid_crystal_green"],
    "Ast6. Std": ["plain_asteroid_6"],
    "Ast7. Std": ["plain_asteroid_7"],
    "Ast8. Std": ["plain_asteroid_8"],
    "Ast9. Std": ["plain_asteroid_9"],
    "Ast10 Std": ["plain_asteroid_10"],
    "Ast11 Std": ["plain_asteroid_11"],
    "Ast. Std Rand": ["plain_asteroid_6", "plain_asteroid_7", "plain_asteroid_8", "plain_asteroid_9", "plain_asteroid_10", "plain_asteroid_11"],
    "Res. Denebite": ["asteroid_crystal_blue"],
    "Nebula": "Nebula",
    "Mine": "Mine"
}

asteroidDatabase = {
    "Ast1. Blue": {"Type": "Denebite", "Crystal Density": random.randint(50, 100)},
    "Ast2. Red": {"Type": "Volitile", "Crystal Density": random.randint(50, 100)},
    "Ast3. Gold": {"Type": "Gold", "Crystal Density": random.randint(50, 100)},
    "Ast4. Silver": {"Type": "Silver", "Crystal Density": random.randint(50, 100)},
    "Ast5. Green": {"Type": "Green", "Crystal Density": random.randint(50, 100)}
}

#civilian AMC
tierCAMC = {
    "Aid Package": ["Medical Supplies", "Power Relay", "Repair Materials"],
    "Packaging": ["Ashfilum"],
    "Meals": ["Produce", "Ice", "Packaging"],
    "Rations": ["Meals", "Packaging"],
    "Warning Buoy": ["Transmitter", "Casing"],
    "Virus Sample": ["Virus", "Coolant"]
}

# AMC = Advanced Manufacturing Complex
tier1AMC = {
    "Homing": ["Warhead", "Torpedo Casing", "Guidance System"],
    "Mine": ["Casing", "High Yield Warhead", "Sensor Suite"],
    "Nuke": ["High Yield Warhead", "Torpedo Casing", "Guidance System"],
    "EMP": ["Torpedo Casing", "Power Relay", "Guidance System"],
    "Comms Relay": ["Transmitter", "Casing", "Receiver"],
    "Sensor Relay": ["Sensor Suite", "Casing", "Transmitter"],
    "Scorch": ["Homing", "Sensor Suite"],
    "Disruptor": ["Homing", "Power Relay", "Mexalon"],
    "Penetration": ["Homing", "Tharium Plating"],
    "Computer Core": ["Data Core", "Analysis Suite", "Container"],
    "Black Box": ["Data Chip", "Micro Controller", "Tharium Plating"],
    "Fuel Cell 100": ["Denebite Crystals", "Power Relay", "Casing"],
    "Fuel Cell 200": ["Fuel Cell 100", "Denebite Crystals", "Container"]
}

tier1AMC.update(tierCAMC)

tier2AMC = {
    "Power Relay": ["Denebite Crystals", "Micro Controller", "Container"],
    "Repair Materials": ["Tharium Plating", "Iso B Circuit"],
    "Casing": ["Iron", "Alerite"],
    "Torpedo Casing": ["Casing", "Micro Controller", "Tharium"],
    "High Yield Warhead": ["Gredian", "Reisium", "Denebite"],
    "Warhead": ["Gredian", "Reisium"],
    "Medical Supplies": ["Analysis Suite", "Packaging", "Coolant"],
    "Transmitter": ["Micro Controller", "Cabrite"],
    "Receiver": ["Micro Controller", "Nuidinium"],
    "Sensor Suite": ["Micro Controller", "Receiver", "Cabrite"],
    "Guidance System": ["Micro Controller", "Iso B Circuit", "Tharium"],
    "Data Chip": ["Iso B Circuit", "Cabrite"],
    "Data Core": ["Data Chip", "Micro Controller", "Power Relay"]
}

tier2AMC.update(tier1AMC)

tier3AMC = {
    "Denebite Crystals": ["Denebite", "Aegirine"],
    "Analysis Suite": ["Micro Controller", "Sensor Suite", "Iso B Circuit"],
    "Tharium Plating": ["Tharium", "Iron", "Alerite"],
    "Iso B Circuit": ["Tharium", "Nuidinium"],
    "Micro Controller": ["Ashfilum", "Nuidinium", "Tharium"],
    "Container": ["Iron", "Ashfilum"],
    "Coolant": ["Ice", "Cabrite"],
    "Sensor Scrambler": ["Receiver", "Mexalon", "Power Relay"],
    "Vaccine": ["Virus Sample", "Medical Supplies", "Packaging"],
    "Warp Inhibitor": ["Sensor Scrambler", "Fuel Cell 100", "Mexalon"],
    "Fuel Cell 400": ["Fuel Cell 200", "Denebite Crystals", "Power Relay", "Mexalon"]
}

tier3AMC.update(tier2AMC)

#industrial AMC
tierIAMC = {
    "Denebite Crystals": ["Denebite", "Aegirine"],
    "Tharium Plating": ["Tharium", "Iron", "Alerite"],
    "Iso B Circuit": ["Tharium", "Nuidinium"],
    "Micro Controller": ["Ashfilum", "Nuidinium", "Tharium"],
    "Container": ["Iron", "Ashfilum"],
    "Coolant": ["Ice", "Cabrite"],
    "Sensor Scrambler": ["Receiver", "Mexalon", "Power Relay"],
    "Vaccine": ["Virus Sample", "Medical Supplies", "Packaging"],
    "Black Box": ["Data Chip", "Micro Controller", "Tharium Plating"],
    "Packaging": ["Ashfilum"],
    "Casing": ["Iron", "Alerite"],
    "Power Relay": ["Denebite Crystals", "Micro Controller", "Container"],
    "Analysis Suite": ["Micro Controller", "Sensor Suite", "Iso B Circuit"],
    "Medical Supplies": ["Analysis Suite", "Packaging", "Coolant"],
    "Data Chip": ["Iso B Circuit", "Cabrite"],
    "Data Core": ["Data Chip", "Micro Controller", "Power Relay"],
    "Fuel Cell 100": ["Denebite Crystals", "Power Relay", "Casing"],
    "Fuel Cell 200": ["Fuel Cell 100", "Denebite Crystals", "Container"],
    "Fuel Cell 400": ["Fuel Cell 200", "Denebite Crystals", "Power Relay", "Mexalon"]
}

#military AMC
# Includes ordnance manufacturing and supporting sub-assemblies, but omits recipes that
# resolve directly from raw materials alone.
tierMAMC = {
    "Homing": ["Warhead", "Torpedo Casing", "Guidance System"],
    "Mine": ["Casing", "High Yield Warhead", "Sensor Suite"],
    "Nuke": ["High Yield Warhead", "Torpedo Casing", "Guidance System"],
    "EMP": ["Torpedo Casing", "Power Relay", "Guidance System"],
    "Scorch": ["Homing", "Sensor Suite"],
    "Disruptor": ["Homing", "Power Relay", "Mexalon"],
    "Penetration": ["Homing", "Tharium Plating"],
    "Power Relay": ["Denebite Crystals", "Micro Controller", "Container"],
    "Torpedo Casing": ["Casing", "Micro Controller", "Tharium"],
    "Receiver": ["Micro Controller", "Nuidinium"],
    "Sensor Suite": ["Micro Controller", "Receiver", "Cabrite"],
    "Guidance System": ["Micro Controller", "Iso B Circuit", "Tharium"]
}

rawMaterials = {
    # Common material used in structures.
    "Iron": {
        "icon": 305,
        "signatures": ["Inert Material"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.5,
        "crystal": "asteroid_crystal_silver"
    },
    # Common material used in armor and other situations where extreme durability is needed.
    "Tharium": {
        "icon": 309,
        "signatures": ["Inert Material"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.5,
        "crystal": "asteroid_crystal_silver"
    },
    # Hazardous material, Grade 3. Reactive energetic material used in military explosive compounds.
    "Reisium": {
        "icon": 308,
        "signatures": ["Chemical", "Volatile Material", "Radiological"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.5,
        "crystal": "asteroid_crystal_red"
    },
    # Lightweight structural alloying material used in casings and reinforced plating.
    "Alerite": {
        "icon": 301,
        "signatures": ["Inert Material"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.5,
        "crystal": "asteroid_crystal_yellow"
    },
    # Industrial mineral used in advanced electronics and precision control systems.
    "Cabrite": {
        "icon": 303,
        "signatures": ["Chemical", "Electro Magnetic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.5,
        "crystal": "asteroid_crystal_green"
    },
    # Organic or synthetic polymer feedstock used in micro-components and fine electronics.
    "Ashfilum": {
        "icon": 302,
        "signatures": ["Organic", "Chemical"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.5,
        "crystal": "asteroid_crystal_green"
    },
    # Hazardous material, Grade 4. Useful for energy storage, but volatile in all forms.
    "Denebite": {
        "icon": 304,
        "signatures": ["Energy", "Volatile Material", "Exotic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.1,
        "crystal": "asteroid_crystal_blue"
    },
    # Silicate crystal mineral used to stabilize and refine Denebite into safer energy-storage products.
    "Aegirine": {
        "icon": 300,
        "signatures": ["Inert Material"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.5,
        "crystal": "asteroid_crystal_blue"
    },
    # Rare conductive material used in circuits, controllers, and other high-performance electronics.
    "Nuidinium": {
        "icon": 307,
        "signatures": ["Energy", "Electro Magnetic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.5,
        "crystal": "asteroid_crystal_yellow"
    },
    # Reactive energetic material used in warheads and other explosive ordnance.
    "Gredian": {
        "icon": 306,
        "signatures": ["Chemical", "Volatile Material"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.5,
        "crystal": "asteroid_crystal_red"
    },
    # Hazardous material, Grade 3.
    "Mexalon": {
        "icon": 310,
        "signatures": ["Chemical", "Exotic", "Volatile Material"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.3,
        "crystal": "asteroid_crystal_green"
    },
    # Frozen water used as a transportable source of water in space operations.
    "Ice": {
        "icon": 311,
        "signatures": ["Cryonic", "Chemical"],  # Temporary icon
        "colour": "#ffffff",
        "count": 0,
        "size": 0.5,
        "crystal": "asteroid_crystal_silver"
    }
}

shipItems = {
    "AMC": {
        "icon": 261,
        "signatures": ["Inert Material", "Energy"],
        "colour": "#00b300",
        "count": 0,
        "size": 3
    },
    "Life Support": {
        "icon": 280,
        "signatures": ["Organic", "Chemical", "Energy"],
        "colour": "#00b300",
        "count": 0,
        "size": 2
    },
    "Navigational Array": {
        "icon": 263,
        "signatures": ["Electro Magnetic", "Energy"],
        "colour": "#00b300",
        "count": 0,
        "size": 5
    },
    "Tactical Array": {
        "icon": 216,
        "signatures": ["Electro Magnetic", "Energy"],
        "colour": "#00b300",
        "count": 0,
        "size": 4
    },
    "FCS": {
        "icon": 54, #to update
        "signatures": ["Electro Magnetic", "Energy"],
        "colour": "#ccffff",
        "count": 0,
        "size": 4
    },
    "Computer Core": {
        "icon": 215,
        "signatures": ["Electro Magnetic", "Energy"],
        "colour": "#ccffff",
        "count": 0,
        "size": 2
    }
}

#update the commodities database to match items in the tier1 AMC system
commoditiesDatabase = {
    "Comms Relay": {
        "icon": 209,
        "signatures": ["Electro Magnetic", "Energy"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1
    },
    "Warp Inhibitor": {
        "icon": 230,
        "signatures": ["Gravitic", "Energy", "Exotic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1
    },
    "Sensor Relay": {
        "icon": 219,
        "signatures": ["Electro Magnetic", "Energy"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1
    },
    "Black Box": {
        "icon": 290,
        "signatures": ["Electro Magnetic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1,
        "active": True
    },
    "Aid Package": {
        "icon": 206,
        "signatures": ["Organic", "Chemical", "Energy"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1
    },
    "Repair Materials": {
        "icon": 218,
        "signatures": ["Inert Material", "Chemical"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.5
    },
    "Medical Supplies": {
        "icon": 208,
        "signatures": ["Organic", "Chemical"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.6
    },
    "Iso B Circuit": {
        "icon": 212,
        "signatures": ["Electro Magnetic", "Energy"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.1
    },
    "Container": {
        "icon": 221,
        "signatures": ["Inert Material", "Chemical"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.5
    },
    "Packaging": {
        "icon": 234,
        "signatures": ["Chemical"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.2
    },
    "Micro Controller": {
        "icon": 215,
        "signatures": ["Electro Magnetic", "Chemical"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.1
    },
    "High Yield Warhead": {
        "icon": 211,
        "signatures": ["Chemical", "Volatile Material", "Radiological", "Exotic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.6
    },
    "Warhead": {
        "icon": 210,
        "signatures": ["Chemical", "Volatile Material"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.5
    },
    "Torpedo Casing": {
        "icon": 245,
        "signatures": ["Inert Material", "Electro Magnetic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1
    },
    "Guidance System": {
        "icon": 200,
        "signatures": ["Electro Magnetic", "Energy"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.3
    },
    "Denebite Crystals": {
        "icon": 231,
        "signatures": ["Energy", "Exotic", "Shielding"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.3
    },
    "Tharium Plating": {
        "icon": 214,
        "signatures": ["Inert Material"],
        "colour": "#ffffff",
        "count": 0,
        "size": 2
    },
    "Sensor Suite": {
        "icon": 213,
        "signatures": ["Electro Magnetic", "Energy"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.6
    },
    "Casing": {
        "icon": 220,
        "signatures": ["Inert Material"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1
    },
    "Transmitter": {
        "icon": 224,
        "signatures": ["Electro Magnetic", "Energy"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.3
    },
    "Receiver": {
        "icon": 223,
        "signatures": ["Electro Magnetic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.3
    },
    "Power Relay": {
        "icon": 225,
        "signatures": ["Energy", "Electro Magnetic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.5
    },
    "Analysis Suite": {
        "icon": 274,
        "signatures": ["Electro Magnetic", "Energy"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.6
    },
    # Base items from specialist production lines and do not have a recipe.
    "Wild Animals": {
        "icon": 201,
        "signatures": ["Organic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1
    },
    "Pets": {
        "icon": 202,
        "signatures": ["Organic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1
    },
    "Coffee": {
        "icon": 203,
        "signatures": ["Organic", "Chemical"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.2
    },
    "Tea": {
        "icon": 204,
        "signatures": ["Organic", "Chemical"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.2
    },
    "Alcohol": {
        "icon": 205,
        "signatures": ["Organic", "Chemical", "Volatile Material"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.2
    },
    "Coolant": {
        "icon": 222,
        "signatures": ["Chemical", "Cryonic", "Shielding"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.4
    },
    # Base items from specialist production lines and do not have a recipe.
    # Renamed from Food.
    "Produce": {
        "icon": 207,
        "signatures": ["Organic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.4
    },
    "Meals": {
        "icon": 226,
        "signatures": ["Organic", "Chemical"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.4
    },
    "Rations": {
        "icon": 227,
        "signatures": ["Organic", "Chemical"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.3
    },
    # Base items from specialist production lines and do not have a recipe.
    "Virus": {
        "icon": 228,
        "signatures": ["Organic", "Exotic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.1,
        "intel": {}
    },
    "Virus Sample": {
        "icon": 228,  # Temporary icon
        "signatures": ["Organic", "Cryonic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.1,
    },
    "Vaccine": {
        "icon": 229,
        "signatures": ["Organic", "Chemical", "Cryonic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.1,
        "active": True
    },
    # Review name. Icon to be revised.
    "Warning Buoy": {
        "icon": 217,
        "signatures": ["Electro Magnetic", "Energy"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1,
        "intel": {}
    },
    "Fuel Cell 100": {
        "icon": 236,
        "signatures": ["Energy", "Chemical"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1,
        "active": True
    },
    "Fuel Cell 200": {
        "icon": 237,
        "signatures": ["Energy", "Chemical"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1.3,
        "active": True
    },
    "Fuel Cell 400": {
        "icon": 238,
        "signatures": ["Energy", "Chemical", "Shielding"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1.6,
        "active": True
    },
    "Sensor Scrambler": {
        "icon": 233,
        "signatures": ["Electro Magnetic", "Shielding"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.2,
    }
}

intelfragmentsDatabase = {
    "Data Core": {
        "icon": 291,
        "signatures": ["Electro Magnetic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1,
    },
    "Data Chip": {
        "icon": 292,
        "signatures": ["Electro Magnetic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 0.3,
    }
}

ordnanceDatabase = {
    "Homing": {
        "icon": 241,
        "signatures": ["Electro Magnetic", "Energy", "Volatile Material"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1,
        "speed": 40,
        "lifetime": 10,
        "flare_color": "white",
        "trail_color": "white",
        "warhead": ["standard", 0],
        "damage": 100,
        "explosion_size": 10,
        "explosion_color": "fire",
        "behavior": "homing",
        "energy_conversion_value": 0
    },
    "Scorch": {
        "icon": 244,
        "signatures": ["Energy", "Volatile Material"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1,
        "speed": 40,
        "lifetime": 10,
        "flare_color": "purple",
        "trail_color": "purple",
        "warhead": ["standard", 0],
        "damage": 1,
        "explosion_size": 10,
        "explosion_color": "fire",
        "behavior": "homing",
        "energy_conversion_value": 0
    },
    "Nuke": {
        "icon": 240,
        "signatures": ["Energy", "Volatile Material", "Radiological", "Exotic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1,
        "speed": 40,
        "lifetime": 10,
        "flare_color": "white",
        "trail_color": "#99f",
        "warhead": ["blast", 2000],
        "damage": 14,
        "explosion_size": 20,
        "explosion_color": "fire",
        "behavior": "homing",
        "energy_conversion_value": 0
    },
    "EMP": {
        "icon": 243,
        "signatures": ["Energy", "Electro Magnetic", "Volatile Material"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1,
        "speed": 40,
        "lifetime": 10,
        "flare_color": "yellow",
        "trail_color": "#99f",
        "warhead": ["blast, reduce_shields", 2000],
        "damage": 50,
        "explosion_size": 20,
        "explosion_color": "fire",
        "behavior": "homing",
        "energy_conversion_value": 0
    },
    "Mine": {
        "icon": 242,
        "signatures": ["Volatile Material", "Electro Magnetic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1,
        "speed": 20,
        "lifetime": 10,
        "flare_color": "white",
        "trail_color": "white",
        "warhead": ["blast", 2000],
        "damage": 14,
        "explosion_size": 20,
        "explosion_color": "fire",
        "behavior": "mine",
        "energy_conversion_value": 0
    },
    "Disruptor": {
        "icon": 247,
        "signatures": ["Energy", "Electro Magnetic"],
        "colour": "#ffffff",
        "count": 0,
        "size": 1,
        "speed": 40,
        "lifetime": 10,
        "flare_color": "green",
        "trail_color": "green",
        "warhead": ["standard", 0],
        "damage": 1,
        "explosion_size": 20,
        "explosion_color": "fire",
        "behavior": "homing",
        "energy_conversion_value": 0
    },
    "Penetration": {
        "icon": 246,
        "colour": "#ffffff",
        "count": 0,
        "size": 1,
        "speed": 40,
        "lifetime": 10,
        "flare_color": "red",
        "trail_color": "red",
        "warhead": ["standard", 0],
        "damage": 1,
        "explosion_size": 20,
        "explosion_color": "fire",
        "behavior": "homing",
        "energy_conversion_value": 0,
        "signatures": ["Exotic"]
    },
    "Viral Torp": {
        "icon": 249,
        "colour": "#0ed100",
        "count": 0,
        "size": 1,
        "speed": 40,
        "lifetime": 10,
        "flare_color": "red",
        "trail_color": "red",
        "warhead": ["standard", 0],
        "damage": 1,
        "explosion_size": 20,
        "explosion_color": "fire",
        "behavior": "homing",
        "energy_conversion_value": 0,
        "signatures": ["Alloy", "Virus", "Exotic"]
    },
    "AntiViral Torp": {
        "icon": 250,
        "colour": "#0ed100",
        "count": 0,
        "size": 1,
        "speed": 40,
        "lifetime": 10,
        "flare_color": "red",
        "trail_color": "red",
        "warhead": ["standard", 0],
        "damage": 1,
        "explosion_size": 20,
        "explosion_color": "fire",
        "behavior": "homing",
        "energy_conversion_value": 0,
        "signatures": ["Alloy", "Exotic"]
    },

}

masterDatabase = {}
masterDatabase.update(commoditiesDatabase)
masterDatabase.update(rawMaterials)
masterDatabase.update(shipItems)
masterDatabase.update(ordnanceDatabase)
masterDatabase.update(intelfragmentsDatabase)



defaultSideRaces = {
    "Default": [],
    "Allied": ["TSN", "Hjorden", "USFP", "Ximni", "USN"],
    "Hegemony": ["Torgoth", "Arvonian", "Kralien", "Skaraan"],
    "Pirate": ["Euphini", "Skull"]
}

raceCommanderTraits = {
    "TSN": {
        "Courage": [95, 99],
        "Stubborn": [80, 90],
        "Side": "Allied"
    },
    "Torgoth": {
        "Courage": [95, 99],
        "Stubborn": [80, 90],
        "Side": "Hegemony"
    },
    "Kralien": {
        "Courage": [85, 90],
        "Stubborn": [60, 70],
        "Side": "Hegemony"
    },
    "Arvonian": {
        "Courage": [70, 80],
        "Stubborn": [50, 80],
        "Side": "Hegemony"
    },
    "Skaraan": {
        "Courage": [98, 99],
        "Stubborn": [60, 70],
        "Side": "Hegemony"
    },
    "Euphini": {
        "Courage": [80, 90],
        "Stubborn": [60, 70],
        "Side": "Pirate"
    },
    "Skull": {
        "Courage": [80, 90],
        "Stubborn": [60, 70],
        "Side": "Pirate"
    },
    "Ximni": {
        "Courage": [98, 99],
        "Stubborn": [60, 70],
        "Side": "Allied"
    },
    "Hjorden": {
        "Courage": [98, 99],
        "Stubborn": [60, 70],
        "Side": "Allied"
    },
    "USFP": {
        "Courage": [98, 99],
        "Stubborn": [60, 70],
        "Side": "Allied"
    },
    "USN": {
        "Courage": [95, 99],
        "Stubborn": [60, 75],
        "Side": "Allied"
    }
}

usfpCivilians = {
    "transport_ship": {
        "tags": ["ship", "civilian", "usfp", "noncombat", "transport"],
        "systems": ["Impulse", "Shields"],
        "race": "USFP",
        "type": "Transport Vessel",
        "scandata": NPC_ScanData.usfpScanData,
        "description": "The Atlas class transport ship was designed as a reliable heavy lift vessel "
                       "for both civilian and military use within the USFP. It is frequently deployed "
                       "to move personnel vehicles and equipment between colonies and has earned a "
                       "reputation for endurance and adaptability. With reinforced hull plating redundant "
                       "life support systems and configurable cargo bays it excels in supporting large "
                       "scale construction projects and emergency evacuations alike. The Atlas class stands "
                       "as the logistical backbone of the USFP expansion efforts across known space."
    },
    "luxury_liner": {
        "tags": ["ship", "civilian", "usfp", "noncombat", "cargo", "transport"],
        "systems": ["Impulse", "Shields"],
        "race": "USFP",
        "type": "Luxury Liner",
        "scandata": NPC_ScanData.usfpScanData,
        "description": "The Elysium class luxury liner was constructed under commission by the Orion Leisure "
                       "Consortium and remains a hallmark of interstellar opulence within USFP space. It "
                       "is commonly encountered along major trade routes and in high traffic systems where "
                       "these vessels provide first class accommodations for diplomats merchants and wealthy "
                       "travelers. Featuring grand observation decks zero gravity entertainment chambers and "
                       "full service hospitality suites the Elysium class symbolizes comfort and prestige. Its "
                       "presence in any system is often regarded as a sign of prosperity and stable relations "
                       "within the region."
    },
    "cargo_ship": {
        "tags": ["ship", "civilian", "usfp", "noncombat", "cargo"],
        "systems": ["Impulse", "Shields"],
        "race": "USFP",
        "type": "Cargo Vessel",
        "scandata": NPC_ScanData.usfpScanData,
        "description": "The Hermes class cargo ship was designed by the Vorex of the USFP and"
                       " can be encountered in systems across the USFP. The cargo ship"
                       " has also been successfully traded with other local species along "
                       " the USFP border.^"
                       "The Hermes class of cargo ships is perfectly suited to transporting"
                       " vital supplies to the various USFP colonies and stations around the galaxy"
                       " due to its large cargo capacity and space for a single transport shuttle craft.",
    },
    "science_ship": {
        "tags": ["ship", "civilian", "usfp", "noncombat"],
        "systems": ["Impulse", "Shields"],
        "race": "USFP",
        "type": "Science Vessel",
        "scandata": NPC_ScanData.usfpScanData,
        "description": "The Daedalus class science vessel was developed by the USFP Advanced Research "
                       "Division in cooperation with the Vorex Engineering Guild. These ships can often "
                       "be found charting unexplored systems and conducting deep space analysis across the "
                       "USFP frontier. Equipped with advanced sensor arrays and modular laboratories as "
                       "well as containment facilities the Daedalus class is capable of supporting long "
                       "term research missions. Its design emphasizes versatility and allows it to conduct "
                       "everything from planetary surveys to biological and astronomical studies vital to the "
                       "expansion of USFP scientific knowledge."
    },
}

usnShips = {
    "USN_ScoutF": {
        "tags": ["ship", "combat", "usn", "support", "patrol", "light", "defender"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "USN",
        "type": "Scout F",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [100, 100],
        "systemhealth": [20, 15, 10, 15],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "USN_ScoutG": {
        "tags": ["ship", "combat", "usn", "support", "patrol", "light", "defender"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "USN",
        "type": "Scout G",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [100, 100],
        "systemhealth": [20, 15, 10, 15],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "USN_LightCruiser": {
        "tags": ["ship", "combat", "usn", "support", "patrol", "light", "defender"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "USN",
        "type": "Light Cruiser",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [120, 120],
        "systemhealth": [30, 30, 20, 30],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "USN_Cruiser": {
        "tags": ["ship", "combat", "usn", "support", "patrol", "defender"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "USN",
        "type": "Cruiser",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [130, 130],
        "systemhealth": [35, 35, 25, 35],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "USN_Dread": {
        "tags": ["ship", "combat", "usn", "support", "patrol", "defender"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "USN",
        "type": "Dreadnaught",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [150, 150],
        "systemhealth": [40, 40, 30, 40],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "USN_SuperD": {
        "tags": ["ship", "combat", "usn", "support", "patrol", "defender"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "USN",
        "type": "Super Destroyer",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [170, 170],
        "systemhealth": [45, 45, 35, 45],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    }
}

kralienShips = {
    "kralien_cruiser": {
        "tags": ["hegemony", "light", "combat", "ship"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Kralien",
        "type": "Cruiser",
        "scandata": NPC_ScanData.kralienScanData,
        "shields": [100, 100],
        "systemhealth": [10, 10, 10, 10],
        "systemrepair": 0.1,
        "shieldrepair": 0.05,
        "toughness": [30, 50]
    },
    "kralien_battleship": {
        "tags": ["hegemony", "medium", "combat", "ship"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Kralien",
        "type": "Battleship",
        "scandata": NPC_ScanData.kralienScanData,
        "shields": [110, 100],
        "systemhealth": [15, 10, 15, 10],
        "systemrepair": 0.1,
        "shieldrepair": 0.05,
        "toughness": [30, 50]
    },
    "kralien_dreadnought": {
        "tags": ["hegemony", "heavy", "combat", "ship"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Kralien",
        "type": "Dreadnought",
        "scandata": NPC_ScanData.kralienScanData,
        "shields": [120, 120],
        "systemhealth": [20, 15, 20, 15],
        "systemrepair": 0.1,
        "shieldrepair": 0.05,
        "toughness": [25, 50]
    },
    "kralien_drone_cruiser": {
        "tags": ["hegemony", "medium", "combat", "ship"],
        "systems": ["Impulse", "Shields", "Beams", "Drone Launchers"],
        "race": "Kralien",
        "type": "Drone Cruiser",
        "scandata": NPC_ScanData.kralienScanData,
        "shields": [100, 100],
        "systemhealth": [10, 10, 10, 10],
        "systemrepair": 0.1,
        "shieldrepair": 0.05,
        "toughness": [30, 50]
    },
    "Hegemony_Transport": {
        "tags": ["hegemony", "ship", "civilian", "noncombat", "cargo"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Kralien",
        "type": "Transport",
        "scandata": NPC_ScanData.kralienScanData,
        "shields": [100, 100],
        "systemhealth": [10, 10, 10, 10],
        "systemrepair": 0.1,
        "shieldrepair": 0.05,
        "toughness": [30, 50]
    },
}

skaraanShips = {
    "skaraan_defiler": {
        "tags": ["hegemony", "light", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Skaraan",
        "type": "Defiler",
        "scandata": NPC_ScanData.skaraanScanData,
        "shields": [150, 150],
        "systemhealth": [20, 20, 10, 20],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["Cloaking", "AntiTorp"]
    },
    "skaraan_executor": {
        "tags": ["hegemony", "medium", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Skaraan",
        "type": "Executor",
        "scandata": NPC_ScanData.skaraanScanData,
        "shields": [150, 150],
        "systemhealth": [30, 30, 20, 30],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["Cloaking", "AntiTorp"]
    },
    "skaraan_enforcer": {
        "tags": ["hegemony", "heavy", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Skaraan",
        "type": "Enforcer",
        "scandata": NPC_ScanData.skaraanScanData,
        "shields": [150, 150],
        "systemhealth": [30, 30, 30, 30],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["Cloaking", "AntiTorp"]
    },
}

torgothShips = {
    "torgoth_destroyer": {
        "tags": ["hegemony", "support", "combat", "ship"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Torgoth",
        "type": "Destroyer",
        "scandata": NPC_ScanData.torgothScanData,
        "shields": [150, 150],
        "systemhealth": [40, 40, 40, 40],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "torgoth_goliath": {
        "tags": ["hegemony", "light", "combat", "ship"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Torgoth",
        "type": "Goliath",
        "scandata": NPC_ScanData.torgothScanData,
        "shields": [180, 150],
        "systemhealth": [50, 50, 50, 50],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "torgoth_leviathan": {
        "tags": ["hegemony", "medium", "combat", "ship"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Torgoth",
        "type": "Leviathan",
        "scandata": NPC_ScanData.torgothScanData,
        "shields": [180, 180],
        "systemhealth": [80, 80, 50, 50],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "torgoth_behemoth": {
        "tags": ["hegemony", "heavy", "combat", "ship"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Torgoth",
        "type": "Behemoth",
        "scandata": NPC_ScanData.torgothScanData,
        "shields": [200, 200],
        "systemhealth": [80, 80, 80, 80],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "torgoth_command": {
        "tags": ["hegemony", "heavy", "combat", "ship"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Torgoth",
        "type": "Command",
        "scandata": NPC_ScanData.torgothScanData,
        "shields": [400, 400],
        "systemhealth": [100, 100, 100, 100],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
}

arvonianShips = {
    "arvonian_fighter": {
        "tags": ["hegemony", "fighter", "combat", "ship"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Arvonian",
        "type": "Fighter",
        "scandata": NPC_ScanData.genericScanData,
        "shields": [50, 50],
        "systemhealth": [5, 5, 5, 5],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "Arvo_Bomber": {
        "tags": ["hegemony", "bomber", "combat", "ship"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Arvonian",
        "type": "Bomber",
        "scandata": NPC_ScanData.genericScanData,
        "shields": [60, 60],
        "systemhealth": [8, 8, 8, 8],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "arvonian_destroyer": {
        "tags": ["hegemony", "support", "combat", "ship"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Arvonian",
        "type": "Destroyer",
        "scandata": NPC_ScanData.genericScanData,
        "shields": [150, 100],
        "systemhealth": [40, 40, 40, 40],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "arvonian_light_carrier": {
        "tags": ["hegemony", "medium", "combat", "ship", "carrier"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Arvonian",
        "type": "Light Carrier",
        "scandata": NPC_ScanData.genericScanData,
        "shields": [150, 100],
        "systemhealth": [50, 50, 50, 50],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "arvonian_carrier": {
        "tags": ["hegemony", "heavy", "combat", "ship", "carrier"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Arvonian",
        "type": "Carrier",
        "scandata": NPC_ScanData.genericScanData,
        "shields": [150, 150],
        "systemhealth": [80, 80, 80, 80],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "arvonian_command": {
        "tags": ["hegemony", "heavy", "combat", "ship", "carrier"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Arvonian",
        "type": "Command Carrier",
        "scandata": NPC_ScanData.genericScanData,
        "shields": [200, 200],
        "systemhealth": [80, 80, 80, 80],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
}

skullShips = {
    "pirate_fighter": {
        "tags": ["pirate", "fighter", "combat", "ship"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Skull",
        "type": "Fighter",
        "scandata": NPC_ScanData.genericScanData,
        "shields": [50, 50],
        "systemhealth": [5, 5, 5, 5],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "pirate_longbow": {
        "tags": ["pirate", "light", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Skull",
        "type": "Longbow",
        "scandata": NPC_ScanData.genericScanData,
        "shields": [100, 100],
        "systemhealth": [20, 20, 10, 20],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["LowVis"]
    },
    "pirate_strongbow": {
        "tags": ["pirate", "medium", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Skull",
        "type": "Strongbow",
        "scandata": NPC_ScanData.genericScanData,
        "shields": [130, 100],
        "systemhealth": [20, 20, 10, 20],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["LowVis"]
    },
    "pirate_brigantine": {
        "tags": ["pirate", "heavy", "combat", "ship", "carrier", "elite"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Skull",
        "type": "Brigantine",
        "scandata": NPC_ScanData.genericScanData,
        "shields": [150, 110],
        "systemhealth": [40, 40, 40, 40],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["LowVis"]
    },
    "pirate_transport": {
        "tags": ["pirate", "cargo", "ship", "transport"],
        "systems": ["Impulse", "Shields"],
        "race": "Skull",
        "type": "Transport",
        "scandata": NPC_ScanData.genericScanData,
        "shields": [120, 120],
        "systemhealth": [15, 15, 15, 15],
        "systemrepair": 0.1,
        "shieldrepair": 0.05
    },
}

tsnShips = {
    "tsn_fighter": {
        "tags": ["fighter", "combat", "ship", "tsn"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Fighter",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [50, 50],
        "systemhealth": [5, 5, 5, 5],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "tsn_shuttle": {
        "tags": ["fighter", "ship", "tsn"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Shuttle",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [50, 50],
        "systemhealth": [5, 5, 5, 5],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "tsn_light_cruiser": {
        "tags": ["ship", "combat", "tsn"],
        "systems": ["Impulse", "Shields", "Beams", "Drone Launchers"],
        "race": "TSN",
        "type": "Light Cruiser",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [150, 150],
        "systemhealth": [40, 40, 40, 40],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["AntiTorp"],
        "SetUp": { #data specifically for setting up the ObjectData set
            "drone_damage": [(0, 12)],
            "drone_launch_max_range": [(0, 4000)],
            "drone_launch_timer": [(0, 10)],
            "beamCycleTime": [(0, 3), (1, 3)],
            "beamDamage": [(0, 1.5), (1, 1.5)]
        },
    },
    "tsn_battle_cruiser": {
        "tags": ["ship", "combat", "tsn"],
        "systems": ["Impulse", "Shields", "Beams", "Drone Launchers"],
        "race": "TSN",
        "type": "Battle Cruiser",
        "shields": [180, 180],
        "systemhealth": [80, 80, 50, 50],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["AntiTorp"],
        "scandata": NPC_ScanData.usfpScanData,
        "SetUp": { #data specifically for setting up the ObjectData set
            "drone_damage": [(0, 12)],
            "drone_launch_max_range": [(0, 4000)],
            "drone_launch_timer": [(0, 10)],
            "beamCycleTime": [(0, 3), (1, 3), (2, 3), (3, 3)],
            "beamDamage": [(0, 1.5), (1, 1.5), (2, 1.5), (3, 1.5)]
        },
    },
    "tsn_destroyer": {
        "tags": ["ship", "combat", "tsn"],
        "systems": ["Impulse", "Shields", "Beams", "Drone Launchers"],
        "race": "TSN",
        "type": "Destroyer",
        "scandata": NPC_ScanData.usfpScanData,
        "abilities": ["AntiTorp"],
        "shields": [100, 100],
        "systemhealth": [10, 10, 10, 10],
        "systemrepair": 0.1,
        "shieldrepair": 0.05,
        "toughness": [30, 50],
        "SetUp": { #data specifically for setting up the ObjectData set
            "drone_damage": [(0, 10)],
            "drone_launch_max_range": [(0, 4000)],
            "drone_launch_timer": [(0, 15)]
        },
    },
    "tsn_nemesis_class_interceptor": {
        "tags": ["ship", "combat", "tsn", "interceptor"],
        "systems": ["Impulse", "Shields", "Beams", "Drone Launchers"],
        "race": "TSN",
        "type": "Interceptor",
        "shields": [100, 100],
        "systemhealth": [20, 20, 10, 20],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "scandata": NPC_ScanData.usfpScanData,
        "abilities": ["AntiTorp"],
        "SetUp": { #data specifically for setting up the ObjectData set
            "drone_damage": [(0, 10)],
            "drone_launch_max_range": [(0, 4000)],
            "drone_launch_timer": [(0, 15)]
        },
    },
    "tsn_scout": {
        "tags": ["ship", "combat", "tsn", "scout"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Scout",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [70, 70],
        "systemhealth": [15, 15, 10, 15],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "tsn_bomber": {
        "tags": ["ship", "combat", "tsn", "bomber"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Bomber",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [80, 80],
        "systemhealth": [20, 15, 10, 15],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "tsn_escort": {
        "tags": ["ship", "combat", "tsn", "escort"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Escort",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [90, 90],
        "systemhealth": [20, 15, 10, 15],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "tsn_warpster": {
        "tags": ["ship", "combat", "tsn", "scout", "utility"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Warpster",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [60, 60],
        "systemhealth": [15, 15, 10, 15],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "tsn_light_carrier": {
        "tags": ["ship", "combat", "tsn", "carrier", "light"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Light Carrier",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [160, 160],
        "systemhealth": [60, 60, 60, 60],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["AntiTorp"]
    },
    "tsn_carrier": {
        "tags": ["ship", "combat", "tsn", "carrier"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Carrier",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [200, 200],
        "systemhealth": [80, 80, 80, 80],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["AntiTorp"]
    },
    "tsn_heavy_cruiser": {
        "tags": ["ship", "combat", "tsn", "heavy", "cruiser"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Heavy Cruiser",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [180, 180],
        "systemhealth": [70, 70, 70, 70],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["AntiTorp"]
    },
    "tsn_missile_cruiser": {
        "tags": ["ship", "combat", "tsn", "cruiser", "missile"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Missile Cruiser",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [170, 170],
        "systemhealth": [70, 70, 70, 70],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["AntiTorp"]
    },
    "tsn_mine_layer": {
        "tags": ["ship", "combat", "tsn", "mine"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Mine Layer",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [120, 120],
        "systemhealth": [60, 60, 60, 60],
        "systemrepair": 0.001,
        "shieldrepair": 0.01
    },
    "tsn_juggernaut": {
        "tags": ["ship", "combat", "tsn", "juggernaut", "heavy"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Juggernaut",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [220, 220],
        "systemhealth": [100, 100, 100, 100],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["AntiTorp"]
    },
    "tsn_battleship": {
        "tags": ["ship", "combat", "tsn", "battleship"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Battleship",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [240, 240],
        "systemhealth": [90, 90, 90, 90],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["AntiTorp"]
    },
    "tsn_dreadnought": {
        "tags": ["ship", "combat", "tsn", "dreadnought"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Dreadnought",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [280, 280],
        "systemhealth": [110, 110, 110, 110],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["AntiTorp"]
    },
    "usfp_patrol_boat": {
        "tags": ["ship", "combat", "tsn"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Patrol Boat",
        "scandata": NPC_ScanData.usfpScanData,
        "shields": [100, 100],
        "systemhealth": [10, 10, 10, 10],
        "systemrepair": 0.1,
        "shieldrepair": 0.05,
        "toughness": [30, 50],
        "abilities": ["AntiTorp"]
    },
    "tsn_lion_class_supply": {
        "tags": ["ship", "combat", "tsn", "auxiliary"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "TSN",
        "type": "Auxiliary",
        "scandata": NPC_ScanData.usfpScanData,
        "Teams": {},
        "Shuttles": {},
        "Cargo": {},
        "shields": [90, 90],
        "systemhealth": [10, 10, 10, 10],
        "systemrepair": 0.1,
        "shieldrepair": 0.05,
        "toughness": [30, 50],
        "abilities": ["AntiTorp"]
    }
}

euphiniShips = {
    "pirate_arrow": {
        "tags": ["pirate", "light", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Euphini",
        "type": "Arrow",
        "scandata": NPC_ScanData.genericScanData,
        "shields": [100, 100],
        "systemhealth": [10, 10, 10, 10],
        "shieldrepair": 0.05,
        "toughness": [30, 50],
        "abilities": ["Spoofing"],
        "SetUp": { #data specifically for setting up the ObjectData set
            "beamCycleTime": [(0, 2), (1, 1)],
            "beamDamage": [(0, 1.1), (1, 1.1)]
        },
    },
    "pirate_axe": {
        "tags": ["pirate", "medium", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Euphini",
        "type": "Axe",
        "scandata": NPC_ScanData.genericScanData,
        "shields": [110, 100],
        "systemhealth": [15, 10, 15, 10],
        "systemrepair": 0.1,
        "shieldrepair": 0.05,
        "toughness": [30, 50],
        "abilities": ["Spoofing"],
        "SetUp": { #data specifically for setting up the ObjectData set
            "beamCycleTime": [(0, 1), (1, 2), (2, 2)],
            "beamDamage": [(0, 1.1), (1, 1.1), (2, 1.1)]
        },
    },
}

hjordenShips = {
    "hjorden_cruiser": {
        "tags": ["hjorden", "ship", "medium", "combat"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Hjorden",
        "type": "Cruiser",
        "scandata": NPC_ScanData.genericScanData,
        "shields": [100, 100],
        "systemhealth": [10, 10, 10, 10],
        "systemrepair": 0.1,
        "shieldrepair": 0.05,
        "toughness": [30, 50]
    },}

ximniShips = {
    "xim_scout": {
        "tags": ["ximni", "light", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Ximni",
        "type": "Scout",
        "scandata": NPC_ScanData.ximniScanData,
        "shields": [150, 150],
        "systemhealth": [20, 20, 10, 20],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["JumpDrive"]
    },
    "xim_missile_cruiser": {
        "tags": ["ximni", "medium", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Ximni",
        "type": "Missile Cruiser",
        "scandata": NPC_ScanData.ximniScanData,
        "shields": [150, 150],
        "systemhealth": [20, 20, 10, 20],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["JumpDrive"],
        "SetUp": { #data specifically for setting up the ObjectData set
            "drone_damage": [(0, 12)],
            "drone_launch_max_range": [(0, 4000)],
            "drone_launch_timer": [(0, 10)]
        },
    },
    "xim_light_cruiser": {
        "tags": ["ximni", "medium", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Ximni",
        "type": "Light Carrier",
        "scandata": NPC_ScanData.ximniScanData,
        "shields": [150, 150],
        "systemhealth": [20, 20, 10, 20],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["JumpDrive"]
    },
    "xim_corvette": {
        "tags": ["ximni", "light", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Ximni",
        "type": "Corvette",
        "scandata": NPC_ScanData.ximniScanData,
        "shields": [100, 100],
        "systemhealth": [20, 20, 10, 10],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["JumpDrive"]
    },
    "xim_escort": {
        "tags": ["ximni", "light", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Ximni",
        "type": "Escort",
        "scandata": NPC_ScanData.ximniScanData,
        "shields": [100, 100],
        "systemhealth": [20, 20, 10, 10],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["JumpDrive"]
    },
    "xim_dreadnought": {
        "tags": ["ximni", "heavy", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Ximni",
        "type": "Dreadnought",
        "scandata": NPC_ScanData.ximniScanData,
        "shields": [250, 250],
        "systemhealth": [80, 80, 80, 80],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["JumpDrive"],
        "SetUp": { #data specifically for setting up the ObjectData set
            "beamCycleTime": [(0, 3), (1, 3), (2, 3), (3, 3)],
            "beamDamage": [(0, 1.8), (1, 1.8), (2, 1.8), (3, 1.8)]
        },
    },
    "xim_light_carrier": {
        "tags": ["ximni", "medium", "combat", "ship", "elite", "carrier"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Ximni",
        "type": "Light Carrier",
        "scandata": NPC_ScanData.ximniScanData,
        "shields": [150, 150],
        "systemhealth": [50, 50, 50, 50],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["JumpDrive"]
    },
    "xim_carrier": {
        "tags": ["ximni", "heavy", "combat", "ship", "elite", "carrier"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Ximni",
        "type": "Carrier",
        "scandata": NPC_ScanData.ximniScanData,
        "shields": [150, 150],
        "systemhealth": [80, 80, 80, 80],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["JumpDrive"]
    },
    "xim_destroyer": {
        "tags": ["ximni", "light", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Ximni",
        "type": "Destroyer",
        "scandata": NPC_ScanData.ximniScanData,
        "shields": [150, 100],
        "systemhealth": [40, 40, 40, 40],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["JumpDrive"]
    },
    "xim_corsair": {
        "tags": ["ximni", "light", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Ximni",
        "type": "Corsair",
        "scandata": NPC_ScanData.ximniScanData,
        "shields": [80, 80],
        "systemhealth": [10, 10, 10, 10],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["JumpDrive"]
    },
    "xim_battleship": {
        "tags": ["ximni", "medium", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Drone Launchers", "Beams"],
        "race": "Ximni",
        "type": "Battleship",
        "scandata": NPC_ScanData.ximniScanData,
        "shields": [220, 200],
        "systemhealth": [80, 80, 50, 50],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["JumpDrive"],
        "SetUp": { #data specifically for setting up the ObjectData set
            "beamCycleTime": [(0, 3), (1, 3), (2, 3), (3, 3)],
            "beamDamage": [(0, 1.5), (1, 1.5), (2, 1.5), (3, 1.5)]
        },
    },
    "xim_avenger": {
        "tags": ["ximni", "fighter", "combat", "ship", "elite"],
        "systems": ["Impulse", "Shields", "Beams"],
        "race": "Ximni",
        "type": "Avenger",
        "scandata": NPC_ScanData.ximniScanData,
        "shields": [50, 50],
        "systemhealth": [5, 5, 5, 5],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
        "abilities": ["JumpDrive"]
    },
}

usfpStations = {
    "starbase_civil": {
        "tags": ["station", "usfp", "civilian", "cargo"],
        "type": "Civilian",
        "race": 'USFP',
        "consume": ["Coffee", "Tea", "Alcohol", "Food", "Medical Supplies"],
        "demand": ["Coffee", "Tea", "Alcohol", "Food", "Medical Supplies", "Repair Materials", "Power Relay"],
        "supply": ["Aid Package", "Pets", "Data Chip"],
        "scandata": NPC_ScanData.usfpstationScanData,
        "Teams":    {},
        "Shuttles": {},
        "AMC": "C"
    },
    "starbase_industry": {
        "tags": ["station", "usfp", "civilian", "cargo"],
        "type": "Industrial",
        "race": 'USFP',
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.usfpstationScanData,
        "Teams":    {},
        "Shuttles": {},
        "AMC": "C"
    },
    "starbase_science": {
        "tags": ["station", "usfp", "civilian"],
        "type": "Science",
        "race": 'USFP',
        "consume": ["Coffee", "Tea", "Alcohol", "Food"],
        "demand": ["Power Relay", "Analysis Suite", "Transmitter", "Receiver", "Casing", "Denebite Crystals", "Guidance System",
                   "Iso B Circuit"],
        "supply": [],
        "scandata": NPC_ScanData.usfpstationScanData,
        "Teams":    {},
        "Shuttles": {},
        "AMC": "C"
    },
    "usfp_industrial_assembly": {
        "tags": ["station", "usfp", "civilian", "industrial"],
        "type": "Assembly Yard",
        "race": 'USFP',
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.usfpstationScanData,
        "Teams": {},
        "Shuttles": {},
        "AMC": "C"
    },
    "usfp_industrial_processor": {
        "tags": ["station", "usfp", "civilian", "industrial"],
        "type": "Processor Unit",
        "race": 'USFP',
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.usfpstationScanData,
        "Teams": {},
        "Shuttles": {},
        "AMC": "C"
    },
    "usfp_industrial_refinary": {
        "tags": ["station", "usfp", "civilian", "industrial"],
        "type": "Refinary Unit",
        "race": 'USFP',
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.usfpstationScanData,
        "Teams": {},
        "Shuttles": {},
        "AMC": "C"
    },
    "usfp_industrial_storage": {
        "tags": ["station", "usfp", "civilian", "industrial"],
        "type": "Storage Module",
        "race": 'USFP',
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.usfpstationScanData,
        "Teams": {},
        "Shuttles": {},
        "AMC": "C"
    },
    "usfp_industrial_unit": {
        "tags": ["station", "usfp", "civilian", "industrial"],
        "type": "Industrial Unit",
        "race": 'USFP',
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.usfpstationScanData,
        "Teams": {},
        "Shuttles": {},
        "AMC": "C"
    },
    "usfp_shipyard": {
        "tags": ["station", "usfp", "civilian", "industrial"],
        "type": "Shipyard",
        "race": 'USFP',
        "consume": [],
        "demand": ["Tharium Plating", "Iso B Circuit", "Repair Materials", "Micro Controller", "Denebite Crystals"],
        "supply": [],
        "scandata": NPC_ScanData.usfpstationScanData,
        "Teams": {},
        "Shuttles": {},
        "AMC": "C"
    },
    "starbase_deep_space": {
        "tags": ["station", "usfp", "civilian"],
        "type": "Deep Space Station",
        "race": 'USFP',
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.usfpstationScanData,
        "Teams": {},
        "Shuttles": {},
        "AMC": "C"
    }
}

tsnStations = {
    "starbase_command": {
        "tags": ["station", "usfp"],
        "type": "Command",
        "race": 'TSN',
        "consume": [],
        "demand": ["Warhead", "Torpedo Casing", "Guidance System", "Casing", "High Yield Warhead", "Sensor Suite", "Power Relay"],
        "supply": list(ordnanceDatabase.keys()),
        "scandata": NPC_ScanData.usfpScanData,
        "Teams":    {"DamCon": 6,
                     "Medics": 4,
                     "Marines": 2,
                     "Combat Engineers": 4,
                     },
        "Shuttles": {"Ranger": 3,
                     "Cargo Shuttle": 2,
                     "Fighter": 8
                     },
        "AMC": "C"
    },
}

arvonianStations = {
    "starbase_arvonian": {
        "tags": ["station", "hegemony"],
        "type": "Command",
        "race": 'Arvonian',
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.genericScanData,
        "Teams":    {},
        "Shuttles": {},
    },
}

torgothStations = {
    "starbase_torgoth": {
        "tags": ["station", "hegemony"],
        "type": "Command",
        "race": 'Torgoth',
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.torgothStationScanData,
        "Teams":    {},
        "Shuttles": {},
    }
}

skaraanStations = {
    "starbase_skaraan": {
        "tags": ["station", "hegemony"],
        "type": "Command",
        "race": 'Skaraan',
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.skaraanScanData,
        "Teams": {},
        "Shuttles": {}
    }
}

kralienStations = {
    "starbase_kralien": {
        "tags": ["station", "hegemony"],
        "type": "Command",
        "race": 'Kralien',
        "armour": 500,
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.kralienstationScanData,
        "Teams":    {},
        "Shuttles": {},
    },
    "hegemony_generator": {
        "tags": ["station", "hegemony"],
        "type": "Generator",
        "race": 'Kralien',
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.kralienstationScanData,
        "Teams":    {},
        "Shuttles": {},
    },
    "hegemony_gasextractor": {
        "tags": ["station", "hegemony"],
        "type": "Gas Extractor",
        "race": 'Kralien',
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.kralienstationScanData,
        "Teams":    {},
        "Shuttles": {},
    },
    "hegemony_drydock": {
        "tags": ["station", "hegemony"],
        "type": "Dry Dock",
        "race": 'Kralien',
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.kralienstationScanData,
        "Teams": {},
        "Shuttles": {},
    },
}

hjordenStations = {}

euphiniStations = {
    "pirate_military_base": {
        "tags": ["station", "pirate"],
        "type": "Pirate Base",
        "race": 'Euphini',
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.genericScanData,
        "Teams": {},
        "Shuttles": {},
    },
    "pirate_cache_1": {
        "tags": ["station", "pirate"],
        "type": "Cache",
        "race": 'Euphini',
        "consume": [],
        "demand": [],
        "supply": [],
        "scandata": NPC_ScanData.genericScanData,
        "Teams": {},
        "Shuttles": {},
    },
}

skullStations = {}

ximniStations = {}

infrastructure = {
    "jump_node": {
        "tags": ["node"],
        "type": "Jump Node",
        "race": "USFP",
        "scandata": NPC_ScanData.genericScanData

    },
}

usfpPlatforms = {
    "defense_platform_fighter": {
        "tags": ["defense", "usfp", "platform"],
        "systems": ["Shields", "Beams"],
        "type": "Fighter Platform",
        "race": 'TSN',
        "scandata": NPC_ScanData.usfpstationScanData,
        "shields": [250, 250],
        "systemhealth": [50, 50, 50, 50],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
    },
    "defense_platform_torp": {
        "tags": ["defense", "usfp", "platform"],
        "systems": ["Shields", "Beams", "Drone Launchers"],
        "type": "Torpedo Platform",
        "race": 'TSN',
        "scandata": NPC_ScanData.usfpstationScanData,
        "shields": [250, 250],
        "systemhealth": [50, 50, 50, 50],
    },
    "defense_platform_beam": {
        "tags": ["defense", "usfp", "platform"],
        "type": "LR Beam Platform",
        "systems": ["Shields", "Beams"],
        "race": 'TSN',
        "scandata": NPC_ScanData.usfpstationScanData,
        "shields": [250, 250],
        "systemhealth": [50, 50, 50, 50],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
    }
}

kralienPlatforms = {
    "hegemony_beam_platform": {
        "tags": ["defense", "hegemony", "platform"],
        "type": "Weapon Platform",
        "systems": ["Shields", "Beams"],
        "race": 'Kralien',
        "scandata": NPC_ScanData.usfpstationScanData,
        "shields": [250, 250],
        "systemhealth": [50, 50, 50, 50],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
    },
    "Hegemony_SlingAcu": {
        "tags": ["platform", "static", "hegemony"],
        "type": "Accumulator",
        "systems": ["Shields"],
        "race": 'Kralien',
        "scandata": NPC_ScanData.kralienstationScanData,
        "shields": [500, 500],
        "systemhealth": [150, 150, 150, 150],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
    },
    "Hegemony_Slingshot": {
        "tags": ["platform", "static", "hegemony"],
        "type": "Slingshot Platform",
        "systems": ["Shields"],
        "race": 'Kralien',
        "scandata": NPC_ScanData.kralienstationScanData,
        "shields": [5000, 5000],
        "systemhealth": [500, 500, 500, 500],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
    },
    "Hegemony_SlingAntenna": {
        "tags": ["platform", "static", "hegemony"],
        "type": "Slingshot Antenna",
        "systems": ["Shields"],
        "race": 'Kralien',
        "scandata": NPC_ScanData.kralienstationScanData,
        "shields": [500, 500],
        "systemhealth": [100, 100, 100, 100],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
    }
}
arvonianPlatforms = {
    "hegemony_fighter_platform": {
        "tags": ["defense", "hegemony", "arvonian", "platform"],
        "type": "Dry Dock",
        "systems": ["Shields"],
        "race": 'Arvonian',
        "scandata": NPC_ScanData.kralienstationScanData,
        "shields": [200, 200],
        "systemhealth": [50, 50, 50, 50],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
    },
    "arvonian_platform": {
        "tags": ["defense", "hegemony", "arvonian", "platform"],
        "type": "Platform",
        "systems": ["Shields"],
        "race": 'Arvonian',
        "scandata": NPC_ScanData.genericScanData,
        "shields": [200, 200],
        "systemhealth": [50, 50, 50, 50],
        "systemrepair": 0.001,
        "shieldrepair": 0.01,
    }
}

torgothPlatforms = {}
tsnPlatforms = {}
skaraanPlatforms = {}
hjordenPlatforms = {}
skullPlatforms = {}
euphiniPlatforms = {}
ximniPlatforms = {}

shipProperties = usfpCivilians | usnShips | kralienShips | skaraanShips | torgothShips | arvonianShips | skullShips | tsnShips | euphiniShips | hjordenShips | ximniShips
stationProperties = usfpStations | arvonianStations | kralienStations | torgothStations | tsnStations | skaraanStations | hjordenStations | euphiniStations | skullStations
platformProperties = ximniPlatforms | usfpPlatforms | arvonianPlatforms | torgothPlatforms | tsnPlatforms | skaraanPlatforms | hjordenPlatforms | skullPlatforms | euphiniPlatforms | kralienPlatforms
allProperties = shipProperties | stationProperties | infrastructure | platformProperties

eliteabilities = ["elite_drone_launcher", "elite_main_scn_invis", "elite_low_vis"]


#compiling in game database of all shipData.json entries
def find(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

TagsDatabase = set()
for object, data in allProperties.items():
    tags = data.get("tags")
    for tag in tags:
        TagsDatabase.add(tag)

shuttleNames = {
    "TSN":
        ["Apollo",
        "Arcturus",
        "Atlas",
        "Andromeda",
        "Aurora",
        "Antares",
        "Astra",
        "Alpha",
        "Archer",
        "Aegis",
        "Astraeus",
        "Altair",
        "Argo",
        "Aether",
        "Astrid",
        "Avalon",
        "Alcyone",
        "Arcadia",
        "Aurorae",
        "Borealis",
        "Banshee",
        "Bastion",
        "Boreas",
        "Bravo",
        "Brilliance",
        "Bolt",
        "Beta",
        "Borealis",
        "Cosmos",
        "Celestial",
        "Comet",
        "Cygnus",
        "Centauri",
        "Corona",
        "Cyclone",
        "Constellation",
        "Calypso",
        "Ceres",
        "Celestia",
        "Charon",
        "Cypher",
        "Cerberus",
        "Discovery",
        "Dragon",
        "Diligence",
        "Dione",
        "Delphinus",
        "Delphine",
        "Defender",
        "Demeter",
        "Defiance",
        "Divinity",
        "Endeavour",
        "Equinox",
        "Eclipse",
        "Elara",
        "Eos",
        "Excalibur",
        "Elysium",
        "Emissary",
        "Eridanus",
        "Epiphany",
        "Excelsior",
        "Ecliptic",
        "Ethereal"]
}

EngineeringPowerSliderDatabase = {
    0: "Beams",
    1: "Torps",
    2: "Impulse",
    3: "Warp",
    4: "Maneuver",
    5: "Sensors",
    6: "F. Shield",
    7: "R. Shield"
}

EngineeringCoolantDatabase = {
    0: "Weapons",
    1: "Engines",
    2: "Sensors",
    3: "Shields"
}

hotkeys = ["KEY_0",
    "KEY_1",
    "KEY_2",
    "KEY_3",
    "KEY_4",
    "KEY_5",
    "KEY_6",
    "KEY_7",
    "KEY_8",
    "KEY_9",
    "KEY_A",
    "KEY_B",
    "KEY_C",
    "KEY_D",
    "KEY_E",
    "KEY_F",
    "KEY_G",
    "KEY_H",
    "KEY_I",
    "KEY_J",
    "KEY_K",
    "KEY_L",
    "KEY_M",
    "KEY_N",
    "KEY_O",
    "KEY_P",
    "KEY_Q",
    "KEY_R",
    "KEY_S",
    "KEY_T",
    "KEY_U",
    "KEY_V",
    "KEY_W",
    "KEY_X",
    "KEY_Y",
    "KEY_Z",
    "KEY_NUMPAD0",
    "KEY_NUMPAD1",
    "KEY_NUMPAD2",
    "KEY_NUMPAD3",
    "KEY_NUMPAD4",
    "KEY_NUMPAD5",
    "KEY_NUMPAD6",
    "KEY_NUMPAD7",
    "KEY_NUMPAD8",
    "KEY_NUMPAD9"]
