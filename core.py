import os
import json
import uuid
from functools import wraps
from google.cloud import firestore
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash


# Configuración de Firestore
PROJECT_ID = "surfn-peru"
DATABASE_ID = "predios"

# Inicializar cliente de Firestore
db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)

# --- RUTAS DE COLECCIONES ---
PROPERTIES_PATH = "propiedades"
CLIENTS_PATH = "clientes"
CONFIG_PATH = "configuracion"

# Configuramos Flask para buscar plantillas en el directorio raíz
base_dir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, template_folder=base_dir, static_folder=os.path.join(base_dir, 'static'))
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

# Helpers para Autenticación
def get_password_hash(env_var, default_hash):
    val = os.environ.get(env_var)
    if val:
        # Si ya parece ser un hash, devolverlo. Si no, hashear el texto plano.
        if val.startswith(('scrypt:', 'pbkdf2:', 'bcrypt:')):
            return val
        return generate_password_hash(val)
    return default_hash

# Datos de Autenticación (Hashes)
VALID_USERS = {
    "Rosario": get_password_hash('APP_PASSWORD_ROSARIO', "scrypt:32768:8:1$k3anv6A6jotvvDXo$a88a8b9e9ec55fa6df026cdbd8a16a9408c6fe8be3e7171b8587b30c22af72a277c224f9382cbdc86694d0da4e5cd52a5bc5c7f24268029d9cb3f7be14f383f3"),
    "admin": get_password_hash('APP_PASSWORD_ADMIN', "scrypt:32768:8:1$AsX0iyRSFJp0ImfM$5e93b64becb289a71071ebe13102fc470a737e2b845ab67ecd611cdcf2554c19a252fc0da35afd993758b51dfc5bcf5e0b8a009d7d9ccae425455d55cbe58de8")
}

# --- AUTENTICACIÓN ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            # Si es una petición a la API, devolver 401
            if request.path.startswith('/api/'):
                return jsonify({"error": "No autorizado", "status": "unauthorized"}), 401
            # Si es una petición a una vista, redirigir al login
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in VALID_USERS and check_password_hash(VALID_USERS[username], password):
            session['logged_in'] = True
            session['username'] = username  # Opcional: guardar el rol/usuario
            return redirect(url_for('index'))
        else:
            error = 'Credenciales incorrectas'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# --- LÓGICA DE NEGOCIO (Cálculos) ---
def calculate_metrics(p):
    """Calcula las áreas totales y precios por metro según requerimientos."""
    try:
        techados = float(p.get('metros_techados', 0))
        terrazas = float(p.get('metros_terrazas', 0))
        garajes = float(p.get('metros_garajes', 0))
        depositos = float(p.get('metros_depositos', 0))
        
        # Determinar el precio base para el cálculo por metro
        is_alquiler = p.get('tipo_operacion') == 'Alquiler'
        precio = float(p.get('precio_alquiler' if is_alquiler else 'precio', 0))

        # Fórmula: Techados x 1.0 + Terrazas x 0.5 + Garajes x 1.0 + Depósitos x 1.0
        area_total = (techados * 1.0) + (terrazas * 0.5) + (garajes * 1.0) + (depositos * 1.0)
        precio_metro = precio / area_total if area_total > 0 else 0
        
        # Comisiones
        com_max_pct = float(p.get('comision_max_pct', 0))
        com_min_pct = float(p.get('comision_min_pct', 0))
        comision_max_monto = (precio * com_max_pct / 100)
        comision_min_monto = (precio * com_min_pct / 100)

        return {
            'area_total': round(area_total, 2),
            'precio_metro': round(precio_metro, 0),
            'comision_max_monto': round(comision_max_monto, 0),
            'comision_min_monto': round(comision_min_monto, 0)
        }
    except (ValueError, TypeError):
        return {'area_total': 0, 'precio_metro': 0, 'comision_max_monto': 0, 'comision_min_monto': 0}

# --- RUTAS DE LA API (CRUD) ---

@app.route('/api/properties', methods=['GET', 'POST'])
@login_required
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
@login_required
def handle_property_item(id):
    if request.method == 'DELETE':
        db.collection(PROPERTIES_PATH).document(id).delete()
        return jsonify({"status": "deleted"})
    elif request.method == 'PUT':
        data = request.json
        db.collection(PROPERTIES_PATH).document(id).update(data)
        return jsonify({"status": "updated"})

# --- CLIENTES API ---

@app.route('/api/clients', methods=['GET', 'POST'])
@login_required
def handle_clients():
    if request.method == 'POST':
        data = request.json
        doc_id = data.get('id_cliente') or str(uuid.uuid4())
        data['id_cliente'] = doc_id
        db.collection(CLIENTS_PATH).document(doc_id).set(data)
        return jsonify({"status": "success", "id_cliente": doc_id})
    
    docs = db.collection(CLIENTS_PATH).stream()
    clients = [doc.to_dict() for doc in docs]
    return jsonify(clients)

@app.route('/api/clients/<id>', methods=['DELETE', 'PUT'])
@login_required
def handle_client_item(id):
    if request.method == 'DELETE':
        db.collection(CLIENTS_PATH).document(id).delete()
        return jsonify({"status": "deleted"})
    elif request.method == 'PUT':
        data = request.json
        db.collection(CLIENTS_PATH).document(id).update(data)
        return jsonify({"status": "updated"})


# --- CONFIGURACIÓN API ---

@app.route('/api/config', methods=['GET', 'POST', 'PUT'])
@login_required
def handle_config():
    # Only one config doc for the user/agent
    doc_ref = db.collection(CONFIG_PATH).document('agent_settings')
    
    if request.method == 'GET':
        doc = doc_ref.get()
        if doc.exists:
            return jsonify(doc.to_dict())
        else:
            return jsonify({}) # Empty config if not set yet

    if request.method in ['POST', 'PUT']:
        data = request.json
        doc_ref.set(data, merge=True)
        return jsonify({"status": "success", "message": "Configuración guardada"})

# --- RUTA PRINCIPAL ---
@app.route('/')
@login_required
def index():
    # Carga el archivo HTML separado
    return render_template('predios.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
    

    