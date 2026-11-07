"""Pruebas de orquestación con daemon Docker falso (no acredita Docker real)."""
import base64
import sys
import types
import pytest
from app.config import settings
from app.crypto import encrypt_chunks
from app.sandbox import validate_artifact

class FakeExec:
    def __init__(self,code=0,out=b'PONG',err=b''):
        self.exit_code=code
        self.output=(out,err)

class FakeContainer:
    id='test-sandbox'
    def __init__(self):
        self.commands=[]
        self.deleted=False
    def exec_run(self, command,demux=True):
        self.commands.append(command)
        if command[0]=='mongosh' and '--eval' in command and 'db.adminCommand' not in command[-1]:
            return FakeExec(out=b'{"norecov_demo":{"libros":3}}')
        if command[0]=='mongosh':
            return FakeExec(out=b'1')
        if command[0]=='redis-cli' and 'INFO' in command:
            return FakeExec(out=b'# Keyspace\r\ndb0:keys=3,expires=0,avg_ttl=0\r\n')
        return FakeExec()
    def remove(self,force,v):
        self.deleted=True

class FakeClient:
    def __init__(self,container):
        self.container=container
        self.received=None
        self.containers=self
        self.api=self
        self.launch_options=None
    def run(self,image,command,**kwargs):
        self.launch_options=kwargs
        return self.container
    def put_archive(self,id,where,contents):
        self.received=b''.join(contents)
        return True
    def close(self):
        pass

@pytest.fixture(autouse=True)
def fake_key(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_KEY',base64.urlsafe_b64encode(b'X'*32).decode())
    monkeypatch.setenv('CONTROL_MONGO_URI','mongodb://localhost:27017')
    monkeypatch.setenv('SECRET_KEY','test-secret')
    monkeypatch.setenv('ADMIN_PASSWORD','test-admin-password')
    settings.cache_clear()
    yield
    settings.cache_clear()

@pytest.mark.parametrize('engine,expected',[
 ('mongodb',{'norecov_demo':{'libros':3}}),('redis',{'db0':3})
])
def test_sandbox_isolated_and_cleaned(monkeypatch,tmp_path,engine,expected):
    name='mock.norecov'
    content=b'restored-by-fake-client'
    path=tmp_path/name
    encrypt_chunks([content],path)
    artifact={'engine':engine,'_id':'123','raw_bytes':len(content),'source_counts':expected}
    container=FakeContainer()
    fake=FakeClient(container)
    monkeypatch.setitem(sys.modules,'docker',types.SimpleNamespace(from_env=lambda **kw:fake))
    result=validate_artifact(path,artifact)
    assert result['ok']
    assert container.deleted
    assert fake.launch_options['network_disabled'] is True
    assert fake.launch_options['cap_drop']==['ALL']
    assert content in fake.received
    if engine=='redis':
        assert ['mv','/data/dump.rdb.partial','/data/dump.rdb'] in container.commands


def test_sandbox_always_cleans_after_error(monkeypatch,tmp_path):
    path=tmp_path/'bad.norecov'
    encrypt_chunks([b'abc'],path)
    container=FakeContainer()
    fake=FakeClient(container)
    def break_upload(*args):
        raise RuntimeError('Fallo de transferencia simulado')
    fake.put_archive=break_upload
    monkeypatch.setitem(sys.modules,'docker',types.SimpleNamespace(from_env=lambda **kw:fake))
    with pytest.raises(RuntimeError):
        validate_artifact(path,{'engine':'mongodb','_id':'123','raw_bytes':3,'source_counts':{}})
    assert container.deleted
