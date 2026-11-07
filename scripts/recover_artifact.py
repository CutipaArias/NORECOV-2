"""Descifra respaldos para recuperación controlada en un host confiable.
Usar fuera de producción primero; no subas el archivo resultante a Git.
"""
import argparse
import base64
import os
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

parser = argparse.ArgumentParser()
parser.add_argument('--input',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
key=os.environ.get('ENCRYPTION_KEY')
if not key:
    raise SystemExit('Falta variable ENCRYPTION_KEY. NO escribirla en el código.')
raw=base64.urlsafe_b64decode(key)
if len(raw)!=32:
    raise SystemExit('Clave AES-256 inválida')
source=Path(args.input)
if source.resolve()==Path(args.output).resolve():
    raise SystemExit('Entrada y salida deben ser diferentes')
with source.open('rb') as f:
    if f.read(8)!=b'NORECOV1':
        raise SystemExit('Cabecera NORECOV inválida')
    nonce=f.read(12)
    f.seek(-16,2)
    tag=f.read(16)
    remaining=source.stat().st_size-8-12-16
    dec=Cipher(algorithms.AES(raw),modes.GCM(nonce,tag)).decryptor()
    f.seek(20)
    try:
        with open(args.output,'xb') as out:
            while remaining:
                buf=f.read(min(1024*1024,remaining))
                if not buf: raise ValueError('Archivo truncado')
                remaining-=len(buf)
                out.write(dec.update(buf))
            out.write(dec.finalize())
    except Exception:
        Path(args.output).unlink(missing_ok=True)
        raise
print('Descifrado e integridad GCM verificados:',args.output)
