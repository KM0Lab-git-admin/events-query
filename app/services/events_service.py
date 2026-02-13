"""
Servicio principal para búsqueda de eventos.
Orquesta todos los servicios (DB, IA, QueryBuilder) para procesar búsquedas.
"""

import json
import logging
import unicodedata
from datetime import date
from typing import List, Optional, Dict, Any

from app.models.schemas import QueryRequest, QueryResponse, Evento, ExtractedParameters
from app.services.database import db_service
from app.services.ai_service import ai_service
from app.services.query_builder import query_builder
from app.services.analysis_service import analysis_service

logger = logging.getLogger(__name__)


class EventsService:
    """Servicio principal para búsqueda de eventos."""
    
    async def search_events(self, request: QueryRequest) -> QueryResponse:
        """
        Busca eventos basándose en una pregunta en lenguaje natural.
        
        Args:
            request: Request con la pregunta y código postal del usuario
        
        Returns:
            QueryResponse con los eventos encontrados y respuesta natural
        """
        logger.info(f"Búsqueda iniciada: pregunta='{request.pregunta}', cp={request.cp_usuario}")
        
        # Paso 1: Extraer parámetros de la pregunta con IA
        params = await ai_service.extract_parameters(request.pregunta, request.cp_usuario)
        logger.info(f"Parámetros extraídos: {params.model_dump()}")
        
        # Paso 2: Usar SOLO el código postal del usuario (sin expandir por radio)
        codigos_postales = [request.cp_usuario]
        logger.info(f"Usando solo CP del usuario: {codigos_postales}")
        
        # Paso 3: Construir query SQL (relajada si hay búsqueda semántica para ver descartados)
        expand_for_semantic = bool(params.conceptos)
        query, query_params = query_builder.build_events_query(
            codigos_postales, params, expand_for_semantic=expand_for_semantic
        )
        
        # Paso 4: Ejecutar query (pre-filtrado)
        eventos_raw = await db_service.execute_query(query, query_params)
        logger.info(f"Pre-filtrado SQL: {len(eventos_raw)} eventos encontrados")
        
        # Paso 5: Búsqueda semántica si hay conceptos
        eventos_filtrados = await self._semantic_search(
            eventos_raw,
            params.conceptos,
            params.idioma,
            request.cp_usuario,
            categorias_solicitadas=params.categorias or []
        )
        
        # Paso 5b: Post-filtro temporal (descartar eventos fuera del rango)
        eventos_temporales = self._filtrar_por_fechas(eventos_filtrados, params)
        logger.info(f"Post-filtro temporal: {len(eventos_temporales)} eventos (de {len(eventos_filtrados)})")
        
        # Paso 6: Convertir a modelos Pydantic y asignar nivel_coincidencia
        eventos = await self._convert_to_eventos(eventos_temporales, request.cp_usuario)
        logger.info(f"Eventos finales: {len(eventos)}")
        
        # Paso 7: Generar respuesta en lenguaje natural
        respuesta_texto = await ai_service.generate_response(
            request.pregunta,
            eventos,
            params.idioma
        )
        
        # Preparar response
        response = QueryResponse(
            respuesta_texto=respuesta_texto,
            eventos=eventos,
            total=len(eventos),
            idioma_respuesta=params.idioma
        )
        
        # Añadir debug info si se solicita
        if request.debug:
            # Análisis detallado de eventos
            analisis_detallado = []
            if eventos_raw:
                # Usar conceptos si existen, sino usar la pregunta completa
                conceptos_para_analisis = params.conceptos if params.conceptos else [request.pregunta]
                conceptos_text = " ".join(conceptos_para_analisis)
                pregunta_embedding = await ai_service.generate_embedding(conceptos_text)
                
                # Analizar todos los eventos (incluso los que no pasaron)
                analisis_detallado = await analysis_service.analyze_batch(
                    eventos_raw[:20],  # Limitar a 20 para no saturar
                    pregunta_embedding,
                    conceptos_para_analisis,
                    umbral=0.4
                )
            
            response.debug_info = {
                "parametros_extraidos": params.model_dump(),
                "codigos_postales": codigos_postales,
                "sql_query": query,
                "sql_params": query_params,
                "eventos_pre_filtrado": len(eventos_raw),
                "eventos_post_semantica": len(eventos_filtrados),
                "analisis_detallado": analisis_detallado
            }
        
        return response
    
    def _filtrar_por_fechas(
        self,
        eventos: List[Dict[str, Any]],
        params: ExtractedParameters
    ) -> List[Dict[str, Any]]:
        """Descartar eventos cuya fecha_inicio no esté en el rango solicitado."""
        if not params.fechas and not params.fecha_inicio and not params.fecha_fin:
            return eventos
        
        fechas_validas = set()
        if params.fechas:
            for f in params.fechas:
                fechas_validas.add(f if isinstance(f, date) else date.fromisoformat(str(f)))
        elif params.fecha_inicio or params.fecha_fin:
            from datetime import timedelta
            ini = params.fecha_inicio or params.fecha_fin
            fin = params.fecha_fin or params.fecha_inicio
            if isinstance(ini, str):
                ini = date.fromisoformat(ini)
            if isinstance(fin, str):
                fin = date.fromisoformat(fin)
            d = ini
            while d <= fin:
                fechas_validas.add(d)
                d += timedelta(days=1)
        
        if not fechas_validas:
            return eventos
        
        resultado = []
        for ev in eventos:
            fi = ev.get('fecha_inicio')
            if not fi:
                continue
            if hasattr(fi, 'date'):
                fi = fi.date()
            elif isinstance(fi, str):
                fi = date.fromisoformat(fi[:10]) if len(fi) >= 10 else None
            if fi and fi in fechas_validas:
                resultado.append(ev)
        
        return resultado
    
    def _normalizar_categoria_a_slug(self, nombre: str) -> str:
        """Convierte nombre de categoría (ej. 'Cultura', 'Gastronomía') a slug (cultura, gastronomia)."""
        if not nombre or not isinstance(nombre, str):
            return ""
        s = nombre.strip().lower()
        s = "".join(c for c in s if c.isalnum() or c in " _")
        s = s.replace(" ", "_")
        # Normalizar acentos a ASCII para coincidir con slugs de BD
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        return s or ""

    async def _semantic_search(
        self,
        eventos_raw: List[Dict[str, Any]],
        conceptos: List[str],
        idioma: str,
        cp_usuario: str,
        categorias_solicitadas: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Realiza búsqueda semántica sobre los eventos pre-filtrados.
        Si la categoría del evento coincide con una categoría solicitada, el score
        se refuerza para superar el umbral (categoría tiene más peso que tags).
        
        Args:
            eventos_raw: Eventos del pre-filtrado SQL
            conceptos: Conceptos para búsqueda semántica
            idioma: Idioma ('es' o 'ca')
            cp_usuario: Código postal del usuario
            categorias_solicitadas: Categorías extraídas de la pregunta (ej. ['Cultura'])
        
        Returns:
            Lista de eventos con score, ordenados por similitud
        """
        if not conceptos or not eventos_raw:
            return eventos_raw
        
        # Slugs de categorías solicitadas (ej. ['Cultura'] -> {'cultura'})
        slugs_solicitados = set()
        for cat in (categorias_solicitadas or []):
            slug = self._normalizar_categoria_a_slug(cat)
            if slug:
                slugs_solicitados.add(slug)
        
        # Generar embedding de los conceptos del usuario
        conceptos_text = " ".join(conceptos)
        user_embedding = await ai_service.generate_embedding(conceptos_text)
        
        # Cache de embeddings por categoría (evita llamadas repetidas)
        slug_to_expanded = {
            "cultura": "cultura arte museo exposición concierto",
            "deportes": "deportes ejercicio actividad física",
            "ocio": "ocio entretenimiento diversión",
            "infantil": "infantil niños familia",
            "formacion": "formación taller curso aprendizaje",
            "gastronomia": "gastronomía comida restaurante culinaria",
            "musica": "música concierto musical",
            "naturaleza": "naturaleza jardinería plantas aire libre"
        }
        cat_embeddings_cache: Dict[str, List[float]] = {}
        
        # Calcular similitud con cada evento (categoría 40%, tags 60%)
        eventos_con_score = []
        for evento in eventos_raw:
            embedding_json = evento.get('tags_embedding_json')
            sim_tags = 0.3  # default si no hay embedding
            
            if embedding_json:
                try:
                    if isinstance(embedding_json, str):
                        evento_embedding = json.loads(embedding_json)
                    else:
                        evento_embedding = embedding_json
                    sim_tags = ai_service.cosine_similarity(user_embedding, evento_embedding)
                except Exception as e:
                    logger.warning(f"Error al procesar embedding del evento {evento.get('id_unico_evento')}: {e}")
            
            # Similitud por categoría de producto (peso 40%)
            sim_cat = 0.0
            cat_slug = evento.get('categoria_slug')
            if cat_slug:
                if cat_slug not in cat_embeddings_cache:
                    cat_text = slug_to_expanded.get(cat_slug, cat_slug)
                    cat_embeddings_cache[cat_slug] = await ai_service.generate_embedding(cat_text)
                cat_embedding = cat_embeddings_cache[cat_slug]
                sim_cat = ai_service.cosine_similarity(user_embedding, cat_embedding)
            
            # Combinar: 40% categoría, 60% tags (categoría más relevante que tags)
            if cat_slug:
                score = 0.4 * sim_cat + 0.6 * sim_tags
            else:
                score = sim_tags
            
            # Refuerzo si categoría solicitada coincide
            if slugs_solicitados and cat_slug in slugs_solicitados:
                score = max(score, 0.45)
            
            evento['similitud_score'] = round(score, 4)
            eventos_con_score.append(evento)
        
        # Ordenar por similitud descendente (sin filtrar por umbral)
        # Esto permite mostrar todos los eventos: primero los que pasan el filtro, luego los que no
        eventos_filtrados = sorted(eventos_con_score, key=lambda x: x['similitud_score'], reverse=True)
        
        # Contar cuántos pasan el umbral para logging
        eventos_que_pasan = [e for e in eventos_filtrados if e['similitud_score'] >= 0.4]
        logger.info(f"Búsqueda semántica: {len(eventos_que_pasan)} eventos con similitud >= 0.4 de {len(eventos_filtrados)} totales")
        
        return eventos_filtrados
    
    async def _convert_to_eventos(
        self,
        eventos_raw: List[Dict[str, Any]],
        cp_usuario: str
    ) -> List[Evento]:
        """
        Convierte eventos raw de la BD a modelos Pydantic Evento.
        
        Args:
            eventos_raw: Eventos raw de la base de datos
            cp_usuario: Código postal del usuario (para calcular distancia)
        
        Returns:
            Lista de modelos Evento
        """
        eventos = []
        
        logger.info(f"Iniciando conversion de {len(eventos_raw)} eventos raw a modelos Pydantic")
        
        # Obtener coordenadas del usuario
        coords_usuario = await db_service.get_coordenadas_cp(cp_usuario)
        
        for evento_raw in eventos_raw:
            try:
                # Parsear tags JSON
                tags_json = evento_raw.get('tags_json')
                if tags_json:
                    if isinstance(tags_json, str):
                        tags = json.loads(tags_json)
                    else:
                        tags = tags_json
                else:
                    tags = []
                
                # Calcular distancia si hay coordenadas
                distancia_km = None
                if coords_usuario and evento_raw.get('latitud') and evento_raw.get('longitud'):
                    # Convertir todos los valores a float (pueden venir como Decimal desde MySQL)
                    lat_usuario = float(coords_usuario['lat']) if coords_usuario.get('lat') is not None else None
                    lng_usuario = float(coords_usuario['lng']) if coords_usuario.get('lng') is not None else None
                    lat_evento = float(evento_raw['latitud']) if evento_raw.get('latitud') is not None else None
                    lng_evento = float(evento_raw['longitud']) if evento_raw.get('longitud') is not None else None
                    
                    if lat_usuario is not None and lng_usuario is not None and lat_evento is not None and lng_evento is not None:
                        distancia_km = self._calculate_distance(
                            lat_usuario,
                            lng_usuario,
                            lat_evento,
                            lng_evento
                        )
                
                # Validar campos requeridos (COMENTADO TEMPORALMENTE PARA DEBUGGING)
                # if not evento_raw.get('id_unico_evento'):
                #     logger.warning(f"Evento sin ID, saltando")
                #     continue
                # 
                # if not evento_raw.get('titulo'):
                #     logger.warning(f"Evento {evento_raw.get('id_unico_evento')} sin título, saltando")
                #     continue
                
                # Asignar nivel_coincidencia según score
                score = evento_raw.get('similitud_score', 0.0)
                if score >= 0.55:
                    nivel = "mayor"
                elif score >= 0.40:
                    nivel = "templada"
                elif score >= 0.25:
                    nivel = "baja"
                else:
                    nivel = "muy_poca"
                
                # Crear modelo Evento
                evento = Evento(
                    id_unico_evento=str(evento_raw['id_unico_evento']),
                    titulo=str(evento_raw['titulo']),
                    descripcion_corta=evento_raw.get('descripcion_corta'),
                    descripcion_larga=evento_raw.get('descripcion_larga'),
                    cp_evento=str(evento_raw.get('cp_evento', '')),
                    poblacion_nombre=str(evento_raw.get('poblacion_nombre', '')),
                    lugar_nombre=evento_raw.get('lugar_nombre'),
                    direccion_completa=evento_raw.get('direccion_completa'),
                    fecha_inicio=evento_raw.get('fecha_inicio'),
                    fecha_fin=evento_raw.get('fecha_fin'),
                    hora_inicio=str(evento_raw['hora_inicio']) if evento_raw.get('hora_inicio') else None,
                    hora_fin=str(evento_raw['hora_fin']) if evento_raw.get('hora_fin') else None,
                    es_gratuito=bool(evento_raw.get('es_gratuito', False)),
                    precio_euros=float(evento_raw['precio_euros']) if evento_raw.get('precio_euros') else None,
                    categorias=[],  # TODO: Cargar desde relación N:M
                    tags=tags,
                    url_evento=evento_raw.get('url_evento'),
                    url_imagen=evento_raw.get('url_imagen'),
                    distancia_km=round(distancia_km, 2) if distancia_km else None,
                    similitud_score=round(evento_raw.get('similitud_score', 0.0), 3),
                    nivel_coincidencia=nivel
                )
                
                eventos.append(evento)
                logger.debug(f"Evento {evento.id_unico_evento} convertido exitosamente")
                
            except Exception as e:
                error_msg = f"Error al convertir evento {evento_raw.get('id_unico_evento')}: {e}"
                logger.error(error_msg)
                logger.error(f"Datos del evento: {evento_raw}")
                logger.exception("Stack trace completo:")
                
                logger.error(f"Tipo de error: {type(e).__name__}")
                
                continue
        
        logger.info(f"Conversion completada: {len(eventos)}/{len(eventos_raw)} eventos convertidos")
        
        return eventos
    
    def _calculate_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """
        Calcula la distancia entre dos coordenadas usando la fórmula de Haversine.
        
        Args:
            lat1, lon1: Coordenadas del primer punto
            lat2, lon2: Coordenadas del segundo punto
        
        Returns:
            Distancia en kilómetros
        """
        import math
        
        R = 6371  # Radio de la Tierra en km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lon / 2) ** 2)
        
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        distance = R * c
        
        return distance


# Instancia global del servicio
events_service = EventsService()
