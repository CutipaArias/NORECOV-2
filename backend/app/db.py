import datetime as dt
from bson import ObjectId
from pymongo import MongoClient, ASCENDING, DESCENDING
from .config import settings

_client = None

def db():
    global _client
    if _client is None:
        _client = MongoClient(settings().control_mongo_uri, serverSelectionTimeoutMS=7000, tz_aware=True)
    return _client[settings().control_db]

def utcnow():
    return dt.datetime.now(dt.timezone.utc)

def oid(text):
    if not ObjectId.is_valid(text):
        from fastapi import HTTPException
        raise HTTPException(400, 'Identificador inválido')
    return ObjectId(text)

def public(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [public(x) for x in value]
    if isinstance(value, dict):
        return {('_id' if k == '_id' else k): public(v) for k, v in value.items() if k not in ('credentials_enc', 'password_hash', 'secret_enc', 'access_key_enc')}
    return value

def initialize():
    from .security import hash_password
    d = db()
    d.command('ping')
    d.usuarios.create_index('email', unique=True)
    d.nodos.create_index([('host', ASCENDING), ('port', ASCENDING), ('engine', ASCENDING)], unique=True)
    d.planes_backup.create_index('node_id')
    d.artefactos.create_index([('node_id', ASCENDING), ('created_at', DESCENDING)])
    d.jobs.create_index([('status', ASCENDING), ('created_at', ASCENDING)])
    d.pruebas_restauracion.create_index('artifact_id')
    d.audit_logs.create_index('at')
    if not d.usuarios.count_documents({'role': 'DBA_MASTER'}, limit=1):
        # Varios procesos pueden inicializar la base a la vez. Solo uno inserta.
        try:
            d.usuarios.insert_one({'email': settings().admin_email.lower(), 'name': 'Administrador NORECOV', 'password_hash': hash_password(settings().admin_password), 'role': 'DBA_MASTER', 'enabled': True, 'created_at': utcnow()})
        except __import__('pymongo').errors.DuplicateKeyError:
            if not d.usuarios.find_one({'email': settings().admin_email.lower(), 'role': 'DBA_MASTER'}):
                raise

def audit(action, actor='system', detail=None, ip=None):
    # Bitácora append-only a nivel de aplicación. Requiere WORM externo para inmutabilidad fuerte.
    db().audit_logs.insert_one({'at': utcnow(), 'actor': actor, 'action': action, 'ip': ip, 'detail': detail or {}})
