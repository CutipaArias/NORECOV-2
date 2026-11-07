"""API REST NORECOV; autenticación JWT y RBAC sobre todas las rutas de datos."""
from contextlib import asynccontextmanager
import csv
import io
from datetime import timedelta
from bson import ObjectId
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from apscheduler.triggers.cron import CronTrigger
from pymongo.errors import DuplicateKeyError
from .config import settings
from .db import db, utcnow, oid, public, initialize, audit
from .security import create_token, current_user, require, hash_password, verify_password, ROLES
from .schemas import Login, NodeCreate, PlanCreate, UserCreate, UserUpdate, RepositoryCreate, ChannelCreate
from .crypto import encrypt_secret
from .adapters import ADAPTERS
from .jobs import enqueue
from .storage import ensure_local, test_repository
from .notifier import send_channel

@asynccontextmanager
async def lifespan(app):
    initialize()
    yield

app = FastAPI(title='NORECOV API',version='0.1.0',lifespan=lifespan,docs_url='/api/docs',openapi_url='/api/openapi.json')
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings().cors_origins.split(',')],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])

def actor(user):
    return user['email']

def activity(action,user,request,detail=None):
    audit(action, actor(user), detail or {}, request.client.host if request.client else None)

def list_data(collection, filters=None, limit=150, order='created_at'):
    return [public(x) for x in db()[collection].find(filters or {}).sort(order,-1).limit(limit)]

@app.get('/api/health')
def health():
    try:
        db().command('ping')
        return {'status':'ok','service':'norecov-api','mongo':'connected'}
    except Exception:
        raise HTTPException(503, 'No se pudo conectar a MongoDB de control')

@app.post('/api/auth/login')
def login(body:Login, request:Request):
    user = db().usuarios.find_one({'email':body.email.strip().lower(),'enabled':True})
    if not user or not verify_password(body.password,user['password_hash']):
        raise HTTPException(401,'Correo o contraseña incorrectos')
    activity('auth.login',user,request)
    return {'access_token':create_token(user),'token_type':'bearer','user':public(user)}

@app.get('/api/auth/me')
def me(user=Depends(current_user)):
    return public(user)

@app.get('/api/dashboard')
def dashboard(user=Depends(current_user)):
    d = db()
    nodes = d.nodos.count_documents({})
    artifacts = d.artefactos.count_documents({'status':{'$ne':'purged'}})
    validated = d.artefactos.count_documents({'status':'validated'})
    tests = list(d.pruebas_restauracion.find().sort('at',-1).limit(30))
    ok = sum(x['result']=='VALIDATED' for x in tests)
    rto = [x['rto_ms'] for x in tests if x['result']=='VALIDATED' and x.get('rto_ms') is not None]
    storage_bytes = sum(x.get('size_bytes',0) for x in d.artefactos.find({'status':{'$ne':'purged'}},{'size_bytes':1}))
    recent = [public(x) for x in tests[:8]]
    return {'nodes':nodes,'artifacts':artifacts,'validated':validated,
        'success_rate':round((ok/len(tests)*100),1) if tests else 0,
        'average_rto_ms':round(sum(rto)/len(rto)) if rto else None,
        'storage_bytes':storage_bytes,
        'jobs_pending':d.jobs.count_documents({'status':{'$in':['queued','running']}}),
        'critical_alerts':d.alertas.count_documents({'severity':'critical'}),
        'recent_tests':recent,
        'rto_trend':[{'date':x['at'].isoformat(),'rto_ms':x['rto_ms'],'result':x['result']} for x in reversed(tests) if x.get('rto_ms')]}

@app.get('/api/nodes')
def nodes(user=Depends(current_user)):
    return list_data('nodos',order='created_at')

@app.post('/api/nodes',status_code=201)
def create_node(body:NodeCreate, request:Request, user=Depends(require('DBA'))):
    data = body.model_dump(exclude={'password'})
    data['credentials_enc'] = encrypt_secret(body.password)
    data['created_at'] = utcnow()
    version = ADAPTERS[body.engine].verify(data)
    data['version'] = version
    data['status'] = 'online'
    try:
        result = db().nodos.insert_one(data)
    except DuplicateKeyError:
        raise HTTPException(409, 'Este nodo ya existe')
    activity('node.created',user,request,{'node_id':str(result.inserted_id)})
    return public(db().nodos.find_one({'_id':result.inserted_id}))

@app.put('/api/nodes/{id}')
def update_node(id:str,body:NodeCreate,request:Request,user=Depends(require('DBA'))):
    d = db()
    before = d.nodos.find_one({'_id':oid(id)})
    if not before:
        raise HTTPException(404, 'Nodo no encontrado')
    data = body.model_dump(exclude={'password'})
    data['credentials_enc'] = encrypt_secret(body.password) if body.password else before.get('credentials_enc','')
    data['version'] = ADAPTERS[body.engine].verify(data)
    data['status'] = 'online'
    try:
        d.nodos.update_one({'_id':oid(id)},{'$set':data})
    except DuplicateKeyError:
        raise HTTPException(409,'Ya existe esa conexión')
    activity('node.updated',user,request,{'node_id':id})
    return public(d.nodos.find_one({'_id':oid(id)}))

@app.delete('/api/nodes/{id}')
def delete_node(id:str,request:Request,user=Depends(require('DBA'))):
    if db().planes_backup.count_documents({'node_id':id}):
        raise HTTPException(409,'Primero elimina las programaciones de este nodo')
    if not db().nodos.delete_one({'_id':oid(id)}).deleted_count:
        raise HTTPException(404,'Nodo no encontrado')
    activity('node.deleted',user,request,{'node_id':id})
    return {'ok':True}

@app.get('/api/plans')
def plans(user=Depends(current_user)):
    return list_data('planes_backup')

@app.post('/api/plans',status_code=201)
def create_plan(body:PlanCreate,request:Request,user=Depends(require('DBA'))):
    try:
        trigger = CronTrigger.from_crontab(body.cron, timezone='UTC')
    except (ValueError, TypeError) as exc:
        raise HTTPException(400,f'Cron inválido: {exc}')
    if not db().nodos.find_one({'_id':oid(body.node_id)}):
        raise HTTPException(404,'Nodo no encontrado')
    if body.repository_id and not db().repositorios.find_one({'_id':oid(body.repository_id)}):
        raise HTTPException(404,'Repositorio no encontrado')
    record = body.model_dump()
    record['created_at'] = utcnow()
    record['next_run'] = trigger.get_next_fire_time(None,utcnow())
    result = db().planes_backup.insert_one(record)
    activity('plan.created',user,request,{'plan_id':str(result.inserted_id)})
    return public(db().planes_backup.find_one({'_id':result.inserted_id}))

@app.put('/api/plans/{id}')
def update_plan(id:str,body:PlanCreate,request:Request,user=Depends(require('DBA'))):
    if not db().planes_backup.find_one({'_id':oid(id)}):
        raise HTTPException(404,'Plan no encontrado')
    try:
        trigger = CronTrigger.from_crontab(body.cron,timezone='UTC')
    except (ValueError, TypeError):
        raise HTTPException(400,'Expresión cron inválida')
    if not db().nodos.find_one({'_id':oid(body.node_id)}):
        raise HTTPException(404,'Nodo inexistente')
    if body.repository_id and not db().repositorios.find_one({'_id':oid(body.repository_id)}):
        raise HTTPException(404,'Repositorio no encontrado')
    data = body.model_dump()
    data['next_run'] = trigger.get_next_fire_time(None,utcnow())
    db().planes_backup.update_one({'_id':oid(id)},{'$set':data})
    activity('plan.updated',user,request,{'plan_id':id})
    return public(db().planes_backup.find_one({'_id':oid(id)}))

@app.delete('/api/plans/{id}')
def delete_plan(id:str,request:Request,user=Depends(require('DBA'))):
    if not db().planes_backup.delete_one({'_id':oid(id)}).deleted_count:
        raise HTTPException(404,'Plan inexistente')
    activity('plan.deleted',user,request,{'plan_id':id})
    return {'ok':True}

@app.post('/api/nodes/{id}/backup',status_code=202)
def backup_now(id:str,request:Request,user=Depends(require('DBA','SOPORTE'))):
    if not db().nodos.find_one({'_id':oid(id)}):
        raise HTTPException(404,'Nodo no encontrado')
    plan = db().planes_backup.find_one({'node_id':id,'active':True})
    job = enqueue('backup',id,actor(user),str(plan['_id']) if plan else None)
    activity('backup.requested',user,request,{'node_id':id,'job_id':job})
    return {'job_id':job,'status':'queued'}

@app.get('/api/jobs')
def jobs(user=Depends(current_user)):
    return list_data('jobs',limit=100)

@app.get('/api/artifacts')
def artifacts(user=Depends(current_user)):
    return list_data('artefactos')

@app.get('/api/tests')
def tests(user=Depends(current_user)):
    return list_data('pruebas_restauracion',order='at')

@app.post('/api/artifacts/{id}/test',status_code=202)
def test_now(id:str,request:Request,user=Depends(require('DBA'))):
    artifact = db().artefactos.find_one({'_id':oid(id),'status':{'$ne':'purged'}})
    if not artifact:
        raise HTTPException(404,'Artefacto no disponible')
    job_id = enqueue('test',id,actor(user))
    activity('restore.requested',user,request,{'artifact_id':id,'job_id':job_id})
    return {'job_id':job_id, 'status':'queued'}

@app.get('/api/artifacts/{id}/download')
def download(id:str,request:Request,user=Depends(require('DBA'))):
    artifact = db().artefactos.find_one({'_id':oid(id),'status':'validated'})
    if not artifact:
        raise HTTPException(404,'Solo es descargable un respaldo validado')
    try:
        path = ensure_local(artifact,db())
    except (FileNotFoundError,RuntimeError) as exc:
        raise HTTPException(409,str(exc))
    activity('backup.downloaded',user,request,{'artifact_id':id})
    return FileResponse(path,filename=f'norecov-{id}.norecov',media_type='application/octet-stream')

@app.get('/api/artifacts/{id}/guide')
def guide(id:str,request:Request,user=Depends(require('DBA'))):
    artifact = db().artefactos.find_one({'_id':oid(id),'status':'validated'})
    if not artifact:
        raise HTTPException(404,'No existe respaldo validado')
    engine = artifact['engine']
    cmd = ('mongorestore --drop --gzip --archive=backup-restaurado.archive --uri="mongodb://USUARIO@HOST:27017/?authSource=admin"'
       if engine == 'mongodb' else 'Detener Redis, copiar backup-restaurado.rdb al directorio de datos como dump.rdb y reiniciar Redis 7.0.x.')
    message = f'''# Guía de restauración NORECOV — {artifact['node_name']}

Artefacto: {id}
Motor: {engine} {artifact['engine_version']}
SHA-256 cifrado: {artifact['sha256']}
Estado: INTEGRIDAD VALIDADA

1. Coordinar la ventana de mantenimiento y proteger las bases existentes con otro respaldo.
2. Descargar el artefacto .norecov desde el portal (contiene datos cifrados AES-256-GCM).
3. En un entorno confiable, con ENCRYPTION_KEY configurada, ejecutar:
   python scripts/recover_artifact.py --input norecov-{id}.norecov --output backup-restaurado.{ 'archive' if engine == 'mongodb' else 'rdb'}
4. Validar la versión del motor de destino: {artifact['engine_version']}.
5. Restaurar en un ambiente NO productivo primero; tras aprobación y respaldo de seguridad, ejecutar:
   {cmd}
6. Comprobar los conteos de colecciones o claves, los permisos y la conectividad.
7. Eliminar los archivos temporales descifrados de forma segura según el procedimiento de la organización.

ADVERTENCIA: NORECOV no modifica automáticamente el origen de producción.
'''
    activity('restore.guide_exported',user,request,{'artifact_id':id})
    return PlainTextResponse(message,media_type='text/markdown',headers={'Content-Disposition':f'attachment; filename="guia-norecov-{id}.md"'})

@app.get('/api/repositories')
def repositories(user=Depends(current_user)):
    return list_data('repositorios')

@app.post('/api/repositories',status_code=201)
def repository_create(body:RepositoryCreate,request:Request,user=Depends(require('DEVOPS'))):
    record = body.model_dump(exclude={'access_key','secret_key'})
    record['access_key_enc'] = encrypt_secret(body.access_key)
    record['secret_enc'] = encrypt_secret(body.secret_key)
    record['created_at'] = utcnow()
    try:
        test_repository(record)
    except Exception as exc:
        raise HTTPException(400,f'No se pudo validar el repositorio: {str(exc)[:300]}')
    record['enabled'] = True
    result = db().repositorios.insert_one(record)
    activity('repository.created',user,request,{'repository_id':str(result.inserted_id)})
    return public(record)

@app.get('/api/channels')
def channels(user=Depends(current_user)):
    return list_data('canales_notificacion')

@app.post('/api/channels',status_code=201)
def channel_create(body:ChannelCreate,request:Request,user=Depends(require('DBA','SOPORTE'))):
    data = body.model_dump(exclude={'smtp_password'})
    data['secret_enc'] = encrypt_secret(body.smtp_password)
    if user['role'] != 'DBA_MASTER':
        data['severities'] = sorted(set(data['severities'] + ['critical']))
    data['enabled'] = False  # Se activa únicamente tras una notificación de prueba exitosa.
    data['created_at'] = utcnow()
    result = db().canales_notificacion.insert_one(data)
    activity('channel.created',user,request,{'channel_id':str(result.inserted_id)})
    return public(data)

@app.post('/api/channels/{id}/test')
def channel_test(id:str,request:Request,user=Depends(require('DBA','SOPORTE'))):
    channel = db().canales_notificacion.find_one({'_id':oid(id)})
    if not channel:
        raise HTTPException(404,'Canal inexistente')
    try:
        send_channel(channel,'success','Notificación de prueba NORECOV')
    except Exception as exc:
        raise HTTPException(400,f'El canal no respondió correctamente: {str(exc)[:300]}')
    db().canales_notificacion.update_one({'_id':oid(id)},{'$set':{'enabled':True}})
    activity('channel.tested',user,request,{'channel_id':id})
    return {'ok':True,'enabled':True}

@app.get('/api/alerts')
def alerts(user=Depends(current_user)):
    return list_data('alertas',order='at')

@app.get('/api/audit')
def audits(user=Depends(require('DBA','AUDITOR'))):
    return list_data('audit_logs',order='at',limit=300)

@app.get('/api/audit.csv')
def audits_csv(request:Request,user=Depends(require('DBA','AUDITOR'))):
    rows = list_data('audit_logs',order='at',limit=3000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['fecha','actor','accion','ip','detalle_json'])
    import json
    for r in rows:
        writer.writerow([r.get('at'),r.get('actor'),r.get('action'),r.get('ip'),json.dumps(r.get('detail'),ensure_ascii=False)])
    activity('audit.exported',user,request,{'count':len(rows)})
    return PlainTextResponse(output.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="norecov-auditoria.csv"'})

@app.get('/api/users')
def users(user=Depends(require('DBA'))):
    return list_data('usuarios')

@app.post('/api/users',status_code=201)
def user_create(body:UserCreate,request:Request,user=Depends(require('DBA'))):
    if body.role == 'DBA_MASTER' and user['role'] != 'DBA_MASTER':
        raise HTTPException(403,'Solo DBA Master crea administradores Master')
    record = {'email':body.email.strip().lower(),'name':body.name,'password_hash':hash_password(body.password),
        'role':body.role,'enabled':True,'created_at':utcnow()}
    try:
        result = db().usuarios.insert_one(record)
    except DuplicateKeyError:
        raise HTTPException(409,'El correo ya está registrado')
    activity('user.created',user,request,{'user_id':str(result.inserted_id),'role':body.role})
    return public(record)

@app.patch('/api/users/{id}')
def user_update(id:str,body:UserUpdate,request:Request,user=Depends(require('DBA'))):
    target = db().usuarios.find_one({'_id':oid(id)})
    if not target:
        raise HTTPException(404,'Usuario no encontrado')
    if target['role']=='DBA_MASTER' and user['role']!='DBA_MASTER':
        raise HTTPException(403,'Solo DBA Master administra otros Master')
    update = body.model_dump(exclude_none=True)
    if update.get('role') == 'DBA_MASTER' and user['role']!='DBA_MASTER':
        raise HTTPException(403,'Solo DBA Master asigna este rol')
    if str(user['_id']) == id and update.get('enabled') is False:
        raise HTTPException(409,'No puedes desactivar tu propia sesión')
    if update:
        db().usuarios.update_one({'_id':oid(id)},{'$set':update})
    activity('user.updated',user,request,{'user_id':id,'fields':list(update)})
    return public(db().usuarios.find_one({'_id':oid(id)}))

@app.post('/api/retention/run',status_code=202)
def retention_now(request:Request,user=Depends(require('DBA'))):
    job_id = enqueue('retention','system',actor(user))
    activity('retention.requested',user,request,{'job_id':job_id})
    return {'job_id':job_id,'status':'queued'}
