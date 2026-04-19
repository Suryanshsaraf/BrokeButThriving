from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "BrokeButThriving API"
    api_prefix: str = "/api/v1"
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'bbt.db'}"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"]
    artifacts_root: Path = PROJECT_ROOT / "artifacts"
    public_benchmark_runs_root: Path = artifacts_root / "public-benchmark-runs"
    sequence_runs_root: Path = artifacts_root / "sequence-runs"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "llama-3.3-70b-versatile"

    model_config = SettingsConfigDict(env_prefix="BBT_", env_file=".env", extra="ignore")


settings = Settings()
