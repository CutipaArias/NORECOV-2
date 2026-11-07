"""Inserta datos de prueba en los dos motores DEMO de Docker Compose.
Requiere docker compose --profile demo up -d.
"""
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def run(*args):
    cmd = ['docker','compose','--profile','demo','exec','-T',*args]
    print('>', ' '.join(cmd[:7]), '...')
    subprocess.run(cmd, cwd=ROOT, check=True)

MONGO_SCRIPT = '''const demo=db.getSiblingDB('norecov_demo'); demo.libros.deleteMany({}); demo.libros.insertMany([{titulo:'Bases de datos NoSQL',autor:'Equipo NORECOV',anio:2026},{titulo:'Resiliencia con Docker',autor:'Laboratorio BD2',anio:2026},{titulo:'MongoDB y Redis',autor:'NORECOV',anio:2026}]); demo.eventos.deleteMany({}); demo.eventos.insertMany([{tipo:'backup',ok:true},{tipo:'restore',ok:true}]);print(JSON.stringify({libros:demo.libros.countDocuments({}),eventos:demo.eventos.countDocuments({})}));'''
MONGO_COMMAND = 'mongosh --quiet -u "$DEMO_MONGO_USER" -p "$DEMO_MONGO_PASSWORD" --authenticationDatabase admin --eval ' + "'" + MONGO_SCRIPT.replace("'", "'\\''") + "'"
REDIS_COMMAND = 'REDISCLI_AUTH="$DEMO_REDIS_PASSWORD" redis-cli MSET norecov:libro:1 "NoSQL" norecov:libro:2 "Docker" norecov:estado "correcto"'

if __name__ == '__main__':
    run('mongo-source','sh','-c',MONGO_COMMAND)
    run('redis-source','sh','-c',REDIS_COMMAND)
    print('Datos de prueba listos: MongoDB (3 libros, 2 eventos) y Redis (3 claves).')
