"""
MiroFish Backend - Flask-Anwendungsfabrik
"""

import os
import warnings

# Warnungen von multiprocessing resource_tracker unterdruecken (aus Drittanbieter-Bibliotheken wie transformers)
# Muss vor allen anderen Imports gesetzt werden
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request, jsonify, g
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """Flask-Anwendungsfabrikfunktion"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # JSON-Kodierung einrichten: Sicherstellen, dass CJK-Zeichen direkt angezeigt werden (statt \uXXXX-Format)
    # Flask >= 2.3 verwendet app.json.ensure_ascii, aeltere Versionen verwenden JSON_AS_ASCII-Konfiguration
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False

    # Protokollierung einrichten
    logger = setup_logger('mirofish')

    # Startinformationen nur im Reloader-Unterprozess ausgeben (doppelte Ausgabe im Debug-Modus vermeiden)
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process

    if should_log_startup:
        logger.info("=" * 50)
        logger.info("MiroFish Backend wird gestartet...")
        logger.info("=" * 50)

    # CORS aktivieren
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Bereinigungsfunktion fuer Simulationsprozesse registrieren (stellt sicher, dass alle Simulationsprozesse beim Herunterfahren beendet werden)
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("Bereinigungsfunktion fuer Simulationsprozesse registriert")

    # Anfrage-Protokollierungs-Middleware
    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(f"Anfrage: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            logger.debug(f"Anfragekoerper: {request.get_json(silent=True)}")

    @app.after_request
    def log_response(response):
        logger = get_logger('mirofish.request')
        logger.debug(f"Antwort: {response.status_code}")
        return response

    # Auth-Blueprint registrieren
    from .auth.routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')

    # Globale Auth-Middleware
    @app.before_request
    def check_auth():
        # Auth fuer Gesundheitspruefung, Auth-Endpunkte, OPTIONS und statische Dateien ueberspringen
        if request.path in ('/health',) or \
           request.path.startswith('/api/auth/') or \
           request.method == 'OPTIONS':
            return None

        if not Config.AUTH_ENABLED:
            return None

        import jwt
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': 'Authentifizierung erforderlich'}), 401

        token = auth_header.split('Bearer ')[1]
        try:
            payload = jwt.decode(
                token,
                Config.SUPABASE_JWT_SECRET,
                algorithms=['HS256'],
                audience='authenticated'
            )
            g.user = {
                'id': payload.get('sub'),
                'email': payload.get('email'),
                'role': payload.get('role', 'authenticated')
            }
        except jwt.ExpiredSignatureError:
            return jsonify({'success': False, 'error': 'Token abgelaufen'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'success': False, 'error': 'Ungueltiger Token'}), 401

    # Blueprints registrieren
    from .api import graph_bp, simulation_bp, report_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')

    # Gesundheitspruefung
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'MiroFish Backend'}

    if should_log_startup:
        logger.info("MiroFish Backend erfolgreich gestartet")

    return app
