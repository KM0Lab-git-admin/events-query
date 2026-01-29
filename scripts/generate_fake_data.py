"""
Script para generar datos fake para la base de datos Events Query API.
Genera 100 eventos para Malgrat de Mar y 100 para Blanes (200 total).
Incluye embeddings generados con OpenAI.
"""

import sys
import os
import asyncio
import json
import hashlib
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional, Tuple
import random

# Añadir el directorio raíz al path para importar módulos
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import AsyncOpenAI

from app.services.database import DatabaseService
from app.config import settings

# Importar datos de lugares reales
from scripts.data.lugares_reales import (
    POBLACIONES,
    ASOCIACIONES,
    EVENTOS_PLANTILLAS
)

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

EVENTOS_POR_POBLACION = 100
PORCENTAJE_RECURRENTES = 0.25  # 25% de eventos serán recurrentes
DIAS_RANGO_EVENTOS = 60  # Próximos 60 días (2 meses)

CATEGORIAS = [
    {"id": 1, "slug": "cultura"},
    {"id": 2, "slug": "deportes"},
    {"id": 3, "slug": "ocio"},
    {"id": 4, "slug": "infantil"},
    {"id": 5, "slug": "formacion"},
    {"id": 6, "slug": "gastronomia"},
    {"id": 7, "slug": "musica"},
    {"id": 8, "slug": "naturaleza"}
]

SLUG_TO_ID = {cat["slug"]: cat["id"] for cat in CATEGORIAS}


# =============================================================================
# CLIENTE OPENAI PARA EMBEDDINGS
# =============================================================================

openai_client: Optional[AsyncOpenAI] = None


def get_openai_client() -> AsyncOpenAI:
    """Obtiene el cliente OpenAI singleton."""
    global openai_client
    if openai_client is None:
        openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return openai_client


async def generate_embedding(text: str) -> List[float]:
    """Genera un embedding para un texto usando OpenAI."""
    client = get_openai_client()
    
    try:
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error generando embedding: {e}")
        return []


async def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Genera embeddings en batch para optimizar llamadas a OpenAI."""
    client = get_openai_client()
    
    try:
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=texts
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"Error generando embeddings en batch: {e}")
        return [[] for _ in texts]


# =============================================================================
# GENERADOR DE IDs ÚNICOS
# =============================================================================

def generate_id_unico(titulo: str, fecha: date, cp: str, index: int) -> str:
    """Genera un ID único para un evento."""
    data = f"{titulo}{fecha.isoformat()}{cp}{index}{random.randint(1000, 9999)}"
    return hashlib.sha256(data.encode()).hexdigest()


# =============================================================================
# GENERADOR DE RECURRENCIA
# =============================================================================

def generate_recurrencia_json(fecha_inicio: date) -> Dict[str, Any]:
    """Genera un JSON de recurrencia aleatorio."""
    tipos_recurrencia = [
        {
            "tipo": "semanal",
            "dias": random.sample(["lunes", "martes", "miercoles", "jueves", "viernes"], k=random.randint(1, 2))
        },
        {
            "tipo": "quincenal",
            "dias": [random.choice(["sabado", "domingo"])]
        }
    ]
    
    recurrencia = random.choice(tipos_recurrencia)
    fecha_fin = fecha_inicio + timedelta(days=DIAS_RANGO_EVENTOS)
    
    hora_inicio = f"{random.randint(9, 19):02d}:00"
    hora_fin = f"{random.randint(int(hora_inicio[:2]) + 1, 22):02d}:00"
    
    return {
        "tipo": recurrencia["tipo"],
        "intervalo": 1 if recurrencia["tipo"] == "semanal" else 2,
        "regla": {
            "dias_semana": recurrencia["dias"],
            "finalizacion": {
                "tipo": "fecha",
                "valor": fecha_fin.isoformat()
            }
        },
        "horarios": [{
            "inicio": hora_inicio,
            "fin": hora_fin
        }]
    }


# =============================================================================
# GENERADOR DE EVENTOS
# =============================================================================

def generate_fake_events() -> List[Dict[str, Any]]:
    """Genera eventos fake para Malgrat y Blanes."""
    eventos = []
    fecha_inicio = datetime.now().date()
    
    for cp, poblacion_data in POBLACIONES.items():
        print(f"\nGenerando eventos para {poblacion_data['nombre']} ({cp})...")
        
        # Combinar lugares públicos y privados
        lugares = (
            poblacion_data["lugares_publicos"] + 
            poblacion_data["lugares_privados"]
        )
        
        # Añadir asociaciones que operan en esta población
        for asoc in ASOCIACIONES:
            if cp in asoc.get("poblaciones", []):
                lugares.append({
                    "nombre": asoc["nombre"],
                    "direccion": f"Varies localitzacions - {poblacion_data['nombre']}",
                    "tipo": asoc["tipo"],
                    "organizador": asoc["organizador"],
                    "web": asoc.get("web"),
                    "categorias_tipicas": asoc["categorias_tipicas"]
                })
        
        eventos_generados = 0
        intentos = 0
        max_intentos = EVENTOS_POR_POBLACION * 3
        
        while eventos_generados < EVENTOS_POR_POBLACION and intentos < max_intentos:
            intentos += 1
            
            # Seleccionar lugar aleatorio
            lugar = random.choice(lugares)
            
            # Seleccionar categoría (preferir las típicas del lugar si las tiene)
            categorias_tipicas = lugar.get("categorias_tipicas", list(EVENTOS_PLANTILLAS.keys()))
            categoria_slug = random.choice(categorias_tipicas)
            
            if categoria_slug not in EVENTOS_PLANTILLAS:
                continue
            
            # Seleccionar plantilla de evento
            plantilla = random.choice(EVENTOS_PLANTILLAS[categoria_slug])
            
            # Generar fecha aleatoria
            dias_adelante = random.randint(1, DIAS_RANGO_EVENTOS)
            fecha_evento = fecha_inicio + timedelta(days=dias_adelante)
            
            # Decidir si es recurrente
            es_recurrente = random.random() < PORCENTAJE_RECURRENTES
            
            # Generar ID único
            id_unico = generate_id_unico(
                plantilla["titulo_es"],
                fecha_evento,
                cp,
                eventos_generados
            )
            
            # Precio (60% gratuitos para públicos, 30% para privados)
            if lugar["tipo"] == "PUBLICO":
                es_gratuito = random.random() < 0.7
            elif lugar["tipo"] == "ASOCIACION":
                es_gratuito = random.random() < 0.8
            else:  # PRIVADO
                es_gratuito = random.random() < 0.3
            
            precio = None if es_gratuito else round(random.uniform(5, 45), 2)
            
            # Hora (si no es recurrente)
            if es_recurrente:
                recurrencia_json = generate_recurrencia_json(fecha_evento)
                hora_inicio = recurrencia_json["horarios"][0]["inicio"]
                hora_fin = recurrencia_json["horarios"][0]["fin"]
            else:
                hora_inicio = f"{random.randint(9, 20):02d}:{random.choice(['00', '30'])}:00"
                hora_fin_h = min(int(hora_inicio[:2]) + random.randint(1, 3), 23)
                hora_fin = f"{hora_fin_h:02d}:{random.choice(['00', '30'])}:00"
                recurrencia_json = None
            
            # Construir título con ubicación
            titulo_es = f"{plantilla['titulo_es']} - {poblacion_data['nombre']}"
            titulo_cat = f"{plantilla['titulo_cat']} - {poblacion_data['nombre']}"
            
            # Construir descripción completa
            desc_es = f"{plantilla['desc_es']} Organizado por {lugar['organizador']} en {lugar['nombre']}."
            desc_cat = f"{plantilla['desc_cat']} Organitzat per {lugar['organizador']} a {lugar['nombre']}."
            
            evento = {
                "id_unico": id_unico,
                "titulo_es": titulo_es,
                "titulo_cat": titulo_cat,
                "desc_es": desc_es,
                "desc_cat": desc_cat,
                "cp_evento": cp,
                "poblacion": poblacion_data["nombre"],
                "lugar_nombre": lugar["nombre"],
                "direccion": lugar.get("direccion"),
                "lat": poblacion_data["lat"] + random.uniform(-0.005, 0.005),
                "lng": poblacion_data["lng"] + random.uniform(-0.005, 0.005),
                "tipo_organizador": lugar["tipo"],
                "organizador_nombre": lugar["organizador"],
                "organizador_web": lugar.get("web"),
                "fecha_inicio": fecha_evento,
                "fecha_fin": fecha_evento if not es_recurrente else fecha_evento + timedelta(days=DIAS_RANGO_EVENTOS),
                "hora_inicio": hora_inicio,
                "hora_fin": hora_fin,
                "es_recurrente": es_recurrente,
                "recurrencia_json": json.dumps(recurrencia_json) if recurrencia_json else None,
                "es_gratuito": es_gratuito,
                "precio": precio,
                "tags_es": plantilla["tags_es"],
                "tags_cat": plantilla["tags_cat"],
                "categoria_slug": categoria_slug,
                "categoria_id": SLUG_TO_ID.get(categoria_slug, 3)  # Default: ocio
            }
            
            eventos.append(evento)
            eventos_generados += 1
        
        print(f"  -> {eventos_generados} eventos generados")
    
    return eventos


# =============================================================================
# GENERADOR DE EMBEDDINGS PARA EVENTOS
# =============================================================================

def build_embedding_text(evento: Dict[str, Any], idioma: str) -> str:
    """
    Construye el texto combinado para el embedding de un evento.
    Incluye: título + descripción (truncada) + tags + categoría.
    Esto permite que el embedding capture TODO el contenido relevante del evento.
    """
    if idioma == "es":
        titulo = evento.get("titulo_es", "")
        desc = evento.get("desc_es", "")[:300]  # Truncar descripción a 300 chars
        tags = " ".join(evento.get("tags_es", []))
    else:
        titulo = evento.get("titulo_cat", "")
        desc = evento.get("desc_cat", "")[:300]
        tags = " ".join(evento.get("tags_cat", []))
    
    # Obtener nombre de categoría
    categoria_slug = evento.get("categoria_slug", "")
    categoria_nombre = {
        "cultura": "Cultura" if idioma == "es" else "Cultura",
        "deportes": "Deportes" if idioma == "es" else "Esports",
        "ocio": "Ocio" if idioma == "es" else "Oci",
        "infantil": "Infantil" if idioma == "es" else "Infantil",
        "formacion": "Formación" if idioma == "es" else "Formació",
        "gastronomia": "Gastronomía" if idioma == "es" else "Gastronomia",
        "musica": "Música" if idioma == "es" else "Música",
        "naturaleza": "Naturaleza" if idioma == "es" else "Naturalesa"
    }.get(categoria_slug, "")
    
    # Construir texto combinado
    # Formato: "TÍTULO. DESCRIPCIÓN. TAGS. CATEGORÍA"
    parts = [titulo, desc, tags, categoria_nombre]
    texto = ". ".join(p for p in parts if p)
    
    return texto


async def add_embeddings_to_events(eventos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Añade embeddings COMBINADOS a todos los eventos.
    El embedding incluye: título + descripción + tags + categoría.
    Esto mejora significativamente el matching semántico.
    """
    print("\n" + "=" * 60)
    print("GENERANDO EMBEDDINGS COMBINADOS CON OPENAI")
    print("(título + descripción + tags + categoría)")
    print("=" * 60)
    
    total = len(eventos)
    batch_size = 20  # Procesar en batches de 20
    
    for i in range(0, total, batch_size):
        batch = eventos[i:i + batch_size]
        
        # Preparar textos COMBINADOS para embedding (no solo tags)
        texts_es = [build_embedding_text(e, "es") for e in batch]
        texts_cat = [build_embedding_text(e, "cat") for e in batch]
        
        # Generar embeddings en batch
        print(f"  Procesando batch {i // batch_size + 1}/{(total + batch_size - 1) // batch_size}...")
        
        embeddings_es = await generate_embeddings_batch(texts_es)
        embeddings_cat = await generate_embeddings_batch(texts_cat)
        
        # Asignar embeddings a eventos
        for j, evento in enumerate(batch):
            evento["embedding_es"] = embeddings_es[j] if j < len(embeddings_es) else []
            evento["embedding_cat"] = embeddings_cat[j] if j < len(embeddings_cat) else []
        
        # Pequeña pausa para no saturar la API
        if i + batch_size < total:
            await asyncio.sleep(0.5)
    
    print(f"  -> {total} eventos con embeddings combinados generados")
    return eventos


# =============================================================================
# INSERCIÓN EN BASE DE DATOS
# =============================================================================

async def insert_base_data(db: DatabaseService):
    """Inserta datos base (ciudades, códigos postales)."""
    print("\nInsertando datos base...")
    
    # Ciudades
    for cp, data in POBLACIONES.items():
        ciudad_id = 1 if cp == "08380" else 5  # Malgrat=1, Blanes=5
        await db.execute_query(
            """
            INSERT INTO CIUDADES (ID_Ciudad, Nombre, Provincia, Latitud, Longitud)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                Nombre=VALUES(Nombre),
                Latitud=VALUES(Latitud),
                Longitud=VALUES(Longitud)
            """,
            (ciudad_id, data["nombre"], data["provincia"], data["lat"], data["lng"])
        )
    print("  -> Ciudades insertadas")
    
    # Códigos postales
    for cp, data in POBLACIONES.items():
        ciudad_id = 1 if cp == "08380" else 5
        await db.execute_query(
            """
            INSERT INTO CODIGOS_POSTALES (CP, ID_Ciudad, Latitud, Longitud)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                Latitud=VALUES(Latitud),
                Longitud=VALUES(Longitud)
            """,
            (cp, ciudad_id, data["lat"], data["lng"])
        )
    print("  -> Códigos postales insertados")


async def insert_events(db: DatabaseService, eventos: List[Dict[str, Any]]):
    """Inserta eventos en la base de datos."""
    print(f"\nInsertando {len(eventos)} eventos...")
    
    inserted = 0
    errors = 0
    
    for evento in eventos:
        try:
            # Insertar evento principal
            await db.execute_query(
                """
                INSERT INTO EVENTOS_MASTER (
                    ID_Unico_Evento, Metodo_Ingesta, ID_Usuario_Carga, Fuente_ID,
                    CP_Evento, Poblacion_Nombre, Lugar_Nombre, Direccion_Fisica,
                    Coordenadas_JSON,
                    Tipo_Organizador, Organizador_Nombre, Organizador_Web,
                    Idioma_Origen, Titulo_ES, Titulo_CAT, 
                    Desc_Larga_ES, Desc_Larga_CAT,
                    Tags_ES, Tags_CAT,
                    Tags_Embedding_ES, Tags_Embedding_CAT,
                    Es_Gratuito, Precio_Euros, Requiere_Inscripcion, Estado
                ) VALUES (
                    %s, 'MANUAL', 'fake_data_generator_v2', 'URL_ESTRUCTURAL',
                    %s, %s, %s, %s,
                    %s,
                    %s, %s, %s,
                    'es', %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, FALSE, 'ACTIVO'
                )
                ON DUPLICATE KEY UPDATE 
                    Titulo_ES=VALUES(Titulo_ES),
                    Tags_Embedding_ES=VALUES(Tags_Embedding_ES),
                    Tags_Embedding_CAT=VALUES(Tags_Embedding_CAT)
                """,
                (
                    evento["id_unico"],
                    evento["cp_evento"],
                    evento["poblacion"],
                    evento["lugar_nombre"],
                    evento.get("direccion"),
                    json.dumps({"lat": evento["lat"], "lng": evento["lng"]}),
                    evento["tipo_organizador"],
                    evento["organizador_nombre"],
                    evento.get("organizador_web"),
                    evento["titulo_es"],
                    evento["titulo_cat"],
                    evento["desc_es"],
                    evento["desc_cat"],
                    json.dumps(evento["tags_es"]),
                    json.dumps(evento["tags_cat"]),
                    json.dumps(evento["embedding_es"]) if evento.get("embedding_es") else None,
                    json.dumps(evento["embedding_cat"]) if evento.get("embedding_cat") else None,
                    evento["es_gratuito"],
                    evento["precio"]
                )
            )
            
            # Insertar horario
            await db.execute_query(
                """
                INSERT INTO EVENTO_HORARIOS (
                    ID_Unico_Evento, Fecha_Inicio, Fecha_Fin, 
                    Hora_Inicio, Hora_Fin,
                    Es_Recurrente, Recurrencia_JSON
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    Fecha_Inicio=VALUES(Fecha_Inicio),
                    Es_Recurrente=VALUES(Es_Recurrente)
                """,
                (
                    evento["id_unico"],
                    evento["fecha_inicio"],
                    evento["fecha_fin"],
                    evento["hora_inicio"],
                    evento["hora_fin"],
                    evento["es_recurrente"],
                    evento.get("recurrencia_json")
                )
            )
            
            # Insertar relación con categoría
            await db.execute_query(
                """
                INSERT INTO EVENTO_CATEGORIAS (ID_Unico_Evento, ID_Categoria)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE ID_Categoria=VALUES(ID_Categoria)
                """,
                (evento["id_unico"], evento["categoria_id"])
            )
            
            inserted += 1
            
        except Exception as e:
            errors += 1
            print(f"  Error insertando evento {evento['id_unico'][:16]}...: {e}")
    
    print(f"  -> {inserted} eventos insertados, {errors} errores")


async def verify_data(db: DatabaseService):
    """Verifica los datos insertados."""
    print("\n" + "=" * 60)
    print("VERIFICACIÓN DE DATOS")
    print("=" * 60)
    
    # Total eventos
    result = await db.execute_query("SELECT COUNT(*) as total FROM EVENTOS_MASTER")
    total = result[0]["total"] if result else 0
    print(f"  Total eventos: {total}")
    
    # Por población
    result = await db.execute_query("""
        SELECT Poblacion_Nombre, COUNT(*) as total 
        FROM EVENTOS_MASTER 
        GROUP BY Poblacion_Nombre
    """)
    for row in result or []:
        print(f"    - {row['Poblacion_Nombre']}: {row['total']}")
    
    # Por tipo organizador
    result = await db.execute_query("""
        SELECT Tipo_Organizador, COUNT(*) as total 
        FROM EVENTOS_MASTER 
        GROUP BY Tipo_Organizador
    """)
    print(f"\n  Por tipo organizador:")
    for row in result or []:
        print(f"    - {row['Tipo_Organizador']}: {row['total']}")
    
    # Con embeddings
    result = await db.execute_query("""
        SELECT COUNT(*) as total 
        FROM EVENTOS_MASTER 
        WHERE Tags_Embedding_ES IS NOT NULL
    """)
    con_embeddings = result[0]["total"] if result else 0
    print(f"\n  Eventos con embeddings: {con_embeddings}")
    
    # Recurrentes
    result = await db.execute_query("""
        SELECT COUNT(*) as total 
        FROM EVENTO_HORARIOS 
        WHERE Es_Recurrente = 1
    """)
    recurrentes = result[0]["total"] if result else 0
    print(f"  Eventos recurrentes: {recurrentes}")


async def clear_existing_events(db: DatabaseService):
    """Limpia eventos existentes (opcional)."""
    print("\nLimpiando eventos existentes...")
    
    await db.execute_query("DELETE FROM EVENTO_CATEGORIAS")
    await db.execute_query("DELETE FROM EVENTO_HORARIOS")
    await db.execute_query("DELETE FROM EVENTOS_MASTER")
    
    print("  -> Eventos eliminados")


# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

async def main(clear_existing: bool = True):
    """Función principal."""
    print("=" * 60)
    print("GENERADOR DE DATOS FAKE v2.0")
    print("Events Query API - Malgrat de Mar & Blanes")
    print("=" * 60)
    print(f"\nConfiguración:")
    print(f"  - Eventos por población: {EVENTOS_POR_POBLACION}")
    print(f"  - Total eventos: {EVENTOS_POR_POBLACION * 2}")
    print(f"  - % Recurrentes: {PORCENTAJE_RECURRENTES * 100}%")
    print(f"  - Rango de fechas: próximos {DIAS_RANGO_EVENTOS} días")
    
    # Crear servicio de BD
    db = DatabaseService()
    
    try:
        # Conectar
        print("\nConectando a la base de datos...")
        await db.connect()
        print("  -> Conectado")
        
        # Limpiar datos existentes (opcional)
        if clear_existing:
            await clear_existing_events(db)
        
        # Insertar datos base
        await insert_base_data(db)
        
        # Generar eventos
        print("\n" + "=" * 60)
        print("GENERANDO EVENTOS")
        print("=" * 60)
        eventos = generate_fake_events()
        print(f"\nTotal eventos generados: {len(eventos)}")
        
        # Generar embeddings
        eventos = await add_embeddings_to_events(eventos)
        
        # Insertar en BD
        await insert_events(db, eventos)
        
        # Verificar
        await verify_data(db)
        
        print("\n" + "=" * 60)
        print("PROCESO COMPLETADO EXITOSAMENTE")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        await db.disconnect()
        print("\nDesconectado de la base de datos")
    
    return 0


if __name__ == "__main__":
    # Argumento opcional para no limpiar datos existentes
    clear = "--no-clear" not in sys.argv
    exit_code = asyncio.run(main(clear_existing=clear))
    sys.exit(exit_code)
