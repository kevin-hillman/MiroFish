"""Auth-Middleware fuer Flask"""
import jwt
from functools import wraps
from flask import request, jsonify, g
from ..config import Config

def require_auth(f):
    """Decorator: Prueft Supabase JWT Token im Authorization-Header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not Config.AUTH_ENABLED:
            g.user = None
            return f(*args, **kwargs)

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

        return f(*args, **kwargs)
    return decorated

def get_current_user():
    """Gibt den aktuellen Benutzer zurueck oder None."""
    return getattr(g, 'user', None)
