"""
Script de diagnóstico para probar la query "Cuentacuentos en la biblioteca"
"""
import asyncio
import sys
import os
import json

# Añadir el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models.schemas import QueryRequest
from app.services import events_service, db_service, ai_service


async def test_query():
    """Prueba la query problemática con debug completo."""
    
    print("=" * 80)
    print("DIAGNÓSTICO: Query 'Cuentacuentos en la biblioteca' CP 08360")
    print("=" * 80)
    
    # Conectar a la base de datos
    try:
        await db_service.connect()
        print("✓ Conectado a la base de datos\n")
    except Exception as e:
        print(f"✗ Error al conectar a la base de datos: {e}")
        return
    
    # Crear request
    request = QueryRequest(
        pregunta="Cuentacuentos en la biblioteca",
        cp_usuario="08360",
        debug=True
    )
    
    print(f"📝 Pregunta: {request.pregunta}")
    print(f"📍 CP Usuario: {request.cp_usuario}\n")
    
    # Paso 1: Extraer parámetros
    print("-" * 80)
    print("PASO 1: Extracción de parámetros con OpenAI")
    print("-" * 80)
    
    try:
        params = await ai_service.extract_parameters(request.pregunta, request.cp_usuario)
        print(f"✓ Parámetros extraídos:")
        print(json.dumps(params.model_dump(), indent=2, ensure_ascii=False))
        print()
    except Exception as e:
        print(f"✗ Error al extraer parámetros: {e}\n")
        await db_service.disconnect()
        return
    
    # Paso 2: Calcular CPs en radio
    print("-" * 80)
    print("PASO 2: Cálculo de códigos postales en radio")
    print("-" * 80)
    
    if params.radio_km:
        codigos_postales = await db_service.get_codigos_postales_in_radius(
            request.cp_usuario,
            params.radio_km
        )
        print(f"✓ Radio: {params.radio_km} km")
        print(f"✓ CPs encontrados: {codigos_postales}")
    else:
        codigos_postales = [request.cp_usuario]
        print(f"✓ Sin radio especificado, usando solo CP usuario: {codigos_postales}")
    print()
    
    # Paso 3: Construir query SQL
    print("-" * 80)
    print("PASO 3: Construcción de query SQL")
    print("-" * 80)
    
    from app.services.query_builder import query_builder
    query, query_params = query_builder.build_events_query(codigos_postales, params)
    
    print("✓ Query SQL:")
    print(query)
    print(f"\n✓ Parámetros: {query_params}\n")
    
    # Paso 4: Ejecutar query
    print("-" * 80)
    print("PASO 4: Ejecución de query SQL (pre-filtrado)")
    print("-" * 80)
    
    try:
        eventos_raw = await db_service.execute_query(query, query_params)
        print(f"✓ Eventos encontrados en BD: {len(eventos_raw)}")
        
        if eventos_raw:
            print("\nPrimeros 3 eventos:")
            for i, evento in enumerate(eventos_raw[:3], 1):
                print(f"\n{i}. {evento.get('titulo')}")
                print(f"   CP: {evento.get('cp_evento')}")
                print(f"   Fecha: {evento.get('fecha_inicio')}")
                print(f"   Tags: {evento.get('tags_json', 'N/A')[:100]}...")
        else:
            print("\n⚠️  NO SE ENCONTRARON EVENTOS EN LA BD")
            print("\nVerificando si existe el evento en la BD...")
            
            # Query directa para verificar
            verify_query = """
            SELECT 
                em.ID_Unico_Evento,
                em.Titulo_ES,
                em.CP_Evento,
                em.Poblacion_Nombre,
                eh.Fecha_Inicio,
                em.Tags_ES
            FROM EVENTOS_MASTER em
            LEFT JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
            WHERE em.Estado = 'ACTIVO'
            AND em.Titulo_ES LIKE '%Cuentacuentos%'
            AND em.CP_Evento = '08360'
            """
            
            verify_results = await db_service.execute_query(verify_query, ())
            
            if verify_results:
                print(f"\n✓ EVENTO EXISTE EN LA BD:")
                for evento in verify_results:
                    print(f"   - {evento.get('Titulo_ES')}")
                    print(f"     CP: {evento.get('CP_Evento')}")
                    print(f"     Fecha: {evento.get('Fecha_Inicio')}")
                    print(f"     Tags: {evento.get('Tags_ES')}")
                print("\n⚠️  PROBLEMA: El evento existe pero no se recupera con la query principal")
            else:
                print("\n✗ El evento NO existe en la BD")
        
        print()
    except Exception as e:
        print(f"✗ Error al ejecutar query: {e}\n")
        await db_service.disconnect()
        return
    
    # Paso 5: Búsqueda semántica
    if eventos_raw and params.conceptos:
        print("-" * 80)
        print("PASO 5: Búsqueda semántica")
        print("-" * 80)
        
        print(f"✓ Conceptos para búsqueda: {params.conceptos}")
        
        # Generar embedding de conceptos
        conceptos_text = " ".join(params.conceptos)
        user_embedding = await ai_service.generate_embedding(conceptos_text)
        print(f"✓ Embedding generado: {len(user_embedding)} dimensiones")
        
        # Calcular similitud con cada evento
        for i, evento in enumerate(eventos_raw[:5], 1):
            embedding_json = evento.get('tags_embedding_json')
            
            if embedding_json:
                try:
                    if isinstance(embedding_json, str):
                        evento_embedding = json.loads(embedding_json)
                    else:
                        evento_embedding = embedding_json
                    
                    similitud = ai_service.cosine_similarity(user_embedding, evento_embedding)
                    print(f"\n{i}. {evento.get('titulo')}")
                    print(f"   Similitud: {similitud:.3f}")
                    print(f"   {'✓ PASA' if similitud >= 0.6 else '✗ NO PASA'} (umbral: 0.6)")
                except Exception as e:
                    print(f"\n{i}. {evento.get('titulo')}")
                    print(f"   ✗ Error al procesar embedding: {e}")
            else:
                print(f"\n{i}. {evento.get('titulo')}")
                print(f"   ⚠️  Sin embedding")
        
        print()
    
    # Desconectar
    await db_service.disconnect()
    print("=" * 80)
    print("DIAGNÓSTICO COMPLETADO")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_query())
