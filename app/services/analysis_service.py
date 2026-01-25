"""
Servicio de análisis detallado de similitud semántica.
Proporciona visibilidad completa del proceso de decisión de OpenAI.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from app.services.ai_service import ai_service

logger = logging.getLogger(__name__)


class AnalysisService:
    """Servicio para análisis detallado de similitud semántica."""
    
    async def analyze_event_similarity(
        self,
        evento: Dict[str, Any],
        pregunta_embedding: List[float],
        conceptos: List[str],
        umbral: float = 0.4
    ) -> Dict[str, Any]:
        """
        Analiza en detalle por qué un evento tiene cierto score de similitud.
        
        Args:
            evento: Evento raw de la BD
            pregunta_embedding: Embedding de la pregunta del usuario
            conceptos: Conceptos extraídos de la pregunta
            umbral: Umbral de similitud para pasar el filtro
        
        Returns:
            Análisis detallado con similitudes por tag, categoría, descripción
        """
        analisis = {
            "evento_id": evento.get('id_unico_evento'),
            "titulo": evento.get('titulo'),
            "score_global": round(evento.get('similitud_score', 0.0), 3),
            "umbral": umbral,
            "pasa_filtro": evento.get('similitud_score', 0.0) >= umbral,
            "similitud_por_tag": [],
            "similitud_categoria": None,
            "similitud_descripcion": None,
            "diagnostico": {}
        }
        
        # Analizar similitud por cada tag
        tags_json = evento.get('tags_json')
        if tags_json:
            try:
                if isinstance(tags_json, str):
                    tags = json.loads(tags_json)
                else:
                    tags = tags_json
                
                for tag in tags:
                    tag_embedding = await ai_service.generate_embedding(tag)
                    similitud = ai_service.cosine_similarity(pregunta_embedding, tag_embedding)
                    analisis['similitud_por_tag'].append({
                        "tag": tag,
                        "similitud": round(similitud, 3)
                    })
                
                # Ordenar por similitud descendente
                analisis['similitud_por_tag'].sort(key=lambda x: x['similitud'], reverse=True)
                
            except Exception as e:
                logger.warning(f"Error al analizar tags del evento {evento.get('id_unico_evento')}: {e}")
        
        # Analizar similitud por categoría (si existe en los tags)
        # Nota: Las categorías están en los tags, buscar las que empiecen con mayúscula
        categorias = [tag for tag in (tags if tags_json else []) if tag and tag[0].isupper()]
        if categorias:
            # Usar la primera categoría encontrada
            categoria = categorias[0]
            cat_embedding = await ai_service.generate_embedding(categoria)
            similitud_cat = ai_service.cosine_similarity(pregunta_embedding, cat_embedding)
            analisis['similitud_categoria'] = {
                "categoria": categoria,
                "similitud": round(similitud_cat, 3)
            }
        
        # Analizar similitud por descripción (primeros 200 caracteres)
        descripcion = evento.get('descripcion_larga') or evento.get('descripcion_corta')
        if descripcion:
            desc_text = descripcion[:200]
            desc_embedding = await ai_service.generate_embedding(desc_text)
            similitud_desc = ai_service.cosine_similarity(pregunta_embedding, desc_embedding)
            analisis['similitud_descripcion'] = round(similitud_desc, 3)
        
        # Generar diagnóstico
        analisis['diagnostico'] = self._generar_diagnostico(analisis, conceptos)
        
        return analisis
    
    def _generar_diagnostico(
        self,
        analisis: Dict[str, Any],
        conceptos: List[str]
    ) -> Dict[str, Any]:
        """
        Genera diagnóstico automático basado en el análisis de similitud.
        
        Args:
            analisis: Análisis de similitud del evento
            conceptos: Conceptos de la pregunta del usuario
        
        Returns:
            Diagnóstico con problemas detectados y soluciones propuestas
        """
        diagnostico = {
            "problemas": [],
            "soluciones": [],
            "score_estimado_con_mejoras": analisis['score_global']
        }
        
        # Problema 1: No pasa el umbral
        if not analisis['pasa_filtro']:
            diagnostico['problemas'].append({
                "tipo": "SCORE_BAJO",
                "descripcion": f"Score {analisis['score_global']} < umbral {analisis['umbral']}",
                "severidad": "ALTA"
            })
        
        # Problema 2: Categoría con baja similitud
        if analisis['similitud_categoria']:
            sim_cat = analisis['similitud_categoria']['similitud']
            if sim_cat < 0.3:
                diagnostico['problemas'].append({
                    "tipo": "CATEGORIA_IRRELEVANTE",
                    "descripcion": f"Categoría '{analisis['similitud_categoria']['categoria']}' tiene similitud muy baja ({sim_cat})",
                    "severidad": "ALTA"
                })
                
                # Sugerir cambio de categoría
                mejor_categoria = self._sugerir_categoria(analisis['similitud_por_tag'], conceptos)
                if mejor_categoria:
                    diagnostico['soluciones'].append({
                        "prioridad": "ALTA",
                        "tipo": "cambiar_categoria",
                        "accion": f"Cambiar categoría a '{mejor_categoria}'",
                        "impacto_estimado": "+0.20",
                        "categoria_actual": analisis['similitud_categoria']['categoria'],
                        "categoria_sugerida": mejor_categoria
                    })
                    diagnostico['score_estimado_con_mejoras'] += 0.20
        
        # Problema 3: Pocos tags relevantes
        tags_relevantes = [t for t in analisis['similitud_por_tag'] if t['similitud'] > 0.4]
        if len(tags_relevantes) < 2:
            diagnostico['problemas'].append({
                "tipo": "TAGS_INSUFICIENTES",
                "descripcion": f"Solo {len(tags_relevantes)} tags con similitud > 0.4",
                "severidad": "ALTA"
            })
            
            # Sugerir tags adicionales
            tags_sugeridos = self._sugerir_tags(analisis, conceptos)
            if tags_sugeridos:
                diagnostico['soluciones'].append({
                    "prioridad": "ALTA",
                    "tipo": "añadir_tags",
                    "accion": f"Añadir tags: {', '.join(tags_sugeridos)}",
                    "impacto_estimado": "+0.15",
                    "tags_sugeridos": tags_sugeridos
                })
                diagnostico['score_estimado_con_mejoras'] += 0.15
        
        # Problema 4: Descripción con baja similitud
        if analisis['similitud_descripcion'] and analisis['similitud_descripcion'] < 0.3:
            diagnostico['problemas'].append({
                "tipo": "DESCRIPCION_POCO_RELEVANTE",
                "descripcion": f"Descripción tiene similitud baja ({analisis['similitud_descripcion']})",
                "severidad": "MEDIA"
            })
            
            diagnostico['soluciones'].append({
                "prioridad": "MEDIA",
                "tipo": "mejorar_descripcion",
                "accion": f"Incluir palabras clave: {', '.join(conceptos)}",
                "impacto_estimado": "+0.08"
            })
            diagnostico['score_estimado_con_mejoras'] += 0.08
        
        # Problema 5: Sin embedding
        if analisis['score_global'] == 0.3:  # Score por defecto cuando no hay embedding
            diagnostico['problemas'].append({
                "tipo": "SIN_EMBEDDING",
                "descripcion": "El evento no tiene embedding generado",
                "severidad": "CRÍTICA"
            })
            
            diagnostico['soluciones'].append({
                "prioridad": "CRÍTICA",
                "tipo": "generar_embedding",
                "accion": "Generar embedding para este evento",
                "impacto_estimado": "+0.30"
            })
            diagnostico['score_estimado_con_mejoras'] += 0.30
        
        # Redondear score estimado
        diagnostico['score_estimado_con_mejoras'] = round(
            min(diagnostico['score_estimado_con_mejoras'], 1.0), 3
        )
        
        return diagnostico
    
    def _sugerir_categoria(
        self,
        similitud_por_tag: List[Dict[str, Any]],
        conceptos: List[str]
    ) -> Optional[str]:
        """
        Sugiere una categoría más apropiada basándose en los tags con mayor similitud.
        
        Args:
            similitud_por_tag: Lista de tags con sus similitudes
            conceptos: Conceptos de la pregunta
        
        Returns:
            Categoría sugerida o None
        """
        # Mapeo de conceptos comunes a categorías
        mapeo_categorias = {
            "comida": "Gastronomía",
            "comer": "Gastronomía",
            "restaurante": "Gastronomía",
            "cata": "Gastronomía",
            "vino": "Gastronomía",
            "queso": "Gastronomía",
            "cocina": "Gastronomía",
            "niños": "Infantil",
            "niño": "Infantil",
            "familia": "Infantil",
            "infantil": "Infantil",
            "cuentacuentos": "Infantil",
            "deporte": "Deportes",
            "fútbol": "Deportes",
            "running": "Deportes",
            "gimnasio": "Deportes",
            "arte": "Cultura",
            "museo": "Cultura",
            "exposición": "Cultura",
            "concierto": "Cultura",
            "música": "Cultura"
        }
        
        # Buscar en conceptos
        for concepto in conceptos:
            concepto_lower = concepto.lower()
            if concepto_lower in mapeo_categorias:
                return mapeo_categorias[concepto_lower]
        
        # Buscar en tags con alta similitud
        for tag_info in similitud_por_tag[:3]:  # Top 3 tags
            tag_lower = tag_info['tag'].lower()
            if tag_lower in mapeo_categorias:
                return mapeo_categorias[tag_lower]
        
        return None
    
    def _sugerir_tags(
        self,
        analisis: Dict[str, Any],
        conceptos: List[str]
    ) -> List[str]:
        """
        Sugiere tags adicionales basándose en los conceptos de la pregunta.
        
        Args:
            analisis: Análisis de similitud del evento
            conceptos: Conceptos de la pregunta
        
        Returns:
            Lista de tags sugeridos
        """
        tags_actuales = [t['tag'].lower() for t in analisis['similitud_por_tag']]
        tags_sugeridos = []
        
        # Mapeo de conceptos a tags relacionados
        mapeo_tags = {
            "comida": ["comida", "gastronomía", "alimentación", "culinaria"],
            "comer": ["comida", "gastronomía", "restaurante"],
            "cata": ["degustación", "gastronomía", "comida"],
            "vino": ["enología", "bebidas", "gastronomía"],
            "niños": ["infantil", "familia", "educativo"],
            "deporte": ["deportivo", "actividad física", "salud"],
            "arte": ["cultural", "artístico", "creativo"],
            "música": ["musical", "concierto", "cultural"]
        }
        
        for concepto in conceptos:
            concepto_lower = concepto.lower()
            if concepto_lower in mapeo_tags:
                for tag in mapeo_tags[concepto_lower]:
                    if tag not in tags_actuales and tag not in tags_sugeridos:
                        tags_sugeridos.append(tag)
        
        # Limitar a 5 sugerencias
        return tags_sugeridos[:5]
    
    async def analyze_batch(
        self,
        eventos: List[Dict[str, Any]],
        pregunta_embedding: List[float],
        conceptos: List[str],
        umbral: float = 0.4
    ) -> List[Dict[str, Any]]:
        """
        Analiza un lote de eventos.
        
        Args:
            eventos: Lista de eventos raw
            pregunta_embedding: Embedding de la pregunta
            conceptos: Conceptos extraídos
            umbral: Umbral de similitud
        
        Returns:
            Lista de análisis detallados
        """
        analisis_list = []
        
        for evento in eventos:
            try:
                analisis = await self.analyze_event_similarity(
                    evento,
                    pregunta_embedding,
                    conceptos,
                    umbral
                )
                analisis_list.append(analisis)
            except Exception as e:
                logger.error(f"Error al analizar evento {evento.get('id_unico_evento')}: {e}")
        
        return analisis_list


# Instancia global del servicio
analysis_service = AnalysisService()
