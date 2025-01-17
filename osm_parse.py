# Modules
# Elementary modules
from math import radians, cos, sin, asin, sqrt
import copy

# Graph module
import networkx

# Specific modules
import xml.sax  # parse osm file
from pathlib import Path  # manage cached tiles

"""This file parses osm"""
"""
Read directional graph from Open Street Maps osm format
Based on the osm to networkx tool from aflaxman : https://gist.github.com/aflaxman/287370/
Use python3.6
Added : 
- : Python3.6 compatibility
- : Cache for avoiding to download again the same osm tiles
- : distance computation to estimate length of each ways (useful to compute the shortest path)
Copyright (C) 2017 Loic Messal (github : Tofull)"""
# Adapted and modified for traffic simulation

__authors__ = "Loic Messal some parts where modified by Ole Schmidt, Matthias Andres and Jonathan Gärtner"


def haversine(lon1, lat1, lon2, lat2, unit_m=True):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    default unit : km
    """
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of earth in kilometers. Use 3956 for miles
    if unit_m:
        r *= 1000
    return c * r


def download_osm(left, bottom, right, top, proxy=False, proxy_host="mnsplusproxy", proxy_port=8080,
                 cache=False, cache_temp_dir="/tmp/tmpOSM/", verbose=True):
    """ Return a filehandle to the downloaded data from osm api."""

    import urllib.request  # To request the web

    if cache:
        # cached tile filename
        cached_tile_filename = "osm_map_{:.8f}_{:.8f}_{:.8f}_{:.8f}.map".format(left, bottom, right, top)

        if verbose:
            print("Cached tile filename :", cached_tile_filename)

        Path(cache_temp_dir).mkdir(parents=True, exist_ok=True)  # Create cache path if not exists

        osm_file = Path(cache_temp_dir + cached_tile_filename).resolve()
        # Replace the relative cache folder path to absolute path

        if osm_file.is_file():
            # download from the cache folder
            if verbose:
                print("Tile loaded from the cache folder.")

            fp = urllib.request.urlopen("file://"+str(osm_file))
            return fp

    if proxy:
        # configure the urllib request with the proxy
        proxy_handler = urllib.request.ProxyHandler({'https': 'https://' + str(proxy_host) + ":" + str(proxy_port),
                                                     'http': 'http://' + str(proxy_host) + ":" + str(proxy_port)})
        opener = urllib.request.build_opener(proxy_handler)
        urllib.request.install_opener(opener)

    request = "http://api.openstreetmap.org/api/0.6/map?bbox=%f,%f,%f,%f" % (left, bottom, right, top)

    if verbose:
        print("Download the tile from osm web api ... in progress")
        print("Request :", request)

    fp = urllib.request.urlopen(request)

    if verbose:
        print("OSM Tile downloaded")

    if cache:
        if verbose:
            print("Write osm tile in the cache")
        content = fp.read()
        with open(osm_file, 'wb') as f:
            f.write(content)

        if osm_file.is_file():
            if verbose:
                print("OSM tile written in the cache")

            fp = urllib.request.urlopen("file://"+str(osm_file))
            # Reload the osm tile from the cache (because fp.read moved the cursor)
            return fp

    return fp


def create_streetnetwork(filename_or_stream, only_roads=True):
    """Read graph in OSM format from file specified by name or by stream object.
    Parameters
    ----------
    filename_or_stream : filename or stream object
    Returns
    -------
    G : Graph
    Examples
    --------
    >>> import networkx as nx
    >>> G=nx.read_osm(nx.download_osm(-122.33,47.60,-122.31,47.61))
    >>> import matplotlib.pyplot as plt
    >>> plt.plot([G.node[n]['lat']for n in G], [G.node[n]['lon'] for n in G], 'o', color='k', labels=True)
    >>> plt.show()
    :param filename_or_stream: input
    :param only_roads: (little ways or highways)
    """
    osm = OSM(filename_or_stream)
    graph = networkx.Graph()

    # Add ways
    for w in osm.ways.values():
        if only_roads and 'highway' not in w.tags:
            continue
        if w.tags["highway"] in ["cicleway", "path", "corridor", "steps", "bridleway", "footway", "bus_guideway",
                                 "raceway", "pedestrian", "service", "sidewalk", "proposed", "construction"]:
            continue

        if 'oneway' in w.tags:
            if w.tags['oneway'] == 'yes':
                # ONLY ONE DIRECTION
                cars = {}
                for i in w.nds:
                    cars[i] = []
                max_v = 50 / 3.6
                if "maxspeed" in w.tags:
                    try:
                        max_v = float(w.tags["maxspeed"]) / 3.6
                    except Exception:
                        pass
                graph.add_path(w.nds, id=w.id, max_v=max_v, cars=cars)  # Length
            else:
                # BOTH DIRECTION
                cars = {}
                for i in w.nds:
                    cars[i] = []
                max_v = 50 / 3.6
                if "maxspeed" in w.tags:
                    try:
                        max_v = float(w.tags["maxspeed"]) / 3.6
                    except Exception:
                        pass
                graph.add_path(w.nds, id=w.id, max_v=max_v, cars=cars)  # Length
                graph.add_path(w.nds[::-1], max_v=max_v, id=w.id, cars=cars)
        else:
            # BOTH DIRECTION
            cars = {}
            for i in w.nds:
                cars[i] = []
            max_v = 50 / 3.6
            if "maxspeed" in w.tags:
                try:
                    max_v = float(w.tags["maxspeed"]) / 3.6
                except Exception:
                    pass
            graph.add_path(w.nds, id=w.id, max_v=max_v, cars=cars)  # Length
            graph.add_path(w.nds[::-1], id=w.id, max_v=max_v, cars=cars)

    # Complete the used nodes' information
    bus_stops = []
    example = {"type": "Feature", "name": "test", "geometry": {"type": "Point", "coordinates": []}}

    for n_id in graph.nodes():
        n = osm.nodes[n_id]
        graph.node[n_id]['lat'] = n.lat
        graph.node[n_id]['lon'] = n.lon
        graph.node[n_id]['id'] = n.id

        if "public_transport" in n.tags:
            if n.tags["public_transport"] == "stop_position" or n.tags["public_transport"] == "stop_position":
                # This could also be the tram but there is mostly also bus traffic
                graph.node[n_id]["bus"] = True
                example["geometry"]["coordinates"] = [n.lon, n.lat]
                if "name" in n.tags:  # Some bus_stops do not have name in this file
                    example["name"] = n.tags["name"]
                else:
                    example["name"] = "unkown"
                bus_stops.append(example)
                example = {"type": "Feature", "name": "test", "geometry": {"type": "Point", "coordinates": []}}

        if "crossing" in n.tags:
            graph.node[n_id]["crossing"] = n.tags["crossing"]

        if "highway" in n.tags and "crossing" not in list(graph.node[n_id].keys()):
            graph.node[n_id]["crossing"] = "True"

    distance_sum = 0
    # Estimate the length of each way
    for u, v, d in graph.edges(data=True):
        distance = haversine(graph.node[u]['lon'], graph.node[u]['lat'], graph.node[v]['lon'], graph.node[v]['lat'],
                             unit_m=True)
        # Give a realistic distance estimation (neither EPSG nor projection nor reference system are specified)
        distance_sum += distance
        graph.add_weighted_edges_from([(u, v, distance)], weight='length')

    return graph, bus_stops


class Node:
    def __init__(self, node_id, lon, lat):
        self.id = node_id
        self.lon = lon
        self.lat = lat
        self.tags = {}

    def __str__(self):
        return "Node (id : %s) lon : %s, lat : %s " % (self.id, self.lon, self.lat)


class Way:
    def __init__(self, way_id, osm):
        self.osm = osm
        self.id = way_id
        self.nds = []
        self.tags = {}

    def split(self, dividers):
        # slice the node-array using this nifty recursive function
        def slice_array(ar, dividers_function2):
            for iteration in range(1, len(ar) - 1):
                if dividers_function2[ar[iteration]] > 1:
                    left = ar[:iteration + 1]
                    right = ar[iteration:]

                    rightsliced = slice_array(right, dividers_function2)

                    return [left]+rightsliced
            return [ar]

        slices = slice_array(self.nds, dividers)

        # create a way object for each node-array slice
        ret = []
        i = 0
        for slice_of_slices in slices:
            littleway = copy.copy(self)
            littleway.id += "-%d" % i
            littleway.nds = slice_of_slices
            ret.append(littleway)
            i += 1

        return ret


class OSM:
    def __init__(self, filename_or_stream):
        """ File can be either a filename or stream/file object."""
        nodes = {}
        ways = {}

        superself = self

        class OSMHandler(xml.sax.ContentHandler):
            @classmethod
            def setDocumentLocator(cls, loc):
                pass

            @classmethod
            def startDocument(cls):
                pass

            @classmethod
            def endDocument(cls):
                pass

            @classmethod
            def startElement(cls, name, attrs):
                if name == 'node':
                    cls.currElem = Node(attrs['id'], float(attrs['lon']), float(attrs['lat']))
                elif name == 'way':
                    cls.currElem = Way(attrs['id'], superself)
                elif name == 'tag':
                    cls.currElem.tags[attrs['k']] = attrs['v']
                elif name == 'nd':
                    cls.currElem.nds.append(attrs['ref'])

            @classmethod
            def endElement(cls, name):
                if name == 'node':
                    nodes[cls.currElem.id] = cls.currElem
                elif name == 'way':
                    ways[cls.currElem.id] = cls.currElem

            @classmethod
            def characters(cls, chars):
                pass

        xml.sax.parse(filename_or_stream, OSMHandler)

        self.nodes = nodes
        self.ways = ways

        # counts times each node is used
        node_histogram = dict.fromkeys(self.nodes.keys(), 0)
        for way in self.ways.values():
            if len(way.nds) < 2:  # if a way has only one node, delete it out of the osm collection
                del self.ways[way.id]
            else:
                for node in way.nds:
                    node_histogram[node] += 1

        # use that histogram to split all ways, replacing the member set of ways
        new_ways = {}
        for way_id, way in self.ways.items():
            split_ways = way.split(node_histogram)
            for split_way in split_ways:
                new_ways[split_way.id] = split_way
        self.ways = new_ways
