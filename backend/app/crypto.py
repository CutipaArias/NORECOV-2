"""Formato NORECOV1: cabecera(8) | nonce(12) | ciphertext(n) | tag GCM(16).
No crea respaldos intermedios sin cifrar en el disco de NORECOV.
"""
import base64
import hashlib
import os
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .config import settings

MAGIC = b'NORECOV1'
NONCE_LENGTH = 12
TAG_LENGTH = 16
CHUNK = 1024 * 1024

def key():
    raw = base64.urlsafe_b64decode(settings().encryption_key)
    if len(raw) != 32:
        raise ValueError('ENCRYPTION_KEY debe contener 32 bytes en base64')
    return raw

def encrypt_secret(secret: str) -> str:
    if not secret:
        return ''
    nonce = os.urandom(NONCE_LENGTH)
    data = AESGCM(key()).encrypt(nonce, secret.encode(), None)
    return base64.urlsafe_b64encode(nonce + data).decode()

def decrypt_secret(value: str) -> str:
    if not value:
        return ''
    data = base64.urlsafe_b64decode(value)
    return AESGCM(key()).decrypt(data[:NONCE_LENGTH], data[NONCE_LENGTH:], None).decode()

def encrypt_chunks(chunks, destination):
    """Consume los bytes comprimidos del extractor y los cifra en flujo."""
    nonce = os.urandom(NONCE_LENGTH)
    enc = Cipher(algorithms.AES(key()), modes.GCM(nonce)).encryptor()
    sha = hashlib.sha256()
    total_plain = 0
    with open(destination, 'wb') as output:
        prefix = MAGIC + nonce
        output.write(prefix)
        sha.update(prefix)
        for part in chunks:
            if not part:
                continue
            total_plain += len(part)
            ciphertext = enc.update(part)
            output.write(ciphertext)
            sha.update(ciphertext)
        tail = enc.finalize()
        if tail:
            output.write(tail)
            sha.update(tail)
        output.write(enc.tag)
        sha.update(enc.tag)
    return {'sha256': sha.hexdigest(), 'raw_bytes': total_plain, 'size_bytes': Path(destination).stat().st_size}

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()

def iter_decrypt(path):
    """Generador de plaintext; verifica GCM al terminar. No usar sin consumir completo."""
    with open(path, 'rb') as f:
        if f.read(8) != MAGIC:
            raise ValueError('Cabecera de artefacto inválida')
        nonce = f.read(NONCE_LENGTH)
        f.seek(0, 2)
        end = f.tell()
        if end < 8 + NONCE_LENGTH + TAG_LENGTH:
            raise ValueError('Artefacto truncado')
        f.seek(end - TAG_LENGTH)
        tag = f.read(TAG_LENGTH)
        dec = Cipher(algorithms.AES(key()), modes.GCM(nonce, tag)).decryptor()
        f.seek(8 + NONCE_LENGTH)
        remaining = end - TAG_LENGTH - 8 - NONCE_LENGTH
        while remaining:
            data = f.read(min(CHUNK, remaining))
            if not data:
                raise ValueError('Artefacto truncado')
            remaining -= len(data)
            yield dec.update(data)
        final = dec.finalize()
        if final:
            yield final

def encrypted_payload_size(path):
    return Path(path).stat().st_size - 8 - NONCE_LENGTH - TAG_LENGTH
