"""
Servicio de IA para interactuar con OpenAI.
Incluye extracción de parámetros, generación de embeddings y respuestas naturales.
"""

import hashlib
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import date
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

Expresiones temporales (viernes, sábado y domingo = fin de semana):
- "este fin de semana" / "este finde": viernes, sábado y domingo de la semana actual o próxima
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
            
            # Fallback: si no hay fechas pero la pregunta menciona "fin de semana", calcular
            pregunta_lower = pregunta.lower()
            if not params.fechas and not params.fecha_inicio and not params.fecha_fin:
                if any(x in pregunta_lower for x in ["fin de semana", "finde", "este finde", "este fin de semana"]):
                    fechas_finde = self._calcular_fechas_fin_de_semana(hoy)
                    if fechas_finde:
                        params.fechas = fechas_finde
                        logger.info(f"Fallback: fechas fin de semana = {fechas_finde}")
            
            logger.info(f"Parámetros extraídos: idioma={params.idioma}, categorias={params.categorias}, conceptos={params.conceptos}")
            
            return params
            
        except Exception as e:
            logger.error(f"Error al extraer parámetros: {e}")
            # Fallback: parámetros por defecto
            params = ExtractedParameters(
                idioma="es" if any(word in pregunta.lower() for word in ["qué", "dónde", "cuándo"]) else "ca",
                conceptos=[pregunta]
            )
            # Fallback fechas fin de semana
            if any(x in pregunta.lower() for x in ["fin de semana", "finde", "este finde"]):
                params.fechas = self._calcular_fechas_fin_de_semana(datetime.now().date())
            return params
    
    def _calcular_fechas_fin_de_semana(self, hoy: date) -> List[date]:
        """Calcula viernes, sábado y domingo del fin de semana actual o próximo."""
        wd = hoy.weekday()  # 0=lunes, 4=viernes, 5=sábado, 6=domingo
        if wd <= 3:  # lunes a jueves: próximo viernes, sábado, domingo
            dias_hasta_viernes = 4 - wd
            viernes = hoy + timedelta(days=dias_hasta_viernes)
            return [viernes, viernes + timedelta(days=1), viernes + timedelta(days=2)]
        elif wd == 4:  # viernes: hoy, sábado, domingo
            return [hoy, hoy + timedelta(days=1), hoy + timedelta(days=2)]
        elif wd == 5:  # sábado: hoy, domingo
            return [hoy, hoy + timedelta(days=1)]
        else:  # domingo: solo hoy
            return [hoy]
    
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
        
        # Solo eventos con alta coincidencia (mayor) para el mensaje al usuario
        eventos_mayor = [e for e in eventos if getattr(e, 'nivel_coincidencia', None) == 'mayor']
        eventos_para_resumen = eventos_mayor if eventos_mayor else eventos

        # Preparar resumen de eventos para el prompt (incluir rango de fechas para recurrentes)
        eventos_resumen = []
        for i, evento in enumerate(eventos_para_resumen[:5], 1):  # Solo los primeros 5 para el prompt
            resumen = f"{i}. {evento.titulo} - {evento.poblacion_nombre}"
            if evento.fecha_inicio and evento.fecha_fin:
                resumen += f" (del {evento.fecha_inicio} al {evento.fecha_fin})"
            elif evento.fecha_fin:
                resumen += f" (hasta el {evento.fecha_fin})"
            elif evento.fecha_inicio:
                resumen += f" ({evento.fecha_inicio})"
            if evento.es_gratuito:
                resumen += " [GRATUITO]"
            eventos_resumen.append(resumen)
        
        num_alta = len(eventos_mayor)
        lang = "catalán" if idioma == "ca" else "español"
        system_prompt = f"""Eres un asistente que ayuda a encontrar eventos.
Genera la respuesta en {lang}.

Instrucciones de redacción (OBLIGATORIO):
- RESPONDE SOLO CON 1 O 2 FRASES. No escribas más.
- PROHIBIDO: saludos iniciales, despedidas (ej. "¡Que lo disfrutes!"), preguntas finales, relleno.
- Menciona solo lo esencial: ciudad/fecha (si aplica) + 2–4 eventos más relevantes.
- Resalta cada título de evento en **negrita** (Markdown).
- Tono: directo, claro, informativo.

Reglas de contenido:
- NO menciones el número total de eventos de la lista completa (p. ej. "100 eventos").
- Menciona SOLO los eventos con alta coincidencia en tags y categorías (los que te paso a continuación). Si hay {num_alta} con alta coincidencia, habla solo de esos.
- Para eventos con varias fechas o recurrentes (tienen "del X al Y" o "hasta el Y"), indica el periodo activo (p. ej. "hasta el Y") cuando aplique.

NO inventes información. Solo usa los datos proporcionados."""

        user_prompt = f"""Pregunta del usuario: "{pregunta}"

Eventos con alta coincidencia ({num_alta}):
{chr(10).join(eventos_resumen) if eventos_resumen else '(ninguno con alta coincidencia)'}

Responde en 1 o 2 frases, títulos en **negrita**, solo 2–4 eventos. Sin saludo ni despedida."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.35,
                max_tokens=100
            )
            
            respuesta = response.choices[0].message.content.strip()
            logger.info(f"Respuesta generada en {idioma}: {len(respuesta)} caracteres")
            
            return respuesta
            
        except Exception as e:
            logger.error(f"Error al generar respuesta: {e}")
            # Fallback: respuesta simple (sin citar total)
            if idioma == "ca":
                return "He trobat esdeveniments que coincideixen en tags i categories amb la teva cerca."
            else:
                return "He encontrado eventos que coinciden en tags y categorías con tu búsqueda."


# Instancia global del servicio
ai_service = AIService()
