from flask import Flask, request, jsonify, render_template
import os
import requests
from dotenv import load_dotenv
import re

load_dotenv()

app = Flask(__name__)
MAPQUEST_KEY = os.getenv('MAPQUEST_KEY')

class RouteOptimizer:
    def __init__(self):
        self.cache = {}
    
    def get_route_data(self, origin, destination, waypoints=None, avoid_tolls=False, route_type='fastest'):
        """Obtiene datos de ruta de MapQuest"""
        params = {
            'key': MAPQUEST_KEY,
            'from': origin,
            'to': destination,
            'routeType': route_type,
            'unit': 'k',
            'narrativeType': 'text',
            'locale': 'es_MX',
            'fullShape': True,
            'generalize': 0
        }
        
        if avoid_tolls:
            params['tollRoads'] = 'false'
        
        if waypoints:
            for i, wp in enumerate(waypoints, 1):
                params[f'to{i}'] = wp
        
        try:
            response = requests.get(
                'https://www.mapquestapi.com/directions/v2/route',
                params=params,
                timeout=15
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error MapQuest: {str(e)}")
            return None

optimizer = RouteOptimizer()

def validate_coordinates(coord_str):
    """Valida y normaliza coordenadas"""
    if not coord_str or not isinstance(coord_str, str):
        return None
    
    # Acepta formatos: "lat,lon", "lat_lon", "lat, lon"
    coord_str = coord_str.replace('_', ',').replace(' ', '')
    
    try:
        lat, lon = coord_str.split(',')
        lat = float(lat)
        lon = float(lon)
        
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return f"{lat},{lon}"
        return None
    except ValueError:
        return None

@app.route('/')
def index():
    if not MAPQUEST_KEY:
        return render_template('error.html', error="API Key no configurada")
    return render_template('index.html', mapquest_key=MAPQUEST_KEY)

@app.route('/ruta', methods=['POST'])
def calcular_ruta():
    try:
        data = request.get_json()
        
        # Validar y normalizar entradas
        origen = validate_coordinates(data.get('origen'))
        destino = validate_coordinates(data.get('destino'))
        waypoints = [wp for wp in (validate_coordinates(wp) for wp in data.get('waypoints', [])) if wp]
        
        if not origen or not destino:
            return jsonify({'error': 'Se requieren origen y destino válidos'}), 400
        
        # Obtener datos de la ruta
        route_data = optimizer.get_route_data(
            origin=origen,
            destination=destino,
            waypoints=waypoints,
            avoid_tolls=data.get('avoid_tolls', False),
            route_type=data.get('routeType', 'fastest')
        )
        
        if not route_data or route_data.get('info', {}).get('statuscode') != 0:
            error_msg = route_data.get('info', {}).get('messages', ['Error desconocido de MapQuest'])[0]
            return jsonify({'error': error_msg}), 400
        
        route = route_data.get('route', {})
        locations = route.get('locations', [])
        
        if len(locations) < 2:
            return jsonify({'error': 'No se pudieron obtener suficientes ubicaciones'}), 400
        
        return jsonify({
            'directions': [m['narrative'] for m in route['legs'][0]['maneuvers']],
            'distance_km': round(route['distance'], 2),
            'time_minutes': round(route['time'] / 60, 1),
            'fuel_used_gal': round(route.get('fuelUsed', 0), 2),
            'toll_distance_km': round(route.get('tollRoadDistance', 0), 2),
            'shape': route['shape']['shapePoints'],
            'start_lat_lng': [locations[0]['latLng']['lat'], locations[0]['latLng']['lng']],
            'end_lat_lng': [locations[-1]['latLng']['lat'], locations[-1]['latLng']['lng']],
            'optimal_route': [origen] + waypoints + [destino],
            'algorithm_used': 'Optimización básica'
        })

    except Exception as e:
        return jsonify({'error': f'Error interno: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)