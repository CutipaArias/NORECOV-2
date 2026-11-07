"""Adaptador Redis 7: RDB mediante redis-cli (protocolo de replicación)."""
import os
import subprocess
import redis
from ..crypto import decrypt_secret

def client(node, db=0):
    return redis.Redis(host=node['host'],port=node['port'],username=node.get('username') or None,
        password=decrypt_secret(node.get('credentials_enc','')) or None, db=db,
        ssl=bool(node.get('tls')), socket_connect_timeout=6, socket_timeout=15)

def verify(node):
    c = client(node)
    version = c.info('server')['redis_version']
    if not version.startswith('7.0.'):
        raise ValueError(f'Redis {version} detectado; esta versión admite Redis 7.0.x')
    return version

def source_counts(node):
    c = client(node)
    info = c.info('keyspace')
    return {key: value['keys'] for key, value in info.items() if key.startswith('db')}

def extract(node):
    env = os.environ.copy()
    password = decrypt_secret(node.get('credentials_enc',''))
    if password:
        env['REDISCLI_AUTH'] = password
    cmd = ['redis-cli', '-h', node['host'], '-p', str(node['port'])]
    if node.get('username'):
        cmd += ['--user', node['username']]
    if node.get('tls'):
        cmd += ['--tls']
    cmd += ['--rdb', '-']  # Redis documenta '-' como salida RDB binaria a stdout
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, bufsize=0)
