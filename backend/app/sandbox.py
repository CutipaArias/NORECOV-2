"""Sandbox efímero con network_mode=none. Descifrado *en tránsito* hacia Docker API.
No crea archivos descifrados en disco del orquestador.
"""
import json
import tarfile
import time
from pathlib import Path
from .crypto import iter_decrypt, encrypted_payload_size

class SandboxError(Exception):
    pass

def tar_stream(source, filename, uncompressed_bytes):
    """Construye stream TAR para la API put_archive de Docker sin staging plano."""
    info = tarfile.TarInfo(filename)
    info.size = uncompressed_bytes
    info.mode = 0o600
    if filename == 'dump.rdb.partial':
        info.uid = 999
        info.gid = 1000
    yield info.tobuf(format=tarfile.USTAR_FORMAT)
    total = 0
    for data in iter_decrypt(source):
        total += len(data)
        yield data
    if total != uncompressed_bytes:
        raise SandboxError('Tamaño de plaintext incongruente')
    if pad := ((512 - total % 512) % 512):
        yield b'\0' * pad
    yield b'\0' * 1024

def exec_checked(container, command):
    result = container.exec_run(command, demux=True)
    stdout, stderr = result.output or (b'', b'')
    stdout = stdout or b''
    stderr = stderr or b''
    if result.exit_code:
        raise SandboxError(f'Error de comando en Sandbox: {(stderr or stdout or b"").decode(errors="replace")[:1500]}')
    return stdout.decode(errors='replace').strip()

def wait_ready(container, engine):
    cmd = ['mongosh','--host','127.0.0.1','--quiet','--eval','db.adminCommand({ping:1}).ok'] if engine == 'mongodb' else ['redis-cli','-h','127.0.0.1','ping']
    for _ in range(60):
        try:
            value = exec_checked(container, cmd)
            if '1' in value or 'PONG' in value:
                return
        except Exception:
            pass
        time.sleep(1)
    raise SandboxError('Sandbox no respondió en 60 segundos')

def validate_mongo(container, expected):
    script = r'''const out={}; for(const name of db.getMongo().getDBNames()){if(['admin','config','local'].includes(name))continue;const d=db.getSiblingDB(name);out[name]={};for(const c of d.getCollectionInfos({type:'collection'})){out[name][c.name]=d.getCollection(c.name).countDocuments({});}}print(EJSON.stringify(out));'''
    output = exec_checked(container, ['mongosh','--host','127.0.0.1','--quiet','--eval',script])
    return json.loads(output.splitlines()[-1])

def validate_redis(container):
    output = exec_checked(container, ['redis-cli','-h','127.0.0.1','INFO','keyspace'])
    result = {}
    for line in output.splitlines():
        if line.startswith('db') and ':keys=' in line:
            k, v = line.split(':', 1)
            result[k] = int(v.split('keys=')[1].split(',')[0])
    return result

def validate_artifact(path, artifact):
    import docker
    engine = artifact['engine']
    image = 'mongo:6.0' if engine == 'mongodb' else 'redis:7.0-alpine'
    docker_client = docker.from_env(timeout=180)
    container = None
    start = time.monotonic()
    try:
        if engine == 'mongodb':
            command = ['mongod','--bind_ip','127.0.0.1']
        else:
            command = ['sh','-c', 'until test -f /data/dump.rdb; do sleep 0.2; done; exec redis-server --bind 127.0.0.1 --protected-mode no --save "" --appendonly no --dir /data --dbfilename dump.rdb']
        container = docker_client.containers.run(
            image, command=command, detach=True, network_disabled=True, auto_remove=False,
            user=('redis' if engine == 'redis' else None),
            mem_limit='1024m', nano_cpus=1000000000, pids_limit=128,
            cap_drop=['ALL'], cap_add=(['CHOWN','SETUID','SETGID'] if engine == 'mongodb' else []), security_opt=['no-new-privileges'],
            labels={'norecov.sandbox':'true','norecov.artifact':str(artifact['_id'])})
        if engine == 'mongodb':
            wait_ready(container, engine)
        name = 'restore.archive' if engine == 'mongodb' else 'dump.rdb.partial'
        directory = '/tmp' if engine == 'mongodb' else '/data'
        docker_client.api.put_archive(container.id, directory, tar_stream(path, name, artifact['raw_bytes']))
        if engine == 'mongodb':
            exec_checked(container, ['mongorestore','--host','127.0.0.1','--archive=/tmp/restore.archive','--gzip','--drop'])
            actual = validate_mongo(container, artifact['source_counts'])
        else:
            # El servidor Redis espera dump.rdb: renombrar SOLO tras transferir el RDB completo.
            exec_checked(container, ['mv','/data/dump.rdb.partial','/data/dump.rdb'])
            wait_ready(container, engine)
            actual = validate_redis(container)
        expected = artifact['source_counts']
        passed = actual == expected
        return {'ok':passed, 'expected':expected,'actual':actual,
                'rto_ms':round((time.monotonic()-start)*1000),
                'sandbox_image':image}
    finally:
        if container:
            try:
                container.remove(force=True, v=True)
            except Exception:
                pass
        docker_client.close()




