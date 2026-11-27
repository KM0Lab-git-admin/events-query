"""
Script para generar embeddings para eventos existentes en la base de datos.
Útil cuando:
- Se han insertado eventos sin embeddings (ej: desde scraping)
- Se quiere regenerar embeddings con un nuevo modelo
- Se han modificado tags y se necesita actualizar embeddings

Uso:
    python scripts/generate_embeddings.py                    # Genera embeddings para TODOS los eventos sin embeddings
    python scripts/generate_embeddings.py --all              # Regenera embeddings para TODOS los eventos
    python scripts/generate_embeddings.py --batch-size 50    # Procesa en batches de 50
    python scripts/generate_embeddings.py --dry-run          # Simula sin guardar en BD
"""

import sys
import os
import asyncio
import json
import argparse
from typing import List, Dict, Any, Optional
from datetime import datetime

# Añadir el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import AsyncOpenAI
from app.services.database import DatabaseService
from app.config import settings


# =============================================================================
# CLIENTE OPENAI
# =============================================================================

openai_client: Optional[AsyncOpenAI] = None


def get_openai_client() -> AsyncOpenAI:
    """Obtiene el cliente OpenAI singleton."""
    global openai_client
    if openai_client is None:
        openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return openai_client


async def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Genera embeddings en batch para optimizar llamadas a OpenAI.
    
    Args:
        texts: Lista de textos para generar embeddings
    
    Returns:
        Lista de embeddings (cada uno es una lista de 1536 floats)
    """
    client = get_openai_client()
    
    try:
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=texts
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"❌ Error generando embeddings en batch: {e}")
        return [[] for _ in texts]


# =============================================================================
# CONSTRUCCIÓN DE TEXTO PARA EMBEDDING
# =============================================================================

def build_embedding_text(evento: Dict[str, Any], idioma: str) -> str:
    """
    Construye el texto combinado para el embedding de un evento.
    
    El embedding incluye:
    - Título del evento
    - Descripción (primeros 300 caracteres)
    - Tags (todos concatenados)
    - Categoría
    
    Esto permite que el embedding capture TODO el contenido relevante del evento,
    mejorando significativamente el matching semántico.
    
    Args:
        evento: Diccionario con datos del evento
        idioma: 'es' o 'cat'
    
    Returns:
        Texto combinado para generar embedding
    """
    if idioma == "es":
        titulo = evento.get("Titulo_ES", "")
        desc = evento.get("Desc_Larga_ES", "")[:300]  # Truncar a 300 chars
        tags_json = evento.get("Tags_ES")
    else:
        titulo = evento.get("Titulo_CAT", "")
        desc = evento.get("Desc_Larga_CAT", "")[:300]
        tags_json = evento.get("Tags_CAT")
    
    # Parsear tags
    tags = []
    if tags_json:
        try:
            if isinstance(tags_json, str):
                tags = json.loads(tags_json)
            else:
                tags = tags_json
        except:
            pass
    
    tags_text = " ".join(tags) if tags else ""
    
    # Obtener categoría (si existe)
    # Nota: Esto requeriría un JOIN con EVENTO_CATEGORIAS + CATEGORIAS
    # Por simplicidad, usamos los tags que empiecen con mayúscula como categoría
    categoria = ""
    for tag in tags:
        if tag and tag[0].isupper():
            categoria = tag
            break
    
    # Construir texto combinado
    # Formato: "TÍTULO. DESCRIPCIÓN. TAGS. CATEGORÍA"
    parts = [titulo, desc, tags_text, categoria]
    texto = ". ".join(p for p in parts if p)
    
    return texto


# =============================================================================
# OBTENCIÓN DE EVENTOS
# =============================================================================

async def get_events_without_embeddings(db: DatabaseService) -> List[Dict[str, Any]]:
    """
    Obtiene todos los eventos que NO tienen embeddings generados.
    
    Args:
        db: Servicio de base de datos
    
    Returns:
        Lista de eventos sin embeddings
    """
    query = """
        SELECT 
            ID_Unico_Evento,
            Titulo_ES,
            Titulo_CAT,
            Desc_Larga_ES,
            Desc_Larga_CAT,
            Tags_ES,
            Tags_CAT,
            Tags_Embedding_ES,
            Tags_Embedding_CAT
        FROM EVENTOS_MASTER
        WHERE Estado = 'ACTIVO'
          AND (Tags_Embedding_ES IS NULL OR Tags_Embedding_CAT IS NULL)
        ORDER BY Fecha_Creacion DESC
    """
    
    result = await db.execute_query(query)
    return result or []


async def get_all_events(db: DatabaseService) -> List[Dict[str, Any]]:
    """
    Obtiene TODOS los eventos activos.
    
    Args:
        db: Servicio de base de datos
    
    Returns:
        Lista de todos los eventos
    """
    query = """
        SELECT 
            ID_Unico_Evento,
            Titulo_ES,
            Titulo_CAT,
            Desc_Larga_ES,
            Desc_Larga_CAT,
            Tags_ES,
            Tags_CAT,
            Tags_Embedding_ES,
            Tags_Embedding_CAT
        FROM EVENTOS_MASTER
        WHERE Estado = 'ACTIVO'
        ORDER BY Fecha_Creacion DESC
    """
    
    result = await db.execute_query(query)
    return result or []


# =============================================================================
# GENERACIÓN Y ACTUALIZACIÓN DE EMBEDDINGS
# =============================================================================

async def generate_and_update_embeddings(
    db: DatabaseService,
    eventos: List[Dict[str, Any]],
    batch_size: int = 20,
    dry_run: bool = False
) -> Dict[str, int]:
    """
    Genera embeddings para una lista de eventos y los actualiza en la BD.
    
    Args:
        db: Servicio de base de datos
        eventos: Lista de eventos
        batch_size: Tamaño del batch para OpenAI (default: 20)
        dry_run: Si es True, no guarda en BD (solo simula)
    
    Returns:
        Estadísticas de la operación
    """
    total = len(eventos)
    stats = {
        "total": total,
        "procesados": 0,
        "actualizados": 0,
        "errores": 0
    }
    
    if total == 0:
        return stats
    
    print(f"\n{'=' * 60}")
    print(f"GENERANDO EMBEDDINGS PARA {total} EVENTOS")
    print(f"Batch size: {batch_size}")
    print(f"Modo: {'DRY RUN (no se guardarán cambios)' if dry_run else 'PRODUCCIÓN'}")
    print(f"{'=' * 60}\n")
    
    for i in range(0, total, batch_size):
        batch = eventos[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        
        print(f"📦 Procesando batch {batch_num}/{total_batches} ({len(batch)} eventos)...")
        
        # Preparar textos combinados para embedding
        texts_es = [build_embedding_text(e, "es") for e in batch]
        texts_cat = [build_embedding_text(e, "cat") for e in batch]
        
        # Generar embeddings en batch
        try:
            embeddings_es = await generate_embeddings_batch(texts_es)
            embeddings_cat = await generate_embeddings_batch(texts_cat)
            
            # Actualizar cada evento en la BD
            for j, evento in enumerate(batch):
                try:
                    embedding_es = embeddings_es[j] if j < len(embeddings_es) else []
                    embedding_cat = embeddings_cat[j] if j < len(embeddings_cat) else []
                    
                    if not embedding_es or not embedding_cat:
                        print(f"  ⚠️  Evento {evento['ID_Unico_Evento'][:16]}... - embeddings vacíos")
                        stats["errores"] += 1
                        continue
                    
                    if not dry_run:
                        # Actualizar en BD
                        await db.execute_query(
                            """
                            UPDATE EVENTOS_MASTER
                            SET Tags_Embedding_ES = %s,
                                Tags_Embedding_CAT = %s,
                                Fecha_Actualizacion = NOW()
                            WHERE ID_Unico_Evento = %s
                            """,
                            (
                                json.dumps(embedding_es),
                                json.dumps(embedding_cat),
                                evento['ID_Unico_Evento']
                            )
                        )
                    
                    stats["actualizados"] += 1
                    stats["procesados"] += 1
                    
                    # Mostrar progreso cada 10 eventos
                    if stats["procesados"] % 10 == 0:
                        print(f"  ✅ {stats['procesados']}/{total} eventos procesados...")
                
                except Exception as e:
                    print(f"  ❌ Error actualizando evento {evento['ID_Unico_Evento'][:16]}...: {e}")
                    stats["errores"] += 1
                    stats["procesados"] += 1
            
            # Pequeña pausa para no saturar la API
            if i + batch_size < total:
                await asyncio.sleep(0.5)
        
        except Exception as e:
            print(f"  ❌ Error procesando batch {batch_num}: {e}")
            stats["errores"] += len(batch)
            stats["procesados"] += len(batch)
    
    return stats


# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

async def main(args):
    """Función principal."""
    print("=" * 60)
    print("GENERADOR DE EMBEDDINGS PARA EVENTOS EXISTENTES")
    print("Events Query API")
    print("=" * 60)
    print(f"\nConfiguración:")
    print(f"  - Modo: {'TODOS los eventos' if args.all else 'Solo eventos sin embeddings'}")
    print(f"  - Batch size: {args.batch_size}")
    print(f"  - Dry run: {'Sí (no se guardarán cambios)' if args.dry_run else 'No'}")
    
    # Crear servicio de BD
    db = DatabaseService()
    
    try:
        # Conectar
        print("\n🔌 Conectando a la base de datos...")
        await db.connect()
        print("  ✅ Conectado")
        
        # Obtener eventos
        print("\n📊 Obteniendo eventos...")
        if args.all:
            eventos = await get_all_events(db)
        else:
            eventos = await get_events_without_embeddings(db)
        
        print(f"  ✅ {len(eventos)} eventos encontrados")
        
        if len(eventos) == 0:
            print("\n✨ No hay eventos para procesar. ¡Todo listo!")
            return 0
        
        # Generar y actualizar embeddings
        stats = await generate_and_update_embeddings(
            db,
            eventos,
            batch_size=args.batch_size,
            dry_run=args.dry_run
        )
        
        # Mostrar estadísticas
        print(f"\n{'=' * 60}")
        print("RESUMEN")
        print(f"{'=' * 60}")
        print(f"  Total eventos: {stats['total']}")
        print(f"  Procesados: {stats['procesados']}")
        print(f"  Actualizados: {stats['actualizados']}")
        print(f"  Errores: {stats['errores']}")
        
        if args.dry_run:
            print(f"\n⚠️  DRY RUN: No se guardaron cambios en la BD")
        else:
            print(f"\n✅ Embeddings generados y guardados exitosamente")
        
        print(f"{'=' * 60}\n")
        
        return 0
    
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        await db.disconnect()
        print("🔌 Desconectado de la base de datos\n")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genera embeddings para eventos existentes en la base de datos"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Regenerar embeddings para TODOS los eventos (no solo los que no tienen)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Tamaño del batch para OpenAI (default: 20)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula la generación sin guardar en BD"
    )
    
    args = parser.parse_args()
    
    exit_code = asyncio.run(main(args))
    sys.exit(exit_code)
