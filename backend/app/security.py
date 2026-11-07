from datetime import timedelta
import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .config import settings
from .db import db, utcnow

bearer = HTTPBearer(auto_error=False)
ROLES = ['DBA_MASTER', 'DBA', 'DEVOPS', 'SOPORTE', 'AUDITOR']

def hash_password(value):
    return bcrypt.hashpw(value.encode(), bcrypt.gensalt(rounds=12)).decode()

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user):
    now = utcnow()
    return jwt.encode({'sub': str(user['_id']), 'role': user['role'], 'exp': now + timedelta(hours=8), 'iat': now}, settings().secret_key, algorithm='HS256')

def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not credentials:
        raise HTTPException(401, 'Debes iniciar sesión')
    try:
        payload = jwt.decode(credentials.credentials, settings().secret_key, algorithms=['HS256'])
        from bson import ObjectId
        user = db().usuarios.find_one({'_id': ObjectId(payload['sub']), 'enabled': True})
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, 'Sesión inválida o expirada')
    if not user:
        raise HTTPException(401, 'Cuenta deshabilitada')
    return user

def require(*roles):
    def checker(user=Depends(current_user)):
        if user['role'] not in roles and user['role'] != 'DBA_MASTER':
            raise HTTPException(403, 'No tienes permisos para esta operación')
        return user
    return checker
