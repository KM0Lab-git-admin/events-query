"""
Servicio de base de datos con conexión asíncrona usando aiomysql.
"""

import aiomysql
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class DatabaseService:
    """Servicio para gestionar conexiones y queries a MySQL de forma asíncrona."""
    
    def __init__(self):
        self.pool: Optional[aiomysql.Pool] = None
    
    async def connect(self) -> None:
        """Crea el connection pool de MySQL."""
        try:
            self.pool = await aiomysql.create_pool(
                host=settings.db_host,
                port=settings.db_port,
                user=settings.db_user,
                password=settings.db_password,
                db=settings.db_name,
                minsize=settings.db_pool_min_size,
                maxsize=settings.db_pool_max_size,
                autocommit=True,
                charset='utf8mb4'
            )
            logger.info(f"Connection pool creado: min={settings.db_pool_min_size}, max={settings.db_pool_max_size}")
        except Exception as e:
            logger.error(f"Error al crear connection pool: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Cierra el connection pool."""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            logger.info("Connection pool cerrado")
    
    @asynccontextmanager
    async def get_connection(self):
        """Context manager para obtener una conexión del pool."""
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        
        async with self.pool.acquire() as conn:
            yield conn
    
    async def execute_query(
        self,
        query: str,
        params: Optional[tuple] = None,
        fetch_one: bool = False,
        fetch_all: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Ejecuta una query y devuelve los resultados.
        
        Args:
            query: Query SQL a ejecutar
            params: Parámetros para la query (tupla)
            fetch_one: Si True, devuelve solo un resultado
            fetch_all: Si True, devuelve todos los resultados
        
        Returns:
            Lista de diccionarios con los resultados, o None si no hay resultados
        """
        async with self.get_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, params or ())
                
                if fetch_one:
                    result = await cursor.fetchone()
                    return [result] if result else None
                elif fetch_all:
                    results = await cursor.fetchall()
                    return results if results else []
                else:
                    return None
    
    async def execute_many(
        self,
        query: str,
        params_list: List[tuple]
    ) -> int:
        """
        Ejecuta una query múltiples veces con diferentes parámetros.
        
        Args:
            query: Query SQL a ejecutar
            params_list: Lista de tuplas de parámetros
        
        Returns:
            Número de filas afectadas
        """
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.executemany(query, params_list)
                return cursor.rowcount
    
    async def health_check(self) -> bool:
        """Verifica que la conexión a la base de datos esté funcionando."""
        try:
            result = await self.execute_query("SELECT 1 as health", fetch_one=True)
            return result is not None and result[0].get('health') == 1
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def get_codigos_postales_in_radius(
        self,
        cp_origen: str,
        radio_km: float
    ) -> List[str]:
        """
        Obtiene los códigos postales dentro de un radio desde un CP origen.
        
        Args:
            cp_origen: Código postal de origen
            radio_km: Radio en kilómetros
        
        Returns:
            Lista de códigos postales dentro del radio
        """
        query = """
        SELECT 
            cp2.CP,
            (6371 * acos(
                cos(radians(cp1.Latitud)) * 
                cos(radians(cp2.Latitud)) * 
                cos(radians(cp2.Longitud) - radians(cp1.Longitud)) + 
                sin(radians(cp1.Latitud)) * 
                sin(radians(cp2.Latitud))
            )) AS distancia_km
        FROM CODIGOS_POSTALES cp1
        CROSS JOIN CODIGOS_POSTALES cp2
        WHERE cp1.CP = %s
        HAVING distancia_km <= %s
        ORDER BY distancia_km
        """
        
        results = await self.execute_query(query, (cp_origen, radio_km))
        return [row['CP'] for row in results] if results else []
    
    async def get_coordenadas_cp(self, cp: str) -> Optional[Dict[str, float]]:
        """
        Obtiene las coordenadas de un código postal.
        
        Args:
            cp: Código postal
        
        Returns:
            Diccionario con 'lat' y 'lng', o None si no existe
        """
        query = """
        SELECT Latitud as lat, Longitud as lng
        FROM CODIGOS_POSTALES
        WHERE CP = %s
        """
        
        result = await self.execute_query(query, (cp,), fetch_one=True)
        if result:
            # Convertir Decimal a float explícitamente
            coords = result[0]
            return {
                'lat': float(coords['lat']) if coords.get('lat') is not None else None,
                'lng': float(coords['lng']) if coords.get('lng') is not None else None
            }
        return None


# Instancia global del servicio
db_service = DatabaseService()
