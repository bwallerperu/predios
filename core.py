import os
import json
import uuid
from flask import Flask, render_template, request, jsonify
from firebase_admin import credentials, firestore, initialize_app

# --- CONFIGURACIÓN DE FIREBASE ---
try:
    if '__firebase_config' in globals():
        firebase_config = json.loads(globals()['__firebase_config'])
        initialize_app()
    else:
        initialize_app()
except Exception:
    pass

db = firestore.client()
app_id = locals().get('__app_id', 'inmobiliaria-app-default')

# --- RUTAS DE COLECCIONES (Siguiendo Regla 1) ---
PROPERTIES_PATH = f'artifacts/{app_id}/public/data/properties'
CLIENTS_PATH = f'artifacts/{app_id}/public/data/clients'

# Configuramos Flask para buscar plantillas en el directorio raíz
app = Flask(__name__, template_folder='.')

# --- LÓGICA DE NEGOCIO (Cálculos) ---
def calculate_metrics(p):
    """Calcula las áreas totales y precios por metro según requerimientos."""
    try:
        techados = float(p.get('metros_techados', 0))
        terrazas = float(p.get('metros_terrazas', 0))
        garajes = float(p.get('metros_garajes', 0))
        depositos = float(p.get('metros_depositos', 0))
        precio = float(p.get('precio', 0))

        # Fórmula: Techados x 1.0 + Terrazas x 0.5 + Garajes x 1.0 + Depósitos x 1.0
        area_total = (techados * 1.0) + (terrazas * 0.5) + (garajes * 1.0) + (depositos * 1.0)
        precio_metro = precio / area_total if area_total > 0 else 0
        
        return {
            'area_total': round(area_total, 2),
            'precio_metro': round(precio_metro, 2)
        }
    except (ValueError, TypeError):
        return {'area_total': 0, 'precio_metro': 0}

# --- RUTAS DE LA API (CRUD) ---

@app.route('/api/properties', methods=['GET', 'POST'])
def handle_properties():
    if request.method == 'POST':
        data = request.json
        doc_id = data.get('id') or str(uuid.uuid4())
        data['id'] = doc_id
        db.collection(PROPERTIES_PATH).document(doc_id).set(data)
        return jsonify({"status": "success", "id": doc_id})
    
    docs = db.collection(PROPERTIES_PATH).stream()
    properties = []
    for doc in docs:
        p = doc.to_dict()
        p['metrics'] = calculate_metrics(p)
        properties.append(p)
    return jsonify(properties)

@app.route('/api/properties/<id>', methods=['DELETE', 'PUT'])
def handle_property_item(id):
    if request.method == 'DELETE':
        db.collection(PROPERTIES_PATH).document(id).delete()
        return jsonify({"status": "deleted"})
    elif request.method == 'PUT':
        data = request.json
        db.collection(PROPERTIES_PATH).document(id).update(data)
        return jsonify({"status": "updated"})

@app.route('/api/clients', methods=['GET', 'POST'])
def handle_clients():
    if request.method == 'POST':
        data = request.json
        doc_id = str(uuid.uuid4())
        data['id'] = doc_id
        db.collection(CLIENTS_PATH).document(doc_id).set(data)
        return jsonify({"status": "success", "id": doc_id})
    
    docs = db.collection(CLIENTS_PATH).stream()
    clients = [doc.to_dict() for doc in docs]
    return jsonify(clients)

@app.route('/api/clients/<id>', methods=['DELETE'])
def delete_client(id):
    db.collection(CLIENTS_PATH).document(id).delete()
    return jsonify({"status": "deleted"})

# --- RUTA PRINCIPAL ---
@app.route('/')
def index():
    # Carga el archivo HTML separado
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))