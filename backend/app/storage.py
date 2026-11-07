"""Repositorio local cifrado y copia opcional en S3/MinIO."""
from pathlib import Path
import hashlib
import boto3
from botocore.client import Config
from .config import settings
from .crypto import decrypt_secret, file_sha256

def local_path(artifact_id):
    return Path(settings().artifact_dir) / f'{artifact_id}.norecov'

def s3_client(repo):
    return boto3.client('s3', endpoint_url=repo.get('endpoint') or None,
        region_name=repo.get('region') or 'us-east-1',
        aws_access_key_id=decrypt_secret(repo.get('access_key_enc','')) or None,
        aws_secret_access_key=decrypt_secret(repo.get('secret_enc','')) or None,
        config=Config(signature_version='s3v4', s3={'addressing_style':'path'}))

def test_repository(repo):
    if repo['kind'] == 'local':
        Path(settings().artifact_dir).mkdir(parents=True, exist_ok=True)
        return
    if not repo.get('bucket'):
        raise ValueError('Bucket obligatorio')
    client = s3_client(repo)
    # HEAD valida existencia/permisos de lectura. La escritura se valida con una prueba efímera.
    import uuid
    marker = f'norecov-check/{uuid.uuid4().hex}'
    client.put_object(Bucket=repo['bucket'], Key=marker, Body=b'norecov')
    content = client.get_object(Bucket=repo['bucket'], Key=marker)['Body'].read()
    if content != b'norecov':
        raise RuntimeError('La lectura de prueba no coincide')
    client.delete_object(Bucket=repo['bucket'], Key=marker)

def upload(repo, artifact_id, path, sha):
    if not repo or repo['kind'] == 'local':
        return {'kind':'local','file':str(path)}
    object_key = f'backups/{artifact_id}.norecov'
    client = s3_client(repo)
    extra = {'Metadata':{'sha256':sha}}
    if repo.get('object_lock'):
        # WORM solo si el bucket ya tiene Object Lock configurado.
        from datetime import datetime, timedelta, timezone
        extra['ObjectLockMode'] = 'GOVERNANCE'
        extra['ObjectLockRetainUntilDate'] = datetime.now(timezone.utc) + timedelta(days=30)
    client.upload_file(str(path), repo['bucket'], object_key, ExtraArgs=extra)
    metadata = client.head_object(Bucket=repo['bucket'], Key=object_key)
    if metadata.get('Metadata',{}).get('sha256') != sha:
        raise RuntimeError('Hash de metadata S3 no coincide')
    # Verificación de extremo a extremo: leer el ciphertext del bucket y recalcular SHA-256.
    obj = client.get_object(Bucket=repo['bucket'], Key=object_key)
    check = hashlib.sha256()
    for chunk in obj['Body'].iter_chunks(chunk_size=1024*1024):
        if chunk: check.update(chunk)
    obj['Body'].close()
    if check.hexdigest() != sha:
        raise RuntimeError('SHA-256 de lectura S3 difiere del artefacto local')
    return {'kind':'s3','bucket':repo['bucket'],'key':object_key,'repository_id':str(repo['_id'])}

def ensure_local(artifact, db):
    path = local_path(str(artifact['_id']))
    if not path.exists():
        ref = artifact.get('storage') or {}
        if ref.get('kind') != 's3':
            raise FileNotFoundError('No existe el artefacto local')
        from bson import ObjectId
        repo = db.repositorios.find_one({'_id':ObjectId(ref['repository_id'])})
        if not repo:
            raise FileNotFoundError('Repositorio S3 no encontrado')
        path.parent.mkdir(parents=True, exist_ok=True)
        s3_client(repo).download_file(ref['bucket'], ref['key'], str(path))
    if file_sha256(path) != artifact['sha256']:
        raise RuntimeError('SHA-256 incorrecto; artefacto alterado')
    return path

def remove_artifact(artifact, db):
    ref = artifact.get('storage') or {}
    if ref.get('kind') == 's3':
        from bson import ObjectId
        repo = db.repositorios.find_one({'_id':ObjectId(ref['repository_id'])})
        if repo:
            # WORM puede impedir esta operación: propagar la excepción sin falsear el estado.
            s3_client(repo).delete_object(Bucket=ref['bucket'], Key=ref['key'])
    local_path(str(artifact['_id'])).unlink(missing_ok=True)
