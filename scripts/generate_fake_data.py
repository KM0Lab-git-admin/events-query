"""
Script para generar datos fake para la base de datos Events Query API.
Genera 5 poblaciones con 25 eventos cada una (total: 125 eventos).
"""

import sys
import os
import asyncio
import json
import hashlib
from datetime import datetime, timedelta, date
from typing import List, Dict, Any
import random

# Añadir el directorio raíz al path para importar módulos
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.database import DatabaseService
from app.config import settings

# Configuración
CIUDADES = [
    {"id": 1, "nombre": "Malgrat de Mar", "provincia": "Barcelona", "comunidad": "Cataluña"},
    {"id": 2, "nombre": "Calella", "provincia": "Barcelona", "comunidad": "Cataluña"},
    {"id": 3, "nombre": "Canet de Mar", "provincia": "Barcelona", "comunidad": "Cataluña"},
    {"id": 4, "nombre": "Pineda de Mar", "provincia": "Barcelona", "comunidad": "Cataluña"},
    {"id": 5, "nombre": "Blanes", "provincia": "Girona", "comunidad": "Cataluña"}
]

CODIGOS_POSTALES = [
    {"cp": "08380", "ciudad_id": 1, "lat": 41.6462, "lng": 2.7411},
    {"cp": "08370", "ciudad_id": 2, "lat": 41.6151, "lng": 2.6600},
    {"cp": "08360", "ciudad_id": 3, "lat": 41.5905, "lng": 2.5805},
    {"cp": "08397", "ciudad_id": 4, "lat": 41.6275, "lng": 2.6931},
    {"cp": "17300", "ciudad_id": 5, "lat": 41.6751, "lng": 2.7928}
]

CATEGORIAS = [
    {"id": 1, "nombre_es": "Cultura", "nombre_cat": "Cultura", "slug": "cultura", "orden": 1},
    {"id": 2, "nombre_es": "Deportes", "nombre_cat": "Esports", "slug": "deportes", "orden": 2},
    {"id": 3, "nombre_es": "Ocio", "nombre_cat": "Oci", "slug": "ocio", "orden": 3},
    {"id": 4, "nombre_es": "Infantil", "nombre_cat": "Infantil", "slug": "infantil", "orden": 4},
    {"id": 5, "nombre_es": "Formación", "nombre_cat": "Formació", "slug": "formacion", "orden": 5},
    {"id": 6, "nombre_es": "Gastronomía", "nombre_cat": "Gastronomia", "slug": "gastronomia", "orden": 6},
    {"id": 7, "nombre_es": "Música", "nombre_cat": "Música", "slug": "musica", "orden": 7},
    {"id": 8, "nombre_es": "Naturaleza", "nombre_cat": "Naturalesa", "slug": "naturaleza", "orden": 8}
]

# Plantillas de eventos por categoría
EVENTOS_TEMPLATES = {
    "cultura": [
        {"titulo_es": "Exposición de arte contemporáneo", "titulo_cat": "Exposició d'art contemporani",
         "tags_es": ["#arte", "#exposicion", "#cultura"], "tags_cat": ["#art", "#exposicio", "#cultura"]},
        {"titulo_es": "Cineclub: Clásicos del cine", "titulo_cat": "Cineclub: Clàssics del cinema",
         "tags_es": ["#cine", "#clasicos", "#cultura"], "tags_cat": ["#cinema", "#classics", "#cultura"]},
        {"titulo_es": "Teatro: Comedia en familia", "titulo_cat": "Teatre: Comèdia en família",
         "tags_es": ["#teatro", "#comedia", "#familia"], "tags_cat": ["#teatre", "#comedia", "#familia"]},
        {"titulo_es": "Conferencia sobre historia local", "titulo_cat": "Conferència sobre història local",
         "tags_es": ["#historia", "#conferencia", "#educativo"], "tags_cat": ["#historia", "#conferencia", "#educatiu"]},
    ],
    "deportes": [
        {"titulo_es": "Torneo de fútbol 7", "titulo_cat": "Torneig de futbol 7",
         "tags_es": ["#futbol", "#torneo", "#deporte"], "tags_cat": ["#futbol", "#torneig", "#esport"]},
        {"titulo_es": "Carrera popular 10K", "titulo_cat": "Cursa popular 10K",
         "tags_es": ["#running", "#carrera", "#deporte"], "tags_cat": ["#running", "#cursa", "#esport"]},
        {"titulo_es": "Clase de yoga al aire libre", "titulo_cat": "Classe de ioga a l'aire lliure",
         "tags_es": ["#yoga", "#aire_libre", "#bienestar"], "tags_cat": ["#ioga", "#aire_lliure", "#benestar"]},
    ],
    "ocio": [
        {"titulo_es": "Mercadillo artesanal", "titulo_cat": "Mercat artesanal",
         "tags_es": ["#mercado", "#artesania", "#compras"], "tags_cat": ["#mercat", "#artesania", "#compres"]},
        {"titulo_es": "Fiesta de la cerveza", "titulo_cat": "Festa de la cervesa",
         "tags_es": ["#cerveza", "#fiesta", "#gastronomia"], "tags_cat": ["#cervesa", "#festa", "#gastronomia"]},
        {"titulo_es": "Concierto de música en vivo", "titulo_cat": "Concert de música en viu",
         "tags_es": ["#musica", "#concierto", "#directo"], "tags_cat": ["#musica", "#concert", "#directe"]},
    ],
    "infantil": [
        {"titulo_es": "Taller de manualidades para niños", "titulo_cat": "Taller de manualitats per a nens",
         "tags_es": ["#infantil", "#taller", "#manualidades"], "tags_cat": ["#infantil", "#taller", "#manualitats"]},
        {"titulo_es": "Cuentacuentos en la biblioteca", "titulo_cat": "Contacontes a la biblioteca",
         "tags_es": ["#infantil", "#cuentos", "#lectura"], "tags_cat": ["#infantil", "#contes", "#lectura"]},
        {"titulo_es": "Parque de atracciones móvil", "titulo_cat": "Parc d'atraccions mòbil",
         "tags_es": ["#infantil", "#atracciones", "#diversión"], "tags_cat": ["#infantil", "#atraccions", "#diversio"]},
    ],
    "formacion": [
        {"titulo_es": "Curso de fotografía digital", "titulo_cat": "Curs de fotografia digital",
         "tags_es": ["#fotografia", "#curso", "#aprendizaje"], "tags_cat": ["#fotografia", "#curs", "#aprenentatge"]},
        {"titulo_es": "Taller de cocina mediterránea", "titulo_cat": "Taller de cuina mediterrània",
         "tags_es": ["#cocina", "#taller", "#gastronomia"], "tags_cat": ["#cuina", "#taller", "#gastronomia"]},
    ],
    "gastronomia": [
        {"titulo_es": "Feria gastronómica local", "titulo_cat": "Fira gastronòmica local",
         "tags_es": ["#gastronomia", "#feria", "#comida"], "tags_cat": ["#gastronomia", "#fira", "#menjar"]},
        {"titulo_es": "Cata de vinos y quesos", "titulo_cat": "Tast de vins i formatges",
         "tags_es": ["#vino", "#queso", "#degustacion"], "tags_cat": ["#vi", "#formatge", "#degustacio"]},
    ],
    "musica": [
        {"titulo_es": "Festival de jazz", "titulo_cat": "Festival de jazz",
         "tags_es": ["#jazz", "#musica", "#festival"], "tags_cat": ["#jazz", "#musica", "#festival"]},
        {"titulo_es": "Concierto de música clásica", "titulo_cat": "Concert de música clàssica",
         "tags_es": ["#clasica", "#musica", "#concierto"], "tags_cat": ["#classica", "#musica", "#concert"]},
    ],
    "naturaleza": [
        {"titulo_es": "Excursión guiada por la montaña", "titulo_cat": "Excursió guiada per la muntanya",
         "tags_es": ["#naturaleza", "#senderismo", "#aire_libre"], "tags_cat": ["#naturalesa", "#senderisme", "#aire_lliure"]},
        {"titulo_es": "Limpieza de playa", "titulo_cat": "Neteja de platja",
         "tags_es": ["#playa", "#medio_ambiente", "#voluntariado"], "tags_cat": ["#platja", "#medi_ambient", "#voluntariat"]},
    ]
}


def generate_id_unico(titulo: str, fecha: date, ciudad_id: int) -> str:
    """Genera un ID único para un evento."""
    data = f"{titulo}{fecha.isoformat()}{ciudad_id}"
    return hashlib.sha256(data.encode()).hexdigest()


def generate_fake_events(num_events_per_city: int = 25) -> List[Dict[str, Any]]:
    """Genera eventos fake."""
    eventos = []
    fecha_inicio = datetime.now().date()
    
    for ciudad in CIUDADES:
        cp_info = next(cp for cp in CODIGOS_POSTALES if cp["ciudad_id"] == ciudad["id"])
        
        for i in range(num_events_per_city):
            # Seleccionar categoría aleatoria
            categoria = random.choice(CATEGORIAS)
            slug = categoria["slug"]
            
            # Seleccionar template de evento
            if slug in EVENTOS_TEMPLATES:
                template = random.choice(EVENTOS_TEMPLATES[slug])
            else:
                template = random.choice(EVENTOS_TEMPLATES["ocio"])
            
            # Generar fecha aleatoria (próximos 60 días)
            dias_adelante = random.randint(0, 60)
            fecha_evento = fecha_inicio + timedelta(days=dias_adelante)
            
            # Generar ID único
            id_unico = generate_id_unico(template["titulo_es"], fecha_evento, ciudad["id"])
            
            # Precio (60% gratuitos, 40% de pago)
            es_gratuito = random.random() < 0.6
            precio = None if es_gratuito else round(random.uniform(5, 50), 2)
            
            # Hora
            hora_inicio = f"{random.randint(9, 21):02d}:{random.choice(['00', '30'])}:00"
            hora_fin = f"{random.randint(10, 23):02d}:{random.choice(['00', '30'])}:00"
            
            # Descripción
            desc_corta_es = f"Evento de {categoria['nombre_es'].lower()} en {ciudad['nombre']}"
            desc_corta_cat = f"Esdeveniment de {categoria['nombre_cat'].lower()} a {ciudad['nombre']}"
            
            evento = {
                "id_unico": id_unico,
                "titulo_es": f"{template['titulo_es']} - {ciudad['nombre']}",
                "titulo_cat": f"{template['titulo_cat']} - {ciudad['nombre']}",
                "desc_corta_es": desc_corta_es,
                "desc_corta_cat": desc_corta_cat,
                "cp_evento": cp_info["cp"],
                "poblacion": ciudad["nombre"],
                "lat": cp_info["lat"] + random.uniform(-0.01, 0.01),
                "lng": cp_info["lng"] + random.uniform(-0.01, 0.01),
                "fecha_inicio": fecha_evento,
                "fecha_fin": fecha_evento,
                "hora_inicio": hora_inicio,
                "hora_fin": hora_fin,
                "es_gratuito": es_gratuito,
                "precio": precio,
                "tags_es": json.dumps(template["tags_es"]),
                "tags_cat": json.dumps(template["tags_cat"]),
                "categoria_id": categoria["id"],
                "ciudad_id": ciudad["id"]
            }
            
            eventos.append(evento)
    
    return eventos


async def insert_data(db: DatabaseService):
    """Inserta datos fake en la base de datos."""
    print("Insertando ciudades...")
    for ciudad in CIUDADES:
        await db.execute_query(
            """
            INSERT INTO CIUDADES (ID_Ciudad, Nombre, Provincia)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE Nombre=VALUES(Nombre)
            """,
            (ciudad["id"], ciudad["nombre"], ciudad["provincia"])
        )
    print(f"✓ {len(CIUDADES)} ciudades insertadas")
    
    print("Insertando códigos postales...")
    for cp in CODIGOS_POSTALES:
        await db.execute_query(
            """
            INSERT INTO CODIGOS_POSTALES (CP, ID_Ciudad, Latitud, Longitud)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE Latitud=VALUES(Latitud), Longitud=VALUES(Longitud)
            """,
            (cp["cp"], cp["ciudad_id"], cp["lat"], cp["lng"])
        )
    print(f"✓ {len(CODIGOS_POSTALES)} códigos postales insertados")
    
    print("Insertando categorías...")
    for cat in CATEGORIAS:
        await db.execute_query(
            """
            INSERT INTO CATEGORIAS (ID_Categoria, Nombre_ES, Nombre_CAT, Slug, Orden, Activo)
            VALUES (%s, %s, %s, %s, %s, TRUE)
            ON DUPLICATE KEY UPDATE Nombre_ES=VALUES(Nombre_ES), Nombre_CAT=VALUES(Nombre_CAT)
            """,
            (cat["id"], cat["nombre_es"], cat["nombre_cat"], cat["slug"], cat["orden"])
        )
    print(f"✓ {len(CATEGORIAS)} categorías insertadas")
    
    print("Generando eventos fake...")
    eventos = generate_fake_events(25)
    print(f"✓ {len(eventos)} eventos generados")
    
    print("Insertando eventos...")
    for evento in eventos:
        # Insertar evento
        await db.execute_query(
            """
            INSERT INTO EVENTOS_MASTER (
                ID_Unico_Evento, Metodo_Ingesta, ID_Usuario_Carga, Fuente_ID,
                ID_Ciudad, CP_Evento, Poblacion_Nombre, Lugar_Nombre,
                Idioma_Origen, Titulo_ES, Titulo_CAT, Desc_Larga_ES, Desc_Larga_CAT,
                Tags_ES, Tags_CAT, Es_Gratuito, Precio_Euros, Requiere_Inscripcion, Estado
            ) VALUES (%s, 'MANUAL', 'fake_data_generator', 'URL_ESTRUCTURAL', %s, %s, %s, 'Lugar del evento',
                     'es', %s, %s, %s, %s, %s, %s, %s, %s, FALSE, 'ACTIVO')
            ON DUPLICATE KEY UPDATE Titulo_ES=VALUES(Titulo_ES)
            """,
            (
                evento["id_unico"],
                evento["ciudad_id"], evento["cp_evento"], evento["poblacion"],
                evento["titulo_es"], evento["titulo_cat"],
                evento["desc_corta_es"], evento["desc_corta_cat"],
                evento["tags_es"], evento["tags_cat"],
                evento["es_gratuito"], evento["precio"]
            )
        )
        
        # Insertar horario
        await db.execute_query(
            """
            INSERT INTO EVENTO_HORARIOS (
                ID_Unico_Evento, Fecha_Inicio, Fecha_Fin, Hora_Inicio, Hora_Fin
            ) VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE Fecha_Inicio=VALUES(Fecha_Inicio)
            """,
            (
                evento["id_unico"], evento["fecha_inicio"], evento["fecha_fin"],
                evento["hora_inicio"], evento["hora_fin"]
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
    
    print(f"✓ {len(eventos)} eventos insertados")
    
    # Verificar
    result = await db.execute_query("SELECT COUNT(*) as total FROM EVENTOS_MASTER")
    total_eventos = result[0]["total"] if result else 0
    print(f"\n✓ Total eventos en BD: {total_eventos}")


async def main():
    """Función principal."""
    print("=" * 60)
    print("GENERADOR DE DATOS FAKE - Events Query API")
    print("=" * 60)
    
    # Crear servicio de BD
    db = DatabaseService()
    
    try:
        # Conectar
        print("\nConectando a la base de datos...")
        await db.connect()
        print("✓ Conectado")
        
        # Insertar datos
        await insert_data(db)
        
        print("\n" + "=" * 60)
        print("✓ DATOS GENERADOS EXITOSAMENTE")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        # Desconectar
        await db.disconnect()
        print("\n✓ Desconectado")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
