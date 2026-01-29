"""
Servicio de IA para interactuar con OpenAI.
Incluye extracción de parámetros, generación de embeddings y respuestas naturales.
"""

import hashlib
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from openai import AsyncOpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from app.config import settings
from app.models.schemas import ExtractedParameters, Evento

logger = logging.getLogger(__name__)


class AIService:
    """Servicio para interactuar con OpenAI."""
    
    # Cache de embeddings en memoria (reduce llamadas a OpenAI en queries repetidas)
    _embedding_cache: Dict[str, List[float]] = {}
    _cache_max_size: int = 1000  # Máximo de entradas en cache
    
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout
        )
        self.model = settings.openai_model
        self.embedding_model = settings.openai_embedding_model
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def extract_parameters(self, pregunta: str, cp_usuario: str) -> ExtractedParameters:
        """
        Extrae parámetros estructurados de una pregunta en lenguaje natural.
        
        Args:
            pregunta: Pregunta del usuario
            cp_usuario: Código postal del usuario
        
        Returns:
            ExtractedParameters con los parámetros extraídos
        """
        hoy = datetime.now().date()
        
        system_prompt = f"""Eres un asistente que extrae parámetros de búsqueda de eventos.
Fecha actual: {hoy.strftime('%Y-%m-%d')} ({hoy.strftime('%A, %d de %B de %Y')})

Extrae los siguientes parámetros de la pregunta del usuario:
1. idioma: 'es' (español) o 'ca' (catalán) - detecta el idioma de la pregunta
2. fechas: lista de fechas específicas en formato YYYY-MM-DD
3. fecha_inicio y fecha_fin: rango de fechas
4. radio_km: radio en kilómetros (si menciona "cerca", "alrededores", "a la redonda", usa 20km por defecto)
5. categorias: lista de categorías (Cultura, Deportes, Ocio, Infantil, Formación, Gastronomía, Música, Naturaleza)
6. conceptos: lista de conceptos para búsqueda semántica.
   ⚠️ IMPORTANTE: EXPANDE cada concepto con sinónimos y palabras relacionadas en AMBOS idiomas.
   Ejemplos de expansión:
   - "ballar/bailar" → ["ballar", "dansa", "ball", "bailar", "baile", "música", "festa", "fiesta", "discoteca"]
   - "niños/nens" → ["niños", "nens", "infantil", "familia", "familiar", "kids", "pequeños", "petits"]
   - "comer/menjar" → ["comer", "menjar", "gastronomía", "gastronomia", "comida", "restaurante", "cuina", "cocina"]
   - "gratis/gratuït" → ["gratis", "gratuito", "gratuït", "free", "sense cost", "sin coste"]
   - "música" → ["música", "musica", "concierto", "concert", "jazz", "rock", "directo", "directe"]
   - "deporte/esport" → ["deporte", "esport", "deportivo", "esportiu", "ejercicio", "actividad física"]
   Genera SIEMPRE al menos 5-8 conceptos expandidos para mejorar la búsqueda.
7. es_gratuito: true si pide eventos gratuitos
8. precio_max: precio máximo en euros

Expresiones temporales:
- "este fin de semana": próximo sábado y domingo
- "este sábado": próximo sábado
- "mañana": {(hoy + timedelta(days=1)).strftime('%Y-%m-%d')}
- "hoy": {hoy.strftime('%Y-%m-%d')}
- "esta semana": desde hoy hasta el domingo

Responde SOLO con un JSON válido, sin texto adicional."""

        user_prompt = f"""Pregunta: "{pregunta}"
Código postal usuario: {cp_usuario}"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            params_dict = json.loads(content)
            
            # Validar y crear ExtractedParameters
            params = ExtractedParameters(**params_dict)
            
            logger.info(f"Parámetros extraídos: idioma={params.idioma}, categorias={params.categorias}, conceptos={params.conceptos}")
            
            return params
            
        except Exception as e:
            logger.error(f"Error al extraer parámetros: {e}")
            # Fallback: parámetros por defecto
            return ExtractedParameters(
                idioma="es" if any(word in pregunta.lower() for word in ["qué", "dónde", "cuándo"]) else "ca",
                conceptos=[pregunta]
            )
    
    def _get_cache_key(self, text: str) -> str:
        """Genera una clave de cache para un texto."""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def generate_embedding(self, text: str, use_cache: bool = True) -> List[float]:
        """
        Genera un embedding para un texto, con cache opcional.
        
        Args:
            text: Texto a convertir en embedding
            use_cache: Si True, usa cache en memoria para queries repetidas
        
        Returns:
            Lista de floats representando el embedding (1536 dimensiones)
        """
        # Intentar obtener del cache
        if use_cache:
            cache_key = self._get_cache_key(text)
            if cache_key in self._embedding_cache:
                logger.debug(f"Embedding obtenido de cache (key={cache_key[:8]}...)")
                return self._embedding_cache[cache_key]
        
        try:
            response = await self.client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            
            embedding = response.data[0].embedding
            logger.debug(f"Embedding generado: {len(embedding)} dimensiones")
            
            # Guardar en cache (con límite de tamaño)
            if use_cache:
                if len(self._embedding_cache) >= self._cache_max_size:
                    # Eliminar entrada más antigua (FIFO simple)
                    oldest_key = next(iter(self._embedding_cache))
                    del self._embedding_cache[oldest_key]
                self._embedding_cache[cache_key] = embedding
                logger.debug(f"Embedding guardado en cache (size={len(self._embedding_cache)})")
            
            return embedding
            
        except Exception as e:
            logger.error(f"Error al generar embedding: {e}")
            raise
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calcula la similitud coseno entre dos vectores.
        
        Args:
            vec1: Primer vector
            vec2: Segundo vector
        
        Returns:
            Similitud coseno (0 a 1)
        """
        import math
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def generate_response(
        self,
        pregunta: str,
        eventos: List[Evento],
        idioma: str
    ) -> str:
        """
        Genera una respuesta en lenguaje natural basada en los eventos encontrados.
        
        Args:
            pregunta: Pregunta original del usuario
            eventos: Lista de eventos encontrados
            idioma: Idioma de la respuesta ('es' o 'ca')
        
        Returns:
            Respuesta en lenguaje natural
        """
        if not eventos:
            if idioma == "ca":
                return "Ho sento, no he trobat cap esdeveniment que coincideixi amb la teva cerca."
            else:
                return "Lo siento, no he encontrado ningún evento que coincida con tu búsqueda."
        
        # Preparar resumen de eventos para el prompt
        eventos_resumen = []
        for i, evento in enumerate(eventos[:5], 1):  # Solo los primeros 5 para el prompt
            resumen = f"{i}. {evento.titulo} - {evento.poblacion_nombre}"
            if evento.fecha_inicio:
                resumen += f" ({evento.fecha_inicio})"
            if evento.es_gratuito:
                resumen += " [GRATUITO]"
            eventos_resumen.append(resumen)
        
        system_prompt = f"""Eres un asistente que ayuda a encontrar eventos.
Genera una respuesta natural y amigable en {"catalán" if idioma == "ca" else "español"}.

Incluye:
1. Número total de eventos encontrados
2. Breve mención de los eventos más relevantes
3. Tono conversacional y útil

NO inventes información. Solo usa los datos proporcionados."""

        user_prompt = f"""Pregunta del usuario: "{pregunta}"

Eventos encontrados ({len(eventos)} total):
{chr(10).join(eventos_resumen)}

Genera una respuesta natural."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=200
            )
            
            respuesta = response.choices[0].message.content.strip()
            logger.info(f"Respuesta generada en {idioma}: {len(respuesta)} caracteres")
            
            return respuesta
            
        except Exception as e:
            logger.error(f"Error al generar respuesta: {e}")
            # Fallback: respuesta simple
            if idioma == "ca":
                return f"He trobat {len(eventos)} esdeveniments per a tu."
            else:
                return f"He encontrado {len(eventos)} eventos para ti."


# Instancia global del servicio
ai_service = AIService()
