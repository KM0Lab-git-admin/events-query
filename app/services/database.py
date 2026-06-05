"""
Servicio de base de datos con conexión asíncrona usando aiomysql.
"""

import re
import aiomysql
from pathlib import Path
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
    
    async def execute_insert(
        self,
        query: str,
        params: Optional[tuple] = None,
    ) -> int:
        """
        INSERT (o REPLACE) y devuelve lastrowid (0 si no aplica).
        """
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params or ())
                return int(cursor.lastrowid or 0)

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

    async def _execute_statement(self, statement: str) -> None:
        """Ejecuta una sentencia SQL sin devolver resultados (DDL, INSERT, etc.)."""
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(statement)

    async def _tables_exist(self) -> bool:
        """Comprueba si las tablas base existen (CIUDADES como indicador)."""
        try:
            result = await self.execute_query(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = 'CIUDADES'",
                (settings.db_name,),
                fetch_one=True
            )
            return result is not None
        except Exception:
            return False

    async def init_schema_if_needed(self) -> None:
        """
        Si las tablas no existen, ejecuta el esquema SQL para crearlas.
        Útil para despliegues en Railway u otros entornos donde no hay init manual.
        """
        if await self._tables_exist():
            logger.info("Tablas ya existentes, omitiendo inicialización de esquema")
            return

        logger.info("Tablas no detectadas, creando esquema desde SQL/SCHEMA_SQL_FINAL.sql")

        schema_path = Path(__file__).resolve().parent.parent.parent / "SQL" / "SCHEMA_SQL_FINAL.sql"
        if not schema_path.exists():
            raise FileNotFoundError(
                f"No se encontró el esquema SQL en {schema_path}. "
                "Asegúrate de incluir la carpeta SQL en el despliegue."
            )

        sql_content = schema_path.read_text(encoding="utf-8")

        # Eliminar bloques de comentarios /* ... */
        sql_content = re.sub(r"/\*[\s\S]*?\*/", "", sql_content)

        # Dividir por punto y coma
        statements = [
            s.strip()
            for s in re.split(r";\s*\n", sql_content)
            if s.strip()
        ]

        skip_prefixes = ("CREATE DATABASE", "USE ")

        for stmt in statements:
            stmt = stmt.strip()
            # Quitar líneas de comentario al inicio
            lines = stmt.split("\n")
            while lines and lines[0].strip().startswith("--"):
                lines.pop(0)
            stmt = "\n".join(lines).strip()
            if not stmt:
                continue
            if any(stmt.upper().startswith(prefix) for prefix in skip_prefixes):
                continue

            try:
                await self._execute_statement(stmt)
                logger.debug(f"Ejecutada sentencia: {stmt[:60]}...")
            except Exception as e:
                logger.warning(f"Error ejecutando sentencia (puede ser comentario): {e}")
                # No relanzar: bloques de comentarios o notas pueden fallar

        logger.info("Esquema inicializado correctamente")


# Instancia global del servicio
db_service = DatabaseService()
