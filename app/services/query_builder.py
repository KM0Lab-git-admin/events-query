"""
Servicio para construir queries SQL de forma segura.
"""

import logging
from typing import List, Optional, Tuple
from datetime import date

from app.models.schemas import ExtractedParameters

logger = logging.getLogger(__name__)


class QueryBuilder:
    """Constructor de queries SQL parametrizadas de forma segura."""
    
    def build_events_query(
        self,
        codigos_postales: List[str],
        params: ExtractedParameters
    ) -> Tuple[str, tuple]:
        """
        Construye una query SQL para buscar eventos con los parámetros dados.
        
        Args:
            codigos_postales: Lista de códigos postales a buscar
            params: Parámetros extraídos de la pregunta
        
        Returns:
            Tupla (query_sql, parametros_tupla)
        """
        # Base query
        query = """
        SELECT DISTINCT
            em.ID_Unico_Evento as id_unico_evento,
            CASE 
                WHEN %s = 'es' THEN em.Titulo_ES
                ELSE em.Titulo_CAT
            END as titulo,
            CASE 
                WHEN %s = 'es' THEN em.Desc_Larga_ES
                ELSE em.Desc_Larga_CAT
            END as descripcion_corta,
            CASE 
                WHEN %s = 'es' THEN em.Desc_Larga_ES
                ELSE em.Desc_Larga_CAT
            END as descripcion_larga,
            em.CP_Evento as cp_evento,
            em.Poblacion_Nombre as poblacion_nombre,
            em.Lugar_Nombre as lugar_nombre,
            em.Direccion_Fisica as direccion_completa,
            eh.Fecha_Inicio as fecha_inicio,
            eh.Fecha_Fin as fecha_fin,
            eh.Hora_Inicio as hora_inicio,
            eh.Hora_Fin as hora_fin,
            em.Es_Gratuito as es_gratuito,
            em.Precio_Euros as precio_euros,
            em.Link_Entradas_Inscripcion as url_evento,
            em.Imagen_Principal_URL as url_imagen,
            CASE 
                WHEN %s = 'es' THEN em.Tags_ES
                ELSE em.Tags_CAT
            END as tags_json,
            CASE 
                WHEN %s = 'es' THEN em.Tags_Embedding_ES
                ELSE em.Tags_Embedding_CAT
            END as tags_embedding_json,
            cp.Latitud as latitud,
            cp.Longitud as longitud
        FROM EVENTOS_MASTER em
        INNER JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
        INNER JOIN CODIGOS_POSTALES cp ON em.CP_Evento = cp.CP
        WHERE em.Estado = 'ACTIVO'
        """
        
        # Parámetros para la query
        query_params = [
            params.idioma,  # Para titulo
            params.idioma,  # Para descripcion_corta
            params.idioma,  # Para descripcion_larga
            params.idioma,  # Para tags_json
            params.idioma   # Para tags_embedding_json
        ]
        
        # Filtro por códigos postales
        if codigos_postales:
            placeholders = ','.join(['%s'] * len(codigos_postales))
            query += f" AND em.CP_Evento IN ({placeholders})"
            query_params.extend(codigos_postales)
        
        # Filtro por fechas
        if params.fechas:
            # Fechas específicas
            placeholders = ','.join(['%s'] * len(params.fechas))
            query += f" AND eh.Fecha_Inicio IN ({placeholders})"
            query_params.extend(params.fechas)
        elif params.fecha_inicio or params.fecha_fin:
            # Rango de fechas
            if params.fecha_inicio:
                query += " AND eh.Fecha_Inicio >= %s"
                query_params.append(params.fecha_inicio)
            if params.fecha_fin:
                query += " AND eh.Fecha_Inicio <= %s"
                query_params.append(params.fecha_fin)
        
        # Filtro por precio - solo filtrar si el usuario pidió explícitamente eventos gratuitos
        if params.es_gratuito is True:
            query += " AND em.Es_Gratuito = TRUE"
        elif params.precio_max is not None:
            query += " AND (em.Es_Gratuito = TRUE OR em.Precio_Euros <= %s)"
            query_params.append(params.precio_max)
        
        # Filtro por categorías (si se especificaron)
        if params.categorias:
            # Subconsulta para filtrar por categorías
            placeholders = ','.join(['%s'] * len(params.categorias))
            query += f"""
            AND em.ID_Unico_Evento IN (
                SELECT ec.ID_Unico_Evento
                FROM EVENTO_CATEGORIAS ec
                INNER JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
                WHERE c.Slug IN ({placeholders})
            )
            """
            query_params.extend([cat.lower().replace(' ', '_') for cat in params.categorias])
        
        # Ordenar por fecha
        query += " ORDER BY eh.Fecha_Inicio ASC, eh.Hora_Inicio ASC"
        
        # Limitar resultados (máximo 50 eventos para búsqueda semántica)
        query += " LIMIT 50"
        
        logger.info(f"Query construida con {len(query_params)} parámetros")
        
        return query, tuple(query_params)
    
    def build_categorias_query(self, idioma: str) -> Tuple[str, tuple]:
        """
        Construye una query para obtener todas las categorías.
        
        Args:
            idioma: Idioma ('es' o 'ca')
        
        Returns:
            Tupla (query_sql, parametros_tupla)
        """
        query = """
        SELECT 
            ID_Categoria as id,
            CASE 
                WHEN %s = 'es' THEN Nombre_ES
                ELSE Nombre_CAT
            END as nombre,
            Slug as slug
        FROM CATEGORIAS
        WHERE Activo = TRUE
        ORDER BY Orden ASC
        """
        
        return query, (idioma,)


# Instancia global del servicio
query_builder = QueryBuilder()
