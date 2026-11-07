from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    control_mongo_uri: str
    control_db: str = 'norecov'
    secret_key: str
    encryption_key: str
    admin_email: str = 'admin@norecov.local'
    admin_password: str
    artifact_dir: str = '/data/artifacts'
    cors_origins: str = 'http://localhost:5173,http://localhost:8080'
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

@lru_cache
def settings():
    return Settings()
