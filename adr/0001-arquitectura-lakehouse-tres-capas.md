# ADR-0001: Arquitectura Lakehouse Inmutable de Tres Capas (Bronce, Plata, Oro)

- **Estado:** Aceptado
- **Fecha:** 2026-10-14

## Contexto y Problema
La recolección masiva del catálogo de Steam (~110.000 aplicaciones) está expuesta a interrupciones de red, cambios silenciosos en la estructura de las respuestas JSON del proveedor, errores en reglas de negocio (como sesgos de parámetros o ajustes en algoritmos de clasificación) y límites de tasa HTTP 429. Si los datos se transformaran al vuelo y se insertaran directamente en una base de datos relacional única, cualquier bug en la lógica de parseo o clasificación corrompería los datos históricos y obligaría a volver a consultar la API de Steam durante decenas de horas.

## Alternativas Consideradas
1. **Ingesta directa a base de datos relacional (PostgreSQL / SQLite directo):** Descartada porque acopla la extracción de red con el esquema analítico; un fallo de parseo pierde el payload original y obliga a re-extraer desde la red.
2. **Almacenamiento plano en CSV sin particionamiento ni esquemas fuertes:** Descartada por pérdida de tipos de datos (fechas, listas anidadas de géneros/idiomas, nulos ambiguos) y degradación severa de lectura a escala.
3. **Arquitectura Data Lakehouse local de tres capas (Bronce JSON con SHA-256, Plata Parquet/Arrow tipado, Oro Star Schema SQLite/Parquet):** Seleccionada.

## Decisión
Adoptar una arquitectura Lakehouse local estricta de tres capas:
- **Capa Bronce (`data/bronce/`):** Archivos JSON crudos inmutables particionados por fuente, recurso y fecha UTC (`fecha=AAAA-MM-DD/appid=<id>.json`), envueltos con metadatos de linaje y huella criptográfica SHA-256. Prohibida la sobrescritura.
- **Capa Plata (`data/plata/`):** Tablas normalizadas en formato Apache Parquet con esquemas `pyarrow` explícitos y escrituras atómicas mediante archivos temporales (`.tmp` + `os.replace`), protegidas por contratos de calidad bloqueantes en memoria antes de tocar disco.
- **Capa Oro (`data/oro/`):** Modelo dimensional en estrella (`dim_game`, `dim_date`, `dim_genre_bridge`, `fact_game_performance`) materializado en Parquet y en un Data Mart SQLite indexado (`indie_census_mart.db`).

## Consecuencias y Costos Aceptados
- **Costo en disco y de I/O local:** Mantener más de 220.000 archivos JSON pequeños en la capa Bronce consume varios gigabytes y penaliza el escaneo del sistema de archivos en Windows (NTFS) al reconstruir la capa Plata (~2-3 minutos de lectura secuencial).
- **Beneficio determinante:** Cualquier recalibración taxonómica (como el ajuste de `indie_score` en `v0.3.4`) se aplica reprocesando Bronce → Plata → Oro en minutos y sin realizar una sola petición HTTP adicional.

