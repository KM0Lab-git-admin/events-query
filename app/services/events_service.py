"""
Servicio principal para búsqueda de eventos.
Orquesta todos los servicios (DB, IA, QueryBuilder) para procesar búsquedas.
"""

import json
import logging
from typing import List, Optional, Dict, Any

from app.models.schemas import QueryRequest, QueryResponse, Evento, ExtractedParameters
from app.services.database import db_service
from app.services.ai_service import ai_service
from app.services.query_builder import query_builder

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
        
        # Paso 2: Calcular códigos postales en el radio especificado
        if params.radio_km:
            codigos_postales = await db_service.get_codigos_postales_in_radius(
                request.cp_usuario,
                params.radio_km
            )
            logger.info(f"CPs en radio {params.radio_km}km: {len(codigos_postales)} encontrados")
        else:
            # Solo el CP del usuario
            codigos_postales = [request.cp_usuario]
        
        # Paso 3: Construir query SQL
        query, query_params = query_builder.build_events_query(codigos_postales, params)
        
        # Paso 4: Ejecutar query (pre-filtrado)
        eventos_raw = await db_service.execute_query(query, query_params)
        logger.info(f"Pre-filtrado SQL: {len(eventos_raw)} eventos encontrados")
        
        # Paso 5: Búsqueda semántica si hay conceptos
        eventos_filtrados = await self._semantic_search(
            eventos_raw,
            params.conceptos,
            params.idioma,
            request.cp_usuario
        )
        
        # Paso 6: Convertir a modelos Pydantic
        eventos = await self._convert_to_eventos(eventos_filtrados, request.cp_usuario)
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
            response.debug_info = {
                "parametros_extraidos": params.model_dump(),
                "codigos_postales": codigos_postales,
                "sql_query": query,
                "sql_params": query_params,
                "eventos_pre_filtrado": len(eventos_raw),
                "eventos_post_semantica": len(eventos_filtrados)
            }
        
        return response
    
    async def _semantic_search(
        self,
        eventos_raw: List[Dict[str, Any]],
        conceptos: List[str],
        idioma: str,
        cp_usuario: str
    ) -> List[Dict[str, Any]]:
        """
        Realiza búsqueda semántica sobre los eventos pre-filtrados.
        
        Args:
            eventos_raw: Eventos del pre-filtrado SQL
            conceptos: Conceptos para búsqueda semántica
            idioma: Idioma ('es' o 'ca')
            cp_usuario: Código postal del usuario
        
        Returns:
            Lista de eventos filtrados por similitud semántica
        """
        if not conceptos or not eventos_raw:
            return eventos_raw
        
        # Generar embedding de los conceptos del usuario
        conceptos_text = " ".join(conceptos)
        user_embedding = await ai_service.generate_embedding(conceptos_text)
        
        # Calcular similitud con cada evento
        eventos_con_score = []
        for evento in eventos_raw:
            # Obtener embedding del evento según idioma
            embedding_json = evento.get('tags_embedding_json')
            
            if not embedding_json:
                # Si no hay embedding, asignar score bajo
                evento['similitud_score'] = 0.3
                eventos_con_score.append(evento)
                continue
            
            try:
                # Parsear embedding
                if isinstance(embedding_json, str):
                    evento_embedding = json.loads(embedding_json)
                else:
                    evento_embedding = embedding_json
                
                # Calcular similitud coseno
                similitud = ai_service.cosine_similarity(user_embedding, evento_embedding)
                evento['similitud_score'] = similitud
                
                eventos_con_score.append(evento)
                
            except Exception as e:
                logger.warning(f"Error al procesar embedding del evento {evento.get('id_unico_evento')}: {e}")
                evento['similitud_score'] = 0.3
                eventos_con_score.append(evento)
        
        # Filtrar por similitud mínima (0.4)
        eventos_filtrados = [e for e in eventos_con_score if e['similitud_score'] >= 0.4]
        
        # Si no hay eventos con similitud >= 0.4, devolver los mejores 10
        if not eventos_filtrados and eventos_con_score:
            eventos_filtrados = sorted(eventos_con_score, key=lambda x: x['similitud_score'], reverse=True)[:10]
        
        # Ordenar por similitud descendente
        eventos_filtrados.sort(key=lambda x: x['similitud_score'], reverse=True)
        
        logger.info(f"Búsqueda semántica: {len(eventos_filtrados)} eventos con similitud >= 0.4")
        
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
        
        logger.info(f"Iniciando conversión de {len(eventos_raw)} eventos raw a modelos Pydantic")
        print(f"\n{'='*80}")
        print(f"⚙️  INICIANDO CONVERSIÓN: {len(eventos_raw)} eventos raw")
        print(f"{'='*80}\n")
        
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
                    distancia_km = self._calculate_distance(
                        coords_usuario['lat'],
                        coords_usuario['lng'],
                        float(evento_raw['latitud']),
                        float(evento_raw['longitud'])
                    )
                
                # Validar campos requeridos (COMENTADO TEMPORALMENTE PARA DEBUGGING)
                # if not evento_raw.get('id_unico_evento'):
                #     logger.warning(f"Evento sin ID, saltando")
                #     continue
                # 
                # if not evento_raw.get('titulo'):
                #     logger.warning(f"Evento {evento_raw.get('id_unico_evento')} sin título, saltando")
                #     continue
                
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
                    similitud_score=round(evento_raw.get('similitud_score', 0.0), 3)
                )
                
                eventos.append(evento)
                logger.debug(f"Evento {evento.id_unico_evento} convertido exitosamente")
                print(f"✅ Evento {evento.id_unico_evento} convertido: {evento.titulo[:50] if evento.titulo else 'Sin título'}...")
                
            except Exception as e:
                error_msg = f"Error al convertir evento {evento_raw.get('id_unico_evento')}: {e}"
                logger.error(error_msg)
                logger.error(f"Datos del evento: {evento_raw}")
                logger.exception("Stack trace completo:")
                
                # PRINT para asegurar visibilidad en consola
                print("=" * 80)
                print("\u274c ERROR EN CONVERSIÓN DE EVENTO:")
                print(error_msg)
                print(f"Tipo de error: {type(e).__name__}")
                print(f"Datos del evento: {evento_raw}")
                print("=" * 80)
                
                continue
        
        logger.info(f"Conversión completada: {len(eventos)} eventos convertidos de {len(eventos_raw)} raw")
        
        print(f"\n{'='*80}")
        print(f"✅ CONVERSIÓN COMPLETADA:")
        print(f"   - Eventos raw recibidos: {len(eventos_raw)}")
        print(f"   - Eventos convertidos exitosamente: {len(eventos)}")
        print(f"   - Eventos perdidos: {len(eventos_raw) - len(eventos)}")
        print(f"{'='*80}\n")
        
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
