from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = 'ComfyUI Orchestrator'
    API_V1_STR: str = '/api'

    DEBAG: bool = False

    SECRET_KEY: str = 'COMFYUI_FG_2026'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    class Config:
        env_file = '.env'


settings = Settings()
