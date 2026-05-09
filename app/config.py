"""
Configuración de la aplicación Events Query API.
Carga variables de entorno y proporciona configuración centralizada.
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices, model_validator


class Settings(BaseSettings):
    """Configuración de la aplicación."""

    model_config = SettingsConfigDict(
        env_file=".env",                 # en Railway no suele existir; si no está, no pasa nada
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",                  # RAILWAY_DB_* y otras vars solo para scripts PowerShell
    )

    # Database Configuration
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "events_user"
    db_password: str = "events_password"
    db_name: str = "events_db"
    db_pool_min_size: int = 5
    db_pool_max_size: int = 20

    # OpenAI Configuration
    openai_api_key: str
    openai_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_timeout: int = 30
    openai_max_retries: int = 3

    # API Configuration
    api_host: str = "0.0.0.0"
    # Permite API_PORT o PORT (Railway)
    api_port: int = Field(default=8000, validation_alias=AliasChoices("API_PORT", "PORT"))
    api_debug: bool = False
    api_reload: bool = False

    # Application Configuration
    app_name: str = "Events Query API"
    app_version: str = "1.0.0"
    app_description: str = "API de búsqueda de eventos con lenguaje natural"
    environment: str = "development"  # <-- en Railway ponlo a "production"

    # Logging
    log_level: str = "INFO"

    @property
    def database_url(self) -> str:
        """Construye la URL de conexión a la base de datos."""
        return f"mysql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

    @model_validator(mode="after")
    def _validate_non_local_db(self):
        """
        Regla de oro:
        - En local puedes usar defaults.
        - Fuera de local, NO se permite localhost y NO se permite faltar DB_*.
        """
        env = (self.environment or "").lower()

        if env != "local":
            # 1) No permitir localhost (ni 127.0.0.1) en Railway/producción
            if self.db_host.lower() in ("localhost", "127.0.0.1"):
                raise ValueError(
                    "DB_HOST está en localhost/127.0.0.1 pero ENVIRONMENT != local. "
                    "En Railway debes setear DB_HOST (y DB_*) con reference variables del servicio MySQL."
                )

            # 2) Validar que los esenciales estén presentes (por si alguien borra algo)
            missing = []
            for key, value in [
                ("DB_HOST", self.db_host),
                ("DB_PORT", self.db_port),
                ("DB_USER", self.db_user),
                ("DB_PASSWORD", self.db_password),
                ("DB_NAME", self.db_name),
            ]:
                if value is None or (isinstance(value, str) and not value.strip()):
                    missing.append(key)

            if missing:
                raise ValueError(f"Faltan variables de BD para ENVIRONMENT={env}: {', '.join(missing)}")

        return self


# Instancia global de configuración
settings = Settings()
