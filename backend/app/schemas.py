from typing import Literal
from pydantic import BaseModel, Field, EmailStr

Engine = Literal['mongodb','redis']
Role = Literal['DBA_MASTER','DBA','DEVOPS','SOPORTE','AUDITOR']

class Login(BaseModel):
    email: str
    password: str

class NodeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    engine: Engine
    host: str = Field(min_length=1, max_length=253, pattern=r'^[a-zA-Z0-9._-]+$')
    port: int = Field(ge=1, le=65535)
    username: str = ''
    password: str = ''
    database: str = ''
    auth_db: str = 'admin'
    tls: bool = False

class PlanCreate(BaseModel):
    node_id: str
    name: str = Field(min_length=2, max_length=100)
    cron: str = '*/10 * * * *'
    retention_days: int = Field(default=30, ge=1, le=3650)
    active: bool = True
    repository_id: str | None = None

class UserCreate(BaseModel):
    email: str
    name: str = Field(min_length=2)
    password: str = Field(min_length=10)
    role: Role

class UserUpdate(BaseModel):
    enabled: bool | None = None
    role: Role | None = None

class RepositoryCreate(BaseModel):
    name: str = Field(min_length=2)
    kind: Literal['local','s3']
    endpoint: str = ''
    bucket: str = ''
    region: str = 'us-east-1'
    access_key: str = ''
    secret_key: str = ''
    object_lock: bool = False

class ChannelCreate(BaseModel):
    name: str
    kind: Literal['webhook','smtp']
    destination: str
    severities: list[str] = ['critical','warning','success']
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_username: str = ''
    smtp_password: str = ''
