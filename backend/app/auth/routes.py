"""Auth-API-Endpunkte"""
from flask import Blueprint, jsonify, request
from ..config import Config

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/status', methods=['GET'])
def auth_status():
    """Gibt zurueck ob Auth aktiviert ist und die Supabase-Konfiguration."""
    return jsonify({
        'auth_enabled': Config.AUTH_ENABLED,
        'supabase_url': Config.SUPABASE_URL if Config.AUTH_ENABLED else '',
        'supabase_anon_key': Config.SUPABASE_ANON_KEY if Config.AUTH_ENABLED else ''
    })

@auth_bp.route('/me', methods=['GET'])
def get_me():
    """Gibt den aktuellen Benutzer zurueck."""
    from .middleware import require_auth, get_current_user
    # Manual check here since we want 200 with null if no auth
    if not Config.AUTH_ENABLED:
        return jsonify({'user': None})

    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'user': None}), 401

    import jwt
    token = auth_header.split('Bearer ')[1]
    try:
        payload = jwt.decode(
            token,
            Config.SUPABASE_JWT_SECRET,
            algorithms=['HS256'],
            audience='authenticated'
        )
        return jsonify({
            'user': {
                'id': payload.get('sub'),
                'email': payload.get('email'),
                'role': payload.get('role', 'authenticated')
            }
        })
    except Exception:
        return jsonify({'user': None}), 401
