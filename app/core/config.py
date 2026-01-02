import os
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_PATH = os.path.dirname(__file__)


class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASS: str
    DB_NAME: str

    PROJECT_NAME: str
    API_V1_STR: str

    DEBAG: bool

    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    model_config = SettingsConfigDict(
        # env_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        env_file='.env'
    )
    # class Config:
    #     env_file = '.env'


settings = Settings()
