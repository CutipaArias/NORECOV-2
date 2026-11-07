"""Orquestación persistida: backup -> cifrado -> repositorio -> sandbox -> validación."""
import os
import time
import uuid
from datetime import timedelta
from pathlib import Path
from bson import ObjectId
from pymongo import ReturnDocument
from .db import db, utcnow, audit
from .adapters import ADAPTERS
from .crypto import encrypt_chunks, file_sha256
from .storage import local_path, ensure_local, upload, remove_artifact
from .sandbox import validate_artifact
from .notifier import alert

def enqueue(kind, target_id, actor='system', plan_id=None):
    d = db()
    job = {'kind':kind,'target_id':str(target_id),'plan_id':str(plan_id) if plan_id else None,
           'actor':actor,'created_at':utcnow(),'updated_at':utcnow(),'status':'queued', 'attempts':0,
           'progress':'En cola', 'error':None}
    result = d.jobs.insert_one(job)
    audit('job.queued', actor, {'kind':kind,'target_id':str(target_id),'job_id':str(result.inserted_id)})
    return str(result.inserted_id)

def get_credentials(node):
    from .crypto import decrypt_secret
    return decrypt_secret(node.get('credentials_enc',''))

def _stream_of(process):
    for part in iter(lambda: process.stdout.read(1024*1024), b''):
        yield part

def do_backup(job):
    d = db()
    node = d.nodos.find_one({'_id':ObjectId(job['target_id'])})
    if not node:
        raise ValueError('Nodo inexistente')
    adapter = ADAPTERS[node['engine']]
    plan = d.planes_backup.find_one({'_id':ObjectId(job['plan_id'])}) if job.get('plan_id') else None
    repo = d.repositorios.find_one({'_id':ObjectId(plan['repository_id'])}) if plan and plan.get('repository_id') else None
    backup_started = utcnow()
    t0 = time.monotonic()
    # Lecturas del origen en un punto aproximado previo al dump. Mejorable con snapshots consistentes.
    adapter.verify(node)
    counts = adapter.source_counts(node)
    snapshot_at = utcnow()
    artifact_id = ObjectId()
    path = local_path(str(artifact_id))
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix('.part')
    last_error = None
    for attempt in range(3):
        process = None
        try:
            process = adapter.extract(node)
            meta = encrypt_chunks(_stream_of(process), partial)
            errors = process.stderr.read().decode(errors='replace')[-1500:]
            returncode = process.wait(timeout=60)
            if returncode:
                raise RuntimeError(f'Extractor CLI terminó con código {returncode}: {errors}')
            os.replace(partial, path)
            if file_sha256(path) != meta['sha256']:
                raise RuntimeError('Verificación SHA-256 post-escritura fallida')
            break
        except Exception as exc:
            last_error = exc
            partial.unlink(missing_ok=True)
            if process and process.poll() is None:
                process.kill()
                process.wait()
            if attempt < 2:
                time.sleep(2 ** attempt)
    else:
        raise RuntimeError(f'Extracción falló después de 3 intentos: {last_error}')
    try:
        location = upload(repo, str(artifact_id), path, meta['sha256'])
        artifact = {'_id':artifact_id,'node_id':str(node['_id']), 'plan_id':job.get('plan_id'),
            'engine':node['engine'],'engine_version':node['version'], 'node_name':node['name'],
            'sha256':meta['sha256'], 'raw_bytes':meta['raw_bytes'],'size_bytes':meta['size_bytes'],
            'source_counts':counts, 'snapshot_at':snapshot_at, 'created_at':utcnow(),
            'backup_ms':round((time.monotonic()-t0)*1000),'storage':location,'status':'stored'}
        d.artefactos.insert_one(artifact)
        audit('backup.created', job['actor'], {'artifact_id':str(artifact_id),'sha256':meta['sha256']})
    except Exception:
        path.unlink(missing_ok=True)
        raise
    # Prueba automáticamente cada backup según SRS.
    do_test({'target_id':str(artifact_id),'actor':job['actor']})
    return {'artifact_id':str(artifact_id),'backup_ms':artifact['backup_ms']}

def do_test(job):
    d = db()
    artifact = d.artefactos.find_one({'_id':ObjectId(job['target_id'])})
    if not artifact:
        raise ValueError('Artefacto no encontrado')
    path = ensure_local(artifact, d)
    result = None
    last_error = ''
    for trial in range(1, 3):
        t0 = time.monotonic()
        try:
            result = validate_artifact(path, artifact)
            if not result['ok']:
                last_error = f"Conteo inconsistente: esperado={result['expected']} obtenido={result['actual']}"
            else:
                break
        except Exception as exc:
            last_error = str(exc)[:1200]
        if trial == 1:
            time.sleep(1)
    valid = bool(result and result['ok'])
    now = utcnow()
    # Edad del punto de recuperación al término de la prueba: estimación, no RPO de un desastre real.
    rpo_age_minutes = round((now - artifact['snapshot_at']).total_seconds()/60, 3)
    if not result:
        result = {'ok':False, 'expected':artifact['source_counts'], 'actual':{}, 'rto_ms':round((time.monotonic()-t0)*1000), 'sandbox_image':None}
    record = {'artifact_id':str(artifact['_id']),'node_id':artifact['node_id'],
        'at':now,'result':'VALIDATED' if valid else 'CRITICAL_CORRUPT',
        'rto_ms':result.get('rto_ms'), 'rpo_age_minutes':rpo_age_minutes,
        'expected':result.get('expected'), 'actual':result.get('actual'),
        'sandbox_image':result.get('sandbox_image'),'error':None if valid else last_error}
    d.pruebas_restauracion.insert_one(record)
    d.artefactos.update_one({'_id':artifact['_id']}, {'$set':{'status':'validated' if valid else 'corrupt', 'last_test_at':now}})
    audit('restore.validated' if valid else 'restore.critical', job['actor'], {'artifact_id':str(artifact['_id']),'rto_ms':record['rto_ms'],'detail':record['error']})
    alert('success' if valid else 'critical', f"{'Restauración correcta' if valid else 'Restauración fallida'}: {artifact['node_name']} ({artifact['_id']})", str(artifact['_id']))
    if not valid:
        raise RuntimeError(f'ESTADO_CRÍTICO_CORRUPTO: {last_error}')
    return {'artifact_id':str(artifact['_id']), 'rto_ms':record['rto_ms'], 'rpo_age_minutes':rpo_age_minutes}

def do_retention():
    d = db()
    now = utcnow()
    deleted = 0
    for plan in d.planes_backup.find():
        artifacts = list(d.artefactos.find({'plan_id':str(plan['_id']), 'status':{'$ne':'purged'}}).sort('created_at', -1))
        # Siempre conservar al menos las DOS copias validadas más recientes por nodo.
        valid = list(d.artefactos.find({'node_id':plan['node_id'], 'status':'validated'}).sort('created_at', -1))
        protected = {str(a['_id']) for a in valid[:2]}
        expiry = now - timedelta(days=plan['retention_days'])
        for a in artifacts:
            if a['created_at'] >= expiry or str(a['_id']) in protected:
                continue
            if len(valid) < 2:
                continue
            try:
                remove_artifact(a, d)
                d.artefactos.update_one({'_id':a['_id']}, {'$set':{'status':'purged','purged_at':now}})
                audit('backup.purged', detail={'artifact_id':str(a['_id'])})
                deleted += 1
            except Exception as exc:
                audit('backup.purge_failure', detail={'artifact_id':str(a['_id']),'error':str(exc)[:300]})
    return {'purged': deleted}

def claim_job():
    d = db()
    now = utcnow()
    return d.jobs.find_one_and_update({'status':'queued'},
        {'$set':{'status':'running','updated_at':now, 'progress':'Ejecutando'}, '$inc':{'attempts':1}},
        sort=[('created_at',1)], return_document=ReturnDocument.AFTER)

def execute_job(job):
    d = db()
    try:
        if job['kind'] == 'backup':
            result = do_backup(job)
        elif job['kind'] == 'test':
            result = do_test(job)
        elif job['kind'] == 'retention':
            result = do_retention()
        else:
            raise ValueError('Tipo de trabajo no permitido')
        d.jobs.update_one({'_id':job['_id']}, {'$set':{'status':'done','progress':'Completado','result':result,'updated_at':utcnow()}})
    except Exception as exc:
        d.jobs.update_one({'_id':job['_id']}, {'$set':{'status':'failed','progress':'Fallido','error':str(exc)[:1500],'updated_at':utcnow()}})
        audit('job.failed', job['actor'], {'job_id':str(job['_id']),'error':str(exc)[:800]})
        try:
            alert('critical', f"Error en trabajo {job['_id']}: {str(exc)[:250]}")
        except Exception:
            pass
