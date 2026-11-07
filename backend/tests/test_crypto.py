import base64
import hashlib
import io
import tarfile
import pytest
from cryptography.exceptions import InvalidTag
from app.config import settings
from app.crypto import encrypt_chunks, iter_decrypt, file_sha256
from app.sandbox import tar_stream

@pytest.fixture(autouse=True)
def fake_key(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_KEY',base64.urlsafe_b64encode(b'X'*32).decode())
    monkeypatch.setenv('CONTROL_MONGO_URI','mongodb://localhost:27017')
    monkeypatch.setenv('SECRET_KEY','test-secret')
    monkeypatch.setenv('ADMIN_PASSWORD','test-admin-password')
    settings.cache_clear()
    yield
    settings.cache_clear()

def test_roundtrip_and_sha(tmp_path):
    path=tmp_path/'backup.norecov'
    original=b'RDB-TEST'+(b'mongodb-redis-'*5000)
    meta=encrypt_chunks([original[:5000],original[5000:]],path)
    assert meta['raw_bytes']==len(original)
    assert file_sha256(path)==meta['sha256']
    assert b''.join(iter_decrypt(path))==original
    assert original[:30] not in path.read_bytes()

def test_detects_tag_tampering(tmp_path):
    path=tmp_path/'tampered.norecov'
    encrypt_chunks([b'INTEGRITY'],path)
    data=bytearray(path.read_bytes())
    data[-1]^=0xff
    path.write_bytes(data)
    with pytest.raises(InvalidTag):
        b''.join(iter_decrypt(path))

def test_streamed_tar_has_restoration_file(tmp_path):
    content=b'REDIS0009'+bytes(range(256))*20
    path=tmp_path/'rdb.norecov'
    encrypt_chunks([content],path)
    tar=b''.join(tar_stream(path,'dump.rdb',len(content)))
    with tarfile.open(fileobj=io.BytesIO(tar),mode='r:') as archive:
        assert archive.getnames()==['dump.rdb']
        assert archive.extractfile('dump.rdb').read()==content
