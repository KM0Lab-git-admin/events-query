# 📄 Especificación Técnica: Motor de Ingesta y Gestión de Eventos VAC 360

Este documento la lógica de datos y protocolos de Inteligencia Artificial para el sistema de eventos. Diseñado para su implementación por desarrolladores senior o agentes de IA.

---

## 1. Arquitectura de Datos (Modelo Relacional)

El sistema se organiza en **6 niveles jerárquicos** para garantizar la integridad referencial y permitir cálculos espaciales de proximidad.

### Nivel 1: Geografía Central
* **`CIUDADES`**: Maestro de poblaciones. Almacena el nombre, provincia y el **Centroide** (Lat/Lng) del municipio.
* **`CODIGOS_POSTALES`**: Tabla de precisión para el cálculo de distancias. Cada CP tiene sus propias coordenadas. Es la base para el "Filtro Maestro".

### Nivel 2: Usuario y Proximidad
* **`PERFIL_USUARIO`**: Define el punto de anclaje (`CP_Origen`) y el `Radio_Busqueda_KM`.
    * *Lógica:* El sistema debe usar la fórmula de **Haversine** para comparar las coordenadas del usuario con las del evento.

### Nivel 3 y 4: Estrategia de Captura
* **`MAPEO_REDES_POBLACION`**: Diccionario de búsqueda para la IA (Hashtags, Handles, Plataformas).
* **`FUENTES_FAMILIA`**: Agrupación por entidad organizadora (Ayuntamientos, Entidades Privadas).

### Nivel 5: El Evento Maestro (Las 7 Dimensiones)
La tabla `EVENTOS_MASTER` se divide en bloques lógicos:
1.  **General**: Trazabilidad e IDs.
2.  **Localización**: Lugar físico y coordenadas.
3.  **Organizador**: Datos de la entidad.
4.  **Contenido**: Textos bilingües (CAT/ES) y etiquetas IA.
5.  **Temporalidad**: Vinculada a la tabla hija de horarios.
6.  **Economía**: Precios, aforo y ticketing.
7.  **Multimedia**: URLs de imágenes y binarios.

### Nivel 6: Tablas Hijas y Auditoría
* **`EVENTO_HORARIOS`**: Normalización de horas y recurrencias.
* **`BINARIOS_STORAGE`**: Gestión de archivos (PDF, PNG, DOCX).
* **`AUDITORIA_SCRAPING`**: Registro de texto bruto (Raw Text) para verificación de procesos IA.

---

## 2. Protocolo de Ingesta IA (Fuente_ID)

La IA debe clasificar cada extracción mediante el campo `Fuente_ID`. Esto define la tecnología utilizada y el nivel de confianza del dato:

| Fuente_ID | Tecnología | Método de Aplicación |
| :--- | :--- | :--- |
| **`URL_ESTRUCTURAL`** | Web Scraping (DOM) | Parseo de código HTML. Máxima precisión en campos numéricos. |
| **`SOCIAL_VISUAL`** | Computer Vision (OCR) | Extracción de datos desde carteles/imágenes cuando no hay texto. |
| **`SOCIAL_SEMANTICA`** | NLP (Procesamiento) | Interpretación de lenguaje natural ("mañana", "gratis", "en el centro"). |

---

## 3. Lógica de Temporalidad y Recurrencia

Para evitar la duplicidad de registros, el sistema gestiona la recurrencia mediante un objeto **JSON** y una tabla de horarios normalizada.

### Ejemplo de Configuración de Recurrencia:
Para un evento que ocurre: **Martes y Jueves, de 08:00 a 10:00, entre Agosto y Octubre.**

**Campo `Recurrencia_JSON`:**
```json
{
  "tipo": "semanal",
  "intervalo": 1,
  "regla": {
    "dias_semana": ["martes", "jueves"],
    "meses_activos": [8, 9, 10],
    "finalizacion": { "tipo": "fecha", "valor": "2026-10-31" }
  },
  "horarios": [{ "inicio": "08:00", "fin": "10:00" }]
}


5. Reglas de Validación para la IA (Data Quality)
Para que el dato sea persistido en la base de datos, la IA debe ejecutar las siguientes validaciones:

A. Validación de Integridad Geográfica
Regla: Si el origen de datos no especifica calle o coordenadas, la IA debe asignar automáticamente el Centroide de la CIUDAD vinculada y el CP más probable según el MAPEO_REDES.

Objetivo: Evitar que un evento quede fuera del "Filtro Maestro" por falta de coordenadas.

B. Validación Bilingüe Obligatoria
Regla: Si la fuente solo contiene información en un idioma (ej. Catalán), la IA debe realizar una traducción automática de alta calidad para los campos espejo en Castellano (Titulo_ES, Desc_Larga_ES) y viceversa.

Excepción: Los nombres propios de bandas o artistas no se traducen.

C. Validación de Temporalidad Relativa
Regla: Cuando se usa SOCIAL_SEMANTICA, la IA debe convertir expresiones relativas ("este viernes", "próximo finde") en fechas absolutas (YYYY-MM-DD) usando como referencia el campo Fecha_Creacion del post.

D. Validación de Veracidad Multimedia (OCR)
Regla: Todo proceso SOCIAL_VISUAL debe cruzar el texto extraído del cartel con el texto del post. En caso de contradicción en la fecha o el precio, la IA marcará el registro como Estado: PENDIENTE_REVISION y guardará el error en AUDITORIA_SCRAPING.

E. Limpieza de Contenido (Sanitización)
Regla: Se deben eliminar emojis, llamadas a la acción genéricas ("¡Síguenos!", "Link en la bio") y etiquetas de redes sociales del campo Desc_Larga para mantener la limpieza estética en el frontend.