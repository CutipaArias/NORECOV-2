"""Crea .env local; no lo subas a GitHub."""
from pathlib import Path
import base64, secrets
root = Path(__file__).resolve().parents[1]
path = root / '.env'
if path.exists():
    raise SystemExit('Ya existe .env; no lo sobrescribo.')
def password():
    return secrets.token_urlsafe(24)
control = password()
admin = password()
mongo = password()
redis = password()
key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
lines = [
 'CONTROL_MONGO_USER=norecov_admin',
 f'CONTROL_MONGO_PASSWORD={control}',
 f'CONTROL_MONGO_URI=mongodb://norecov_admin:{control}@mongo-control:27017/admin?authSource=admin',
 'CONTROL_DB=norecov',
 f'SECRET_KEY={secrets.token_urlsafe(48)}',
 f'ENCRYPTION_KEY={key}',
 'ADMIN_EMAIL=admin@norecov.local',
 f'ADMIN_PASSWORD={admin}',
 'CORS_ORIGINS=http://localhost:5173,http://localhost:8080',
 'ARTIFACT_DIR=/data/artifacts',
 'DEMO_MONGO_USER=root', f'DEMO_MONGO_PASSWORD={mongo}',
 f'DEMO_REDIS_PASSWORD={redis}',
 'NORECOV_MINIO_USER=norecovminio',
 f'NORECOV_MINIO_PASSWORD={password()}',
]
path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('Archivo .env creado. Contraseña inicial del portal:', admin)
print('Guarda esta contraseña; se usa en el primer inicio de sesión.')
