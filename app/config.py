from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    spotify_client_id: str = ""
    spotify_client_secret: str = ""

    db_path: Path = Path("data/audiarr.db")
    download_dir: Path = Path("music")
    temp_dir: Path = Path("data/tmp")

    jwt_secret: str = ""
    admin_api_key: str = ""

    queue_workers: int = 1
    log_level: str = "INFO"

    model_config = {"env_prefix": "AUDIARR_", "env_file": ".env"}


settings = Settings()
