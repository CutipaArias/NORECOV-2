"""Adaptador MongoDB 6: extracción nativa y metadata de colecciones."""
import subprocess
from urllib.parse import quote
from pymongo import MongoClient
from ..crypto import decrypt_secret

SYSTEM_DBS = {'admin', 'config', 'local'}

def uri(node):
    auth = ''
    if node.get('username'):
        auth = quote(node['username'], safe='') + ':' + quote(decrypt_secret(node.get('credentials_enc', '')), safe='') + '@'
    tls = 'true' if node.get('tls') else 'false'
    return f"mongodb://{auth}{node['host']}:{node['port']}/?authSource={quote(node.get('auth_db') or 'admin')}&tls={tls}&serverSelectionTimeoutMS=7000"

def verify(node):
    with MongoClient(uri(node), serverSelectionTimeoutMS=7000) as client:
        info = client.admin.command('buildInfo')
        version = info['version']
        client.admin.command('ping')
    if not version.startswith('6.0.'):
        raise ValueError(f'MongoDB {version} detectado; esta versión admite MongoDB 6.0.x')
    return version

def source_counts(node):
    result = {}
    with MongoClient(uri(node)) as client:
        dbs = [node['database']] if node.get('database') else [name for name in client.list_database_names() if name not in SYSTEM_DBS]
        for name in dbs:
            result[name] = {}
            db = client[name]
            for col in db.list_collection_names(filter={'type':'collection'}):
                result[name][col] = db[col].count_documents({})
    return result

def extract(node):
    cmd = ['mongodump', '--uri', uri(node), '--archive', '--gzip']
    if node.get('database'):
        cmd += ['--db', node['database']]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    return process
