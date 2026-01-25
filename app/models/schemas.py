"""
Modelos Pydantic para requests y responses de la API.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, date


class QueryRequest(BaseModel):
    """Request para búsqueda de eventos."""
    
    pregunta: str = Field(
        ...,
        description="Pregunta en lenguaje natural",
        min_length=3,
        max_length=500,
        examples=["¿Qué hacer este fin de semana?"]
    )
    
    cp_usuario: str = Field(
        ...,
        description="Código postal del usuario",
        pattern=r"^\d{5}$",
        examples=["08380"]
    )
    
    debug: bool = Field(
        default=False,
        description="Activar modo debug (devuelve SQL y parámetros extraídos)"
    )
    
    @field_validator("pregunta")
    @classmethod
    def validate_pregunta(cls, v: str) -> str:
        """Valida y limpia la pregunta."""
        v = v.strip()
        if not v:
            raise ValueError("La pregunta no puede estar vacía")
        return v


class ExtractedParameters(BaseModel):
    """Parámetros extraídos de la pregunta natural."""
    
    idioma: str = Field(description="Idioma detectado: 'es' o 'ca'")
    fechas: Optional[List[date]] = Field(default=None, description="Fechas específicas")
    fecha_inicio: Optional[date] = Field(default=None, description="Fecha de inicio del rango")
    fecha_fin: Optional[date] = Field(default=None, description="Fecha de fin del rango")
    radio_km: Optional[int] = Field(default=None, description="Radio en kilómetros", ge=0, le=100)
    categorias: List[str] = Field(default_factory=list, description="Categorías solicitadas")
    conceptos: List[str] = Field(default_factory=list, description="Conceptos para búsqueda semántica")
    es_gratuito: Optional[bool] = Field(default=None, description="Filtrar solo eventos gratuitos")
    precio_max: Optional[float] = Field(default=None, description="Precio máximo", ge=0)


class Evento(BaseModel):
    """Modelo de un evento."""
    
    id_unico_evento: str
    titulo: str
    descripcion_corta: Optional[str] = None
    descripcion_larga: Optional[str] = None
    cp_evento: str
    poblacion_nombre: str
    lugar_nombre: Optional[str] = None
    direccion_completa: Optional[str] = None
    fecha_inicio: date
    fecha_fin: Optional[date] = None
    hora_inicio: Optional[str] = None
    hora_fin: Optional[str] = None
    es_gratuito: bool
    precio_euros: Optional[float] = None
    categorias: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    url_evento: Optional[str] = None
    url_imagen: Optional[str] = None
    distancia_km: Optional[float] = Field(default=None, description="Distancia desde el usuario")
    similitud_score: Optional[float] = Field(default=None, description="Score de similitud semántica")


class QueryResponse(BaseModel):
    """Response de búsqueda de eventos."""
    
    respuesta_texto: str = Field(description="Respuesta en lenguaje natural")
    eventos: List[Evento] = Field(description="Lista de eventos encontrados")
    total: int = Field(description="Número total de eventos")
    idioma_respuesta: str = Field(description="Idioma de la respuesta: 'es' o 'ca'")
    
    # Campos opcionales para modo debug
    debug_info: Optional[dict] = Field(default=None, description="Información de debug")


class HealthResponse(BaseModel):
    """Response del health check."""
    
    status: str = Field(description="Estado del servicio: 'healthy' o 'unhealthy'")
    version: str = Field(description="Versión de la API")
    timestamp: datetime = Field(description="Timestamp del check")
    checks: dict = Field(description="Estado de cada componente")


class ErrorResponse(BaseModel):
    """Response de error."""
    
    error: str = Field(description="Tipo de error")
    message: str = Field(description="Mensaje de error")
    detail: Optional[str] = Field(default=None, description="Detalle adicional del error")
    timestamp: datetime = Field(description="Timestamp del error")
