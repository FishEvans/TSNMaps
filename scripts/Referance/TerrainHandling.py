import random, hjson, os, sbs, copy, math
import sbs_tools as tools
import simulation
import tsn_databases, Objects
from Terrain import TerrainTypes
from Objects import SpaceObjects, JumpPoints, OtherObjects, NPCShips
from NPC_Ships import fleetOrders, AI_Commanders
from collections import OrderedDict


blackholeIDs = []
planetIDs = []
asteroidIDs = []
nebulaIDs = []
minefields = {}
navProxyIDs = []
minefieldAreaDefs = []
minefieldAreaIDs = []
navFieldAreaDefs = []
navFieldAreaIDs = []
currentSystem = ""
systemAlignment = ""


def systemlist():
    path = os.getcwd() + "\data\missions\TSN Cosmos\Terrain\Star-Systems\\"
    systems = set()
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".json"): #changed from .dat
                save_name = os.path.splitext(file)[0]
                systems.add(save_name)
    return systems


def compileSystemInformation():
    allsystems = dict()
    sortedsystems = {}
    for systemname in systemlist():
        with open(tools.find(f"{systemname}.json", os.getcwd() + "\data\missions\TSN Cosmos\Terrain\Star-Systems\\"), "r") as systemdatafile:
            systemdata = hjson.load(systemdatafile)
            alignment = systemdata.get("systemalignment")
            mapCoord = systemdata.get("systemMapCoord")
        allsystems.update({systemname: [mapCoord, alignment]})
    if len(allsystems.keys()) > 0:
        sortedsystems = OrderedDict(sorted(allsystems.items()))
    return sortedsystems


allsystems = compileSystemInformation()


def generateInfluenceCenters(start, end, rng, count, spread):
    centers = []
    for _ in range(count):
        t = rng.random()
        x = start[0] + t * (end[0] - start[0])
        z = start[2] + t * (end[2] - start[2])

        x += rng.uniform(-spread, spread)
        z += rng.uniform(-spread, spread)

        centers.append((x, z))
    return centers


def falloff(dist, radius):
    if dist >= radius:
        return 0.0
    x = 1 - (dist / radius)
    return x * x  # quadratic falloff


def generateLineCoords(
    start,
    end,
    count,
    radius,
    seed=None,
    y_range=(-600, 600),
    clumps=(),
    voids=(),
):
    rng = random.Random(seed)
    coords = []

    dx = end[0] - start[0]
    dz = end[2] - start[2]
    length = math.hypot(dx, dz)

    if length == 0:
        return []

    ux = dx / length
    uz = dz / length

    for _ in range(count):
        # --- position along spine (uniform, no tapering) ---
        t = rng.random()
        cx = start[0] + t * dx
        cz = start[2] + t * dz

        # --- radial distance (Gaussian falloff, no rejection) ---
        u = max(1e-6, rng.random())
        d = radius * math.sqrt(-math.log(u))

        angle = rng.uniform(0, 2 * math.pi)
        ox = math.cos(angle) * d
        oz = math.sin(angle) * d

        x = cx + ox
        z = cz + oz
        y = rng.uniform(*y_range)

        # --- clumps / voids as smooth offsets ---
        density_bias = 0.0

        for cx_, cz_, r, s in clumps:
            dist = math.hypot(x - cx_, z - cz_)
            if dist < r:
                density_bias += (1 - dist / r) ** 2 * s

        for vx_, vz_, r, s in voids:
            dist = math.hypot(x - vx_, z - vz_)
            if dist < r:
                density_bias -= (1 - dist / r) ** 2 * s

        # Instead of rejecting, we gently push points
        if density_bias != 0:
            push = density_bias * radius * 0.15
            x += rng.uniform(-push, push)
            z += rng.uniform(-push, push)

        coords.append((x, y, z))

    return coords


def generateArcCoords(center, radius, start_angle, end_angle, density, scatter, seed=None, y_range=(-600, 600)):
    """
    Generates coordinates for an arc-shaped asteroid field with thicker middle scatter.

    center: (cx, cy, cz) - arc center point (Y here is ignored for arc placement)
    radius: distance from center to arc path
    start_angle: in degrees
    end_angle: in degrees
    density: number of asteroids
    scatter: max random deviation from arc path (in X/Z plane)
    y_range: tuple (min_y, max_y) for vertical randomization
    """
    if seed is not None:
        random.seed(seed)

    coords = []
    cx, _, cz = center

    for _ in range(density):
        # Random interpolation factor from 0 to 1 along the arc
        t = random.random()

        # Convert to angle within arc
        angle_deg = start_angle + t * (end_angle - start_angle)
        angle_rad = math.radians(angle_deg)

        # Base position on the arc
        x = cx + radius * math.cos(angle_rad)
        z = cz + radius * math.sin(angle_rad)

        # Scatter factor thicker in the middle
        scatter_factor = math.sin(t * math.pi)  # Peaks at t=0.5
        local_scatter = scatter * scatter_factor

        # Apply scatter in X/Z plane
        x += random.uniform(-local_scatter, local_scatter)
        z += random.uniform(-local_scatter, local_scatter)

        # Random Y within range
        y = random.uniform(*y_range)

        coords.append((int(x), y, int(z)))

    return coords

"""def generateLineCoords(seed, start, end, density, scatter, height):
    random.seed(seed)
    coordList = []
    if start[0] == end[0]:
        coordList.append((start[0], start[1], start[2]))
    else:
        gradient = (end[2] - start[2]) / (end[0] - start[0])
        constant = start[2] - (gradient * start[0])
        for d in range(density):
            try:
                xcoord = random.randint(int(start[0]), int(end[0]))
            except:
                xcoord = random.randint(int(end[0]), int(start[0]))
            zcoord = (gradient * xcoord) + constant
            changex = random.choice([random.randint(0, int(scatter)), 0 - (random.randint(0, int(scatter)))])
            changez = random.choice([random.randint(0, int(scatter)), 0 - (random.randint(0, int(scatter)))])
            ycoord = random.uniform(-600, 600)
            finalcoordinate = (int(xcoord + changex), ycoord, int(zcoord + changez))
            coordList.append(finalcoordinate)
    return coordList"""


"""def generatePointCoords(seed, coordinate, density, scatter):
    random.seed(seed)
    coordList = []
    for d in range(density):
        changex = random.choice([random.randint(0, int(scatter)), 0 - (random.randint(0, int(scatter)))])
        changez = random.choice([random.randint(0, int(scatter)), 0 - (random.randint(0, int(scatter)))])
        ycoord = random.uniform(-600, 600)
        finalcoordinate = (int(coordinate[0] + changex), ycoord, int(coordinate[2] + changez))
        coordList.append(finalcoordinate)
    return coordList"""


def generatePointCoords(coordinate, density, scatter, seed=None, y_range=(-600, 600)):
    """
    Generates random coordinates scattered around a single point.

    seed: random seed for reproducibility
    coordinate: (x, y, z) center point (y is ignored for scatter)
    density: number of points to generate
    scatter: max offset in X and Z from center
    y_range: tuple (min_y, max_y) vertical variation
    """
    if seed is not None:
        random.seed(seed)
    coords = []

    for _ in range(density):
        # Random scatter in X/Z directly from -scatter to +scatter
        dx = random.randint(-scatter, scatter)
        dz = random.randint(-scatter, scatter)

        # Random Y height within range
        y = random.uniform(*y_range)

        coords.append((int(coordinate[0] + dx), y, int(coordinate[2] + dz)))

    return coords


#checked and improved code
def loaddata(systemname):
    with open(tools.find(f"{systemname}.json", os.getcwd()+ "\data\missions\TSN Cosmos\Terrain\Star-Systems\\") , "r") as systemdatafile:
        systemdata = hjson.load(systemdatafile)
        terrainlist = systemdata.get("terrain")
        objectlist = systemdata.get("objects")
        sensorlist = systemdata.get("sensor_relay")
        trafficlist = systemdata.get("traffic")
        alignment = systemdata.get("systemalignment")
    return terrainlist, objectlist, sensorlist, trafficlist, alignment


def spawnTerrain(sim, system):
    global currentSystem, systemAlignment
    # create all the terrain
    terrain, objects, sensors, traffic, alignment = loaddata(system)
    systemAlignment = alignment
    generateTerrain(sim, terrain)
    systemObjectList = setupObjects(system, objects)
    for object in systemObjectList:
        object.SpawnObject(sim)
        if isinstance(object, Objects.Platforms.Platform) or isinstance(object, Objects.Platforms.FighterPlatform):
            NewCommander = AI_Commanders.AIPlatformCommander(object.ObjectID, object)
            AI_Commanders.commanders.update({id(NewCommander): NewCommander})
    sensorRelayList = setupSensorNet(sensors)
    for sensor in sensorRelayList:
        sensor.SpawnObject(sim)
    #generateTraffic(sim, traffic, alignment, objects)
    currentSystem = system
    refreshTerrainNavAreas(sim)


def registerMinefieldArea(data):
    if data.get("type") in ["hidden_minefield", "minefield"]:
        minefieldAreaDefs.append(data.copy())


def registerNavFieldArea(data):
    if data.get("type") == "nav_field":
        navFieldAreaDefs.append(data.copy())


def clearMinefieldNavAreas(sim):
    global minefieldAreaIDs
    for navareaID in minefieldAreaIDs:
        try:
            sim.delete_navpoint_by_id(navareaID)
        except:
            pass
    minefieldAreaIDs = []


def clearNavFieldAreas(sim):
    global navFieldAreaIDs
    for navareaID in navFieldAreaIDs:
        try:
            sim.delete_navpoint_by_id(navareaID)
        except:
            pass
    navFieldAreaIDs = []


def addMinefieldNavArea(sim, data):
    global minefieldAreaIDs
    coordinate = data.get("coordinate")
    width = data.get("width", 0)
    height = data.get("height", 0)
    xneg = coordinate[0] - width
    yneg = coordinate[2] - height
    xpos = coordinate[0] + width
    ypos = coordinate[2] + height

    if data.get("type") == "hidden_minefield":
        for GM in SpaceObjects.activeGameMasters.keys():
            newArea = sim.add_navarea(xneg, yneg, xpos, yneg, xneg, ypos, xpos, ypos, "Hidden Minefield", "#ff0000BF")
            navarea = sim.get_navpoint_by_id(newArea)
            navarea.visibleToShip = GM
            minefieldAreaIDs.append(newArea)
    elif data.get("type") == "minefield":
        newArea = sim.add_navarea(xneg, yneg, xpos, yneg, xneg, ypos, xpos, ypos, "Minefield", "#ff0000BF")
        navarea = sim.get_navpoint_by_id(newArea)
        navarea.visibleToSide = "Allied"
        minefieldAreaIDs.append(newArea)
        for GM in SpaceObjects.activeGameMasters.keys():
            extraArea = sim.add_navarea(xneg, yneg, xpos, yneg, xneg, ypos, xpos, ypos, "Minefield", "#ff0000BF")
            navarea = sim.get_navpoint_by_id(extraArea)
            navarea.visibleToShip = GM
            minefieldAreaIDs.append(extraArea)


def addNavFieldArea(sim, data):
    global navFieldAreaIDs
    coordinate = data.get("coordinate")
    width = data.get("width", 0)
    height = data.get("height", 0)
    xneg = coordinate[0] - width
    yneg = coordinate[2] - height
    xpos = coordinate[0] + width
    ypos = coordinate[2] + height
    text = data.get("text", "Area")
    colour = data.get("colour", "#ffffff80")

    newArea = sim.add_navarea(xneg, yneg, xpos, yneg, xneg, ypos, xpos, ypos, text, colour)
    navarea = sim.get_navpoint_by_id(newArea)
    navarea.visibleToSide = "Allied"
    navFieldAreaIDs.append(newArea)
    for GM in SpaceObjects.activeGameMasters.keys():
        extraArea = sim.add_navarea(xneg, yneg, xpos, yneg, xneg, ypos, xpos, ypos, text, colour)
        navarea = sim.get_navpoint_by_id(extraArea)
        navarea.visibleToShip = GM
        navFieldAreaIDs.append(extraArea)


def refreshMinefieldNavAreas(sim):
    clearMinefieldNavAreas(sim)
    for data in minefieldAreaDefs:
        addMinefieldNavArea(sim, data)


def refreshNavFieldAreas(sim):
    clearNavFieldAreas(sim)
    for data in navFieldAreaDefs:
        addNavFieldArea(sim, data)


def refreshTerrainNavAreas(sim):
    refreshMinefieldNavAreas(sim)
    refreshNavFieldAreas(sim)


def generateTerrain(sim, terrainlist):
    #create the asteroids, nebula, minefields and blackholes in the system
    for id, data in terrainlist.items():
        if data.get("type") == "blackhole":
            blackhole_kwargs = {
                "size": data.get("size"),
                "strength": data.get("strength"),
                "turbulence_strength": data.get("turbulence_strength"),
                "collision_damage": data.get("collision_damage"),
            }
            gravity_radius = data.get("gravity_radius")
            if gravity_radius is None:
                gravity_radius = data.get("GravityRadius")
            if gravity_radius is None:
                gravity_radius = data.get("GravitRadius")
            if gravity_radius is not None:
                blackhole_kwargs["gravity_radius"] = gravity_radius
            newBlackhole = TerrainTypes.AddBlackHole(
                sim,
                data.get("name"),
                data.get("coordinate"),
                **blackhole_kwargs
            )
            blackholeIDs.append(newBlackhole)
        elif data.get("type") in ["hidden_minefield", "minefield"]:
            registerMinefieldArea(data)
            minefield = TerrainTypes.HiddenMinefield(sim, data.get("coordinate"), data.get("height"), data.get("width"), data.get("density"))
            minefields.update({minefield.ID: minefield})
        elif data.get("type") == "nav_field":
            registerNavFieldArea(data)
        elif data.get("type") == "asteroid_resource":
            coordinates = generatePointCoords(data.get("coordinate"), int(data.get("density")), int(data.get("scatter")))
            for coordinate in coordinates:
                asteroidTypeList = data.get("composition")
                choiceList = []
                for asteroidType in asteroidTypeList:
                    choiceList += tsn_databases.terrainDatabase.get(asteroidType)
                ast = random.choice(choiceList)
                newAsteroid = TerrainTypes.AddAsteroid(sim, ast, coordinate)
                asteroidIDs.append(newAsteroid)
        elif data.get("type") == "debris_field":
            coordinates = generatePointCoords(data.get("coordinate"), int(data.get("density")), int(data.get("scatter")))
            for coordinate in coordinates:
                newObject = OtherObjects.Debris(position=coordinate)
                newObject.SpawnObject(sim)
                del(newObject.Timer)
        elif data.get("type") == "planet":
            planetClass = data.get("class") or data.get("name") or "EarthLike"
            newPlanet = TerrainTypes.AddPlanet(
                sim,
                data.get("name"),
                data.get("coordinate"),
                planetClass=planetClass,
                description=data.get("description", "")
            )
            newNavProxy = sim.add_navproxy(newPlanet, data.get("name"), planetClass, "gray")
            navProxyIDs.append(newNavProxy)
            planetIDs.append(newPlanet)
        else:
            coordinates = generateLineCoords(data.get("start"), data.get("end"), int(data.get("density")), int(data.get("scatter")), seed=data.get("seed"))
            if data.get("type") == "asteroids":
                choiceList = []
                for coordinate in coordinates:
                    asteroidTypeList = data.get("composition")
                    for asteroidType in asteroidTypeList:
                        choiceList += tsn_databases.terrainDatabase.get(asteroidType)
                    if choiceList:
                        ast = random.choice(choiceList)
                    else:
                        ast = random.choice(tsn_databases.terrainDatabase.get("Ast. Std Rand"))
                    newAsteroid = TerrainTypes.AddAsteroid(sim, ast, coordinate)
                    asteroidIDs.append(newAsteroid)
            elif data.get("type") == "nebulas":
                for coordinate in coordinates:
                    newNebula = TerrainTypes.AddNebula(sim, "nebula", coordinate)
                    nebulaIDs.append(newNebula)


def setupObjects(system, objects):
    #create the stations and jump points in the system
    objectList = []
    waypoints = {}
    for name, data in objects.items():
        if data.get("type") == "station":
            newObject = Objects.Stations.setupStation(name, data)
        elif data.get("type") == "jumppoint" or data.get("type") == "jumpnode":
            behav = f"behav_{data.get('type')}"
            newObject = JumpPoints.JumpPoint(name, behav, "invisible", position=data.get("coordinate"), info=data)
        elif data.get("type") == "platform":
            behav = "behav_npcship"
            hull = data.get("hull")
            if "fighter" in hull:
                newObject = Objects.Platforms.FighterPlatform(name, behav, hull, position=data.get("coordinate"), info=data)
            else:
                newObject = Objects.Platforms.Platform(name, behav, hull, position=data.get("coordinate"), info=data)
        else:
            newObject = None
        if newObject:
            objectList.append(newObject)
            coord = data.get("coordinate")
            actCoord = coord[0], coord[1], coord[2]
            waypoints.update({name: actCoord})
        if name == "Course":
            courseType = data.get("type")
            courseCent = data.get("coordinate")
            courseList = setupCourse(courseType, courseCent)
            objectList.extend(courseList)
    #tsn_databases.waypointDatabase.update({system: waypoints})
    return objectList


def setupSensorNet(sensors):
    sensorList = []
    for sensor, sensorData in sensors.items():

        name = sensor
        coordinate = sensorData.get("coordinate")
        type = sensorData.get("type", None)
        if type == "Warning Buoy":
            newObject = OtherObjects.WarningBuoy(position=coordinate)
            newObject.message = sensorData.get("broadcast", "Keep Clear")
            newObject.broadcastRange = sensorData.get("range", 8000)
            newObject.broadcastPing = sensorData.get("ping", 2)
            newObject.ObjectName = name
        else:
            newObject = OtherObjects.SensorRelay(name, position=coordinate)
        if sensorData.get("description"):
            newObject.ObjectDescription = sensorData.get("description")
        sensorList.append(newObject)
    return sensorList


def setupCourse(type, coord):
    with open(tools.find(f"{type}.json", os.getcwd() + "\data\missions\TSN Cosmos\Objects\CheckPointTracks\\"), "r") as checkpointdatafile:
        checkpointList = []
        checkpointdata = hjson.load(checkpointdatafile)
        for checkpoint, data in checkpointdata.items():
            coordinate = data.get("coordinate")
            position = [coordinate[0] + coord[0], coordinate[1] + coord[1], coordinate[2] + coord[2]]
            newObject = Objects.OtherObjects.CheckPoint(checkpoint, position=position, angle=data.get("angle"))
            checkpointList.append(newObject)
    return checkpointList


def generateTraffic(sim, trafficData, systemAlignment, systemObjects):
    stationList = []
    for object, objectdata in systemObjects.items():
        if objectdata.get("type") == "station" and systemAlignment in objectdata.get("sides") and objectdata.get("hideonmap") != True:
            stationList.append(object)
    for traffic, quantity in trafficData.items():
        match quantity:
            case "light":
                elementNo = random.randint(1, 3)
            case "medium":
                elementNo = random.randint(3, 6)
            case "heavy":
                elementNo = random.randint(5, 10)
            case int():
                if quantity > 20: #cap the value at 20
                    elementNo = 20
                else:
                    elementNo = quantity
            case _:
                elementNo = random.randint(3, 5)

        # configure a start location
        # configure destinations
        for no in range(elementNo):
            match traffic:
                case "civilian":
                    elementType = ["transport_ship", "luxury_liner"]
                    elementOrders = copy.deepcopy(fleetOrders.civilianOrders)
                    stationstart = random.choice(stationList)
                    stationdata = systemObjects.get(stationstart)
                    position = tuple(stationdata.get("coordinate"))

                    destinations = set()
                    destinations.add(stationstart)
                    for x in range(random.randint(2, 5)):
                        destinations.add(random.choice(stationList))
                    params = elementOrders.get("Parameters")
                    params.update({"Locations": list(destinations)})
                case "commercial":
                    elementType = ["transport_ship", "cargo_ship"]
                    elementOrders = copy.deepcopy(fleetOrders.civilianOrders)
                    stationstart = random.choice(stationList)
                    stationdata = systemObjects.get(stationstart)
                    position = tuple(stationdata.get("coordinate"))

                    destinations = set()
                    destinations.add(stationstart)
                    for x in range(random.randint(2, 5)):
                        destinations.add(random.choice(stationList))
                    params = elementOrders.get("Parameters")
                    params.update({"Locations": list(destinations)})
                case "security":
                    elementType = ["usfp_patrol_boat", "tsn_destroyer"]
                    elementOrders = copy.deepcopy(fleetOrders.patrolOrders)
                    stationstart = random.choice(stationList)
                    stationdata = systemObjects.get(stationstart)
                    position = tuple(stationdata.get("coordinate"))

                    destinations = set()
                    destinations.add(stationstart)
                    for x in range(random.randint(2, 5)):
                        destinations.add(random.choice(stationList))
                    params = elementOrders.get("Parameters")
                    params.update({"Locations": list(destinations)})
                case _:
                    elementType = ["cargo_ship"]
                    elementOrders = copy.deepcopy(fleetOrders.civilianOrders)
                    stationstart = random.choice(stationList)
                    stationdata = systemObjects.get(stationstart)
                    position = tuple(stationdata.get("coordinate"))

                    destinations = set()
                    destinations.add(stationstart)
                    for x in range(random.randint(2, 5)):
                        destinations.add(random.choice(stationList))
                    params = elementOrders.get("Parameters")
                    params.update({"Locations": list(destinations)})

            hull = random.choice(elementType)
            trafficShip = NPCShips.NPCShip(systemAlignment, "behav_npcship", hull, position=position)
            trafficShip.SpawnObject(sim)

            NewFleetCommander = AI_Commanders.AISoloCommander(trafficShip, {trafficShip.ObjectID: trafficShip}, 1, Orders=elementOrders)
            AI_Commanders.commanders.update({id(NewFleetCommander): NewFleetCommander})
            for GMObj in SpaceObjects.activeGameMasters.values():
                GMObj.addtoScanSources(trafficShip.ObjectID)


def clearTerrain():
    # SpaceObjects.activeStations key/value dictionary of stations: ID, Object
    # SpaceObjects.activeJumpPoints key/value dictionary of jump points: ID, Object
    # SpaceObjects.activeObjects (eg. Lifepods, Marine pods, cargo pods etc) key/value dictionary of Objects: ID, Object
    # SpaceObjects.activeNPCs key/value dictionary of NPCs: ID, Object
    # asteroidIDs
    # nebulaIDs
    # minefields - key/value dictionary of minefields: ID, Object
    global asteroidIDs, nebulaIDs, blackholeIDs, minefields, navProxyIDs, minefieldAreaDefs, navFieldAreaDefs
    for asteroid in asteroidIDs:
        sbs.delete_object(asteroid)
    for nebula in nebulaIDs:
        sbs.delete_object(nebula)
    for blackhole in blackholeIDs:
        sbs.delete_object(blackhole)
    asteroidIDs = []
    blackholeIDs = []
    nebulaIDs = []
    deleteList = []
    allObjects = SpaceObjects.activeStations | SpaceObjects.activeObjects | SpaceObjects.activeNPCs | SpaceObjects.activeJumpPoints | SpaceObjects.activePlatforms
    for activeObjID in allObjects.keys():
        if activeObjID in SpaceObjects.jumpNPCs.keys():
            pass
        else:
            deleteList.append(activeObjID)
    for object in deleteList:
        del allObjects[object]
        sbs.delete_object(object)
    for navProxyID in navProxyIDs:
        simulation.simul.delete_navproxy_by_id(navProxyID)
    navProxyIDs = []
    minefieldAreaDefs = []
    navFieldAreaDefs = []
    clearMinefieldNavAreas(simulation.simul)
    clearNavFieldAreas(simulation.simul)
    SpaceObjects.activeStations = {}
    SpaceObjects.activeJumpPoints = {}
    SpaceObjects.activeObjects = {}
    SpaceObjects.activeNPCs = {}
    SpaceObjects.activePlatforms = {}

    deleteList = []
    for minefieldID in minefields.keys():
        deleteList.append(minefields.get(minefieldID))
    for minefield in deleteList:
        del minefield
    minefields = {}


def asteroidDamage(damage_event, asteroidID):
    asteroid = simulation.simul.get_space_object(asteroidID)
    asteroidData = asteroid.data_set
    curDamage = asteroidData.get("curDamage", 0)
    maxDamage = asteroidData.get("maxDamage", 0)
    if curDamage < maxDamage:
        asteroidData.set("curDamage", curDamage + damage_event.sub_float)
    elif curDamage > maxDamage:
        density = asteroidData.get("materialDensity", 0)
        for x in range(density):
            type = asteroidData.get("composition", x)
            if type:
                scatterx = random.randint(-10, 10)
                scattery = random.randint(-10, 10)
                scatterz = random.randint(-10, 10)
                coordinate = (asteroid.pos.x + scatterx, asteroid.pos.y + scattery, asteroid.pos.z + scatterz)
                newObj = OtherObjects.AsteroidFragment(type, position=coordinate)
                newObj.SpawnObject(simulation.simul)
                newObj.Object.cur_speed = 0.1
                quaternion = OtherObjects.random_quaternion()
                newObj.Object.rot_quat.w = quaternion[0]
                newObj.Object.rot_quat.x = quaternion[1]
                newObj.Object.rot_quat.y = quaternion[2]
                newObj.Object.rot_quat.z = quaternion[3]
        sbs.delete_object(asteroidID)
        asteroidIDs.remove(asteroidID)



