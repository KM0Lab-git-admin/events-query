"""
Configuración de la aplicación Events Query API.
Carga variables de entorno y proporciona configuración centralizada.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Configuración de la aplicación."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
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
    api_port: int = 8000
    api_debug: bool = False
    api_reload: bool = False
    
    # Application Configuration
    app_name: str = "Events Query API"
    app_version: str = "1.0.0"
    app_description: str = "API de búsqueda de eventos con lenguaje natural"
    environment: str = "development"
    
    # Logging
    log_level: str = "INFO"
    
    @property
    def database_url(self) -> str:
        """Construye la URL de conexión a la base de datos."""
        return f"mysql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def is_production(self) -> bool:
        """Verifica si el entorno es producción."""
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Verifica si el entorno es desarrollo."""
        return self.environment.lower() == "development"


# Instancia global de configuración
settings = Settings()
