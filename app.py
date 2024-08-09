from flask import Flask, render_template, request, redirect, url_for
import geopandas as gpd
import pandas as pd
import networkx as nx
from shapely.geometry import Point, LineString
import folium

app = Flask(__name__)

# Update these paths to the correct locations on your Linux system
fire_stations_path = '/home/victor/mappweb/DATA/excelsheets/FireStations.xlsx'
health_facilities_path = '/home/victor/mappweb/DATA/excelsheets/HealthFacilities.xlsx'
redcross_stations_path = '/home/victor/mappweb/DATA/excelsheets/RedCross.xlsx'
roads_shapefile_path = '/home/victor/mappweb/DATA/Shapefiles/ROADS.shp'
study_area_shapefile_path = '/home/victor/mappweb/DATA/Shapefiles/Kilimani.shp'

# Load data
def load_facilities(path):
    df = pd.read_excel(path)
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.longitude, df.latitude))

fire_stations_gdf = load_facilities(fire_stations_path)
health_facilities_gdf = load_facilities(health_facilities_path)
redcross_stations_gdf = load_facilities(redcross_stations_path)

def create_graph_from_shapefile(shapefile_path):
    gdf = gpd.read_file(shapefile_path)
    G = nx.Graph()
    for _, row in gdf.iterrows():
        line = row['geometry']
        if isinstance(line, LineString):
            coords = list(line.coords)
            for i in range(len(coords) - 1):
                u, v = coords[i], coords[i + 1]
                if not G.has_edge(u, v):
                    G.add_edge(u, v, length=line.length)
                    G.nodes[u]['coords'] = u
                    G.nodes[v]['coords'] = v
    return G

G = create_graph_from_shapefile(roads_shapefile_path)

def nearest_node(graph, point):
    min_dist = float('inf')
    nearest_node = None
    for node in graph.nodes:
        node_point = Point(node)
        dist = point.distance(node_point)
        if dist < min_dist:
            min_dist = dist
            nearest_node = node
    return nearest_node

def find_nearest_facility(location, facilities_gdf):
    nearest_distance = float('inf')
    nearest_facility = None
    for _, facility in facilities_gdf.iterrows():
        facility_point = facility.geometry
        distance = location.distance(facility_point)
        if distance < nearest_distance:
            nearest_distance = distance
            nearest_facility = facility
    return nearest_facility, nearest_distance

def calculate_path(graph, point1, point2):
    node1 = nearest_node(graph, point1)
    node2 = nearest_node(graph, point2)
    if node1 in graph.nodes and node2 in graph.nodes:
        try:
            path = nx.shortest_path(graph, source=node1, target=node2, weight='length')
            distance = nx.shortest_path_length(graph, source=node1, target=node2, weight='length')
            return path, distance
        except nx.NetworkXNoPath:
            return None, "A direct path from the specified location to the selected facility could not be determined."
    return None, None

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        facility_type = request.form['facility']
        event_location = Point(36.7805, -1.2920)
        
        if facility_type == 'Fire Station':
            nearest_facility, distance = find_nearest_facility(event_location, fire_stations_gdf)
            color = 'red'
            label = 'Fire Station'
        elif facility_type == 'Health Facility':
            nearest_facility, distance = find_nearest_facility(event_location, health_facilities_gdf)
            color = 'blue'
            label = 'Health Facility'
        elif facility_type == 'Red Cross':
            nearest_facility, distance = find_nearest_facility(event_location, redcross_stations_gdf)
            color = 'green'
            label = 'Red Cross'
        
        path, path_error = calculate_path(G, event_location, nearest_facility.geometry)
        
        # Create map
        m = folium.Map(location=[event_location.y, event_location.x], zoom_start=15)
        
        # Add study area as a folium feature
        study_area_gdf = gpd.read_file(study_area_shapefile_path)
        for _, row in study_area_gdf.iterrows():
            folium.GeoJson(
                row['geometry'],
                style_function=lambda x: {'color': 'black', 'fillOpacity': 0.0, 'weight': 2}
            ).add_to(m)
        
        if path:
            path_coords = [G.nodes[node]['coords'] for node in path]
            folium.PolyLine(locations=[(y, x) for x, y in path_coords], color=color, weight=5, opacity=0.5).add_to(m)
        
        # Plot facility
        folium.Marker(
            location=[nearest_facility.geometry.y, nearest_facility.geometry.x],
            icon=folium.Icon(color=color, icon='info-sign'),
            popup=nearest_facility.title
        ).add_to(m)
        
        # Plot event location
        folium.Marker(
            location=[event_location.y, event_location.x],
            icon=folium.Icon(color='black', icon='info-sign'),
            popup='Event Location'
        ).add_to(m)
        
        # Save map to an HTML file
        map_file = 'static/map.html'
        m.save(map_file)
        
        # Save results to CSV
        if nearest_facility is not None:
            distance_data = {
                'Facility': [label],
                'Distance (meters)': [distance * 1000]  # Convert km to meters
            }
            distance_df = pd.DataFrame(distance_data)
            distance_df.to_csv('static/distances_to_nearest_facility.csv', index=False)

        return redirect(url_for('map'))
    
    return render_template('index.html')

@app.route('/map')
def map():
    return render_template('map.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
    
