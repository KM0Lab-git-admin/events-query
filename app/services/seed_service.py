"""
Servicio de seed para generar datos fake automáticamente si la BD está vacía.
Solo se ejecuta una vez (cuando hay 0 eventos).
"""

import logging
import sys
import os

# Añadir directorio raíz al path para importar scripts
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.database import db_service

logger = logging.getLogger(__name__)


async def get_events_count() -> int:
    """Obtiene el número de eventos en la BD."""
    try:
        result = await db_service.execute_query(
            "SELECT COUNT(*) as total FROM EVENTOS_MASTER",
            fetch_one=True
        )
        return result[0]["total"] if result else 0
    except Exception as e:
        logger.warning(f"Error al contar eventos (tabla puede no existir): {e}")
        return -1  # Indica error, no intentar seed


async def seed_if_empty() -> bool:
    """
    Genera datos fake si la BD está vacía (0 eventos).
    
    Returns:
        True si se generaron datos, False si ya había datos o hubo error.
    """
    count = await get_events_count()
    
    if count < 0:
        logger.warning("No se pudo verificar eventos, omitiendo seed")
        return False
    
    if count > 0:
        logger.info(f"✓ BD ya tiene {count} eventos, omitiendo seed")
        return False
    
    logger.info("BD vacía detectada, iniciando generación de datos fake...")
    
    try:
        # Importar funciones del script de generación
        from scripts.generate_fake_data import (
            generate_fake_events,
            add_embeddings_to_events,
            insert_base_data,
            insert_events,
            DatabaseService
        )
        
        # Usar el servicio de BD existente (ya conectado)
        # El script espera una instancia de DatabaseService, usamos db_service
        
        # 1. Insertar datos base (ciudades, códigos postales)
        logger.info("Insertando datos base (ciudades, CPs)...")
        await insert_base_data(db_service)
        
        # 2. Generar eventos fake
        logger.info("Generando 200 eventos fake...")
        eventos = generate_fake_events()
        logger.info(f"  -> {len(eventos)} eventos generados en memoria")
        
        # 3. Generar embeddings con OpenAI
        logger.info("Generando embeddings con OpenAI (puede tardar ~30s)...")
        eventos = await add_embeddings_to_events(eventos)
        
        # 4. Insertar en BD
        logger.info("Insertando eventos en BD...")
        await insert_events(db_service, eventos)
        
        # Verificar resultado
        final_count = await get_events_count()
        logger.info(f"✓ Seed completado: {final_count} eventos en BD")
        
        return True
        
    except ImportError as e:
        logger.error(f"Error importando scripts de generación: {e}")
        logger.error("Asegúrate de que scripts/generate_fake_data.py esté incluido en el deploy")
        return False
    except Exception as e:
        logger.error(f"Error durante seed: {e}", exc_info=True)
        return False
