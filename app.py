from flask import Flask, request, jsonify, render_template
import os
import requests
from dotenv import load_dotenv
import re
import socket
from datetime import datetime

load_dotenv()

app = Flask(__name__)
MAPQUEST_KEY = os.getenv('MAPQUEST_KEY')

class RouteCalculator:
    def __init__(self):
        self.session = requests.Session()
        self.timeout = 20
        self.max_retries = 3

    def validate_location(self, location):
        """Valida si la ubicación es coordenada o dirección"""
        coord_pattern = r'^-?\d{1,3}[\.\,]\d+\s*[\,\.]\s*-?\d{1,3}[\.\,]\d+$'
        
        if re.match(coord_pattern, location.replace(' ', '')):
            normalized = location.replace(' ', '').replace('.', ',').replace(',,', ',')
            try:
                lat, lon = normalized.split(',')[:2]
                lat = float(lat)
                lon = float(lon)
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return {'valid': True, 'type': 'coordinate', 'normalized': f"{lat},{lon}"}
            except:
                pass
        
        if len(location) >= 3:
            return {'valid': True, 'type': 'address'}
        
        return {'valid': False, 'error': 'Formato inválido'}

    def get_route(self, origin, destination, waypoints=None, vehicle='automovil', avoid_tolls=False):
        """Obtiene ruta de MapQuest con manejo robusto de errores"""
        params = {
            'key': MAPQUEST_KEY,
            'routeType': 'fastest',
            'unit': 'k',
            'narrativeType': 'text',
            'locale': 'es_MX',
            'fullShape': True,
            'generalize': 0,
            'from': origin,
            'to': destination
        }

        if avoid_tolls:
            params['tollRoads'] = 'false'

        if waypoints:
            for i, wp in enumerate(waypoints, 1):
                params[f'to{i}'] = wp

        for attempt in range(self.max_retries):
            try:
                response = self.session.get(
                    'https://www.mapquestapi.com/directions/v2/route',
                    params=params,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('info', {}).get('statuscode') == 0:
                        return self._process_route_data(data, vehicle)
                    
                    error_msg = data.get('info', {}).get('messages', ['Error desconocido'])[0]
                    return {'error': f'MapQuest: {error_msg}'}
                
                return {'error': f'Error HTTP {response.status_code}'}

            except requests.exceptions.Timeout:
                if attempt == self.max_retries - 1:
                    return {'error': 'Timeout: El servidor no respondió a tiempo'}
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    return {'error': f'Error de conexión: {str(e)}'}
            except Exception as e:
                if attempt == self.max_retries - 1:
                    return {'error': f'Error interno: {str(e)}'}

        return {'error': 'No se pudo calcular la ruta después de varios intentos'}

    def _process_route_data(self, data, vehicle):
        """Procesa los datos de la ruta para incluir cálculo de gasolina"""
        route = data['route']
        distance = route['distance']  # km
        time = route['time'] / 60  # minutos
        
        efficiency = {
            'automovil': 12,
            'motocicleta': 25,
            'caminando': 0
        }.get(vehicle, 12)
        
        fuel_used = distance / efficiency if efficiency > 0 else 0
        fuel_cost = fuel_used * 24.50
        
        return {
            'distance': round(distance, 2),
            'time': round(time, 1),
            'fuel_used': round(fuel_used, 2),
            'fuel_cost': round(fuel_cost, 2),
            'directions': [m['narrative'] for m in route['legs'][0]['maneuvers']],
            'geometry': route['shape']['shapePoints'],  # Cambiado a 'geometry'
            'start_coords': [
                route['locations'][0]['latLng']['lat'],
                route['locations'][0]['latLng']['lng']
            ],
            'end_coords': [
                route['locations'][-1]['latLng']['lat'],
                route['locations'][-1]['latLng']['lng']
            ],
            'toll_distance': route.get('tollRoadDistance', 0),
            'toll_cost': round(route.get('tollRoadDistance', 0) * 5, 2),
            'timestamp': datetime.now().strftime('%d/%m/%Y %H:%M')
        }

route_calculator = RouteCalculator()

@app.route('/')
def index():
    if not MAPQUEST_KEY:
        return render_template('error.html', error="API Key no configurada")
    return render_template('index.html')

@app.route('/validate', methods=['POST'])
def validate():
    data = request.get_json()
    location = data.get('location', '').strip()
    return jsonify(route_calculator.validate_location(location))

@app.route('/calculate', methods=['POST'])
def calculate():
    data = request.get_json()
    
    origin = route_calculator.validate_location(data.get('origin', ''))
    dest = route_calculator.validate_location(data.get('destination', ''))
    
    if not origin['valid'] or not dest['valid']:
        return jsonify({'error': 'Origen o destino inválidos'}), 400
    
    waypoints = []
    for wp in data.get('waypoints', []):
        validated = route_calculator.validate_location(wp)
        if validated['valid']:
            waypoints.append(validated.get('normalized', wp))
    
    result = route_calculator.get_route(
        origin=origin.get('normalized', data.get('origin')),
        destination=dest.get('normalized', data.get('destination')),
        waypoints=waypoints,
        vehicle=data.get('vehicle', 'automovil'),
        avoid_tolls=data.get('avoid_tolls', False)
    )
    
    if 'error' in result:
        return jsonify({'error': result['error']}), 400
    
    return jsonify(result)

if __name__ == '__main__':
    try:
        socket.create_connection(("www.google.com", 80))
        app.run(debug=True)
    except OSError:
        print("Error: No hay conexión a internet")