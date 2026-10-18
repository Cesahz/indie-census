# Indie Census

[Read in English](README.md) · [Leer en español](README.es.md)

Observatorio abierto de datos del ecosistema de desarrollo de videojuegos independiente.

---

> **Estado del proyecto:** En desarrollo activo (`v0.3.0`). Este es un proyecto personal que se construye de forma pausada y metódica, priorizando la solidez de la ingeniería de software y el rigor analítico. Todo módulo se diseña bajo desarrollo guiado por pruebas (TDD), con suites de pruebas herméticas (sin llamadas a la red ni aleatoriedad no controlada), tipado estricto y contratos de datos inmutables antes de cada implementación.

---

## Intención y Visión

Este observatorio nace como una iniciativa personal con el propósito de aportar valor y datos abiertos a la comunidad de desarrollo de videojuegos, analistas e investigadores.

El debate sobre la industria del videojuego independiente —motores utilizados, saturación de tiendas, precios y la irrupción de nuevas tecnologías— suele estar dominado por impresiones anecdóticas, discusiones polarizadas en foros o análisis comerciales que no publican sus datos crudos ni su metodología.

**Indie Census** busca aportar a la comunidad una **fuente pública, citable y metodológicamente auditable** que transforme la conversación empírica en evidencia cuantitativa abierta.

El proyecto no busca validar una postura particular ni se restringe a una herramienta específica, sino medir con neutralidad las transformaciones reales del sector:

1. **Adopción y transición de motores técnicos:** Cómo evolucionan y se distribuyen las tecnologías de desarrollo (motores de código abierto, motores comerciales y herramientas propias) en el catálogo independiente.
2. **Dinámica de precios y sostenibilidad comercial:** Rangos de precios, estrategias de lanzamiento y supervivencia económica de producciones de pequeña escala.
3. **Divulgación de Inteligencia Artificial generativa:** Detección y análisis cuantitativo de las declaraciones de uso de IA en assets y código según las políticas públicas de las plataformas de distribución.
4. **Metodología y datos abiertos:** Publicación no solo de conclusiones o gráficos, sino de los datasets limpios y el código del pipeline para que cualquier persona en la comunidad pueda reproducir o auditar los resultados.
5. **Auditoría de Viabilidad Comercial y Data Science Aplicada:** Evolución desde la observación descriptiva hacia un motor diagnóstico prescriptivo y predictivo. Aportar a desarrolladores, publishers y consultores modelos de regresión y scoring de ventas/pricing, cálculo de densidad competitiva en ventanas de lanzamiento, detección de tags saturados frente a nichos desatendidos, y generación headless automatizada de reportes ejecutivos de auditoría (PDF/JSON).

---

## Arquitectura y Evolución del Proyecto

La plataforma implementa una arquitectura Data Lakehouse de tres capas (Bronce, Plata, Oro) con contratos bloqueantes de calidad de datos en cada transición:

- **Capa Bronce (`data/bronce/`):** Almacenamiento inmutable del payload crudo particionado por fecha UTC y tipo de recurso (`appdetails`, `appreviews`, `applist`), garantizado mediante verificación criptográfica de integridad.
- **Capa Plata (`data/plata/`):** Normalización, tipado estricto con Apache Arrow/Parquet y contratos automatizados de calidad de datos (`dim_game`, `game_review_summary`).
- **Capa Oro (`data/oro/`):** Modelado dimensional Star Schema (`dim_game`, `dim_engine`, `fact_game_performance`) exportado atómicamente a un Data Mart relacional en SQLite (`data/oro/indie_census_mart.db`) para su consulta analítica y conexión con herramientas de BI (Power BI, DuckDB, Metabase).

### Hitos y Versiones

- **Fase 0 — Gobernanza del Repositorio y CI (`v0.0.0`):** Jerarquía canónica de directorios, aislamiento estricto en `.gitignore`, estándar de conventional commits y suite de pruebas de gobernanza.
- **Fase 1 — MVP Vertical Slice (`v0.1.0`):** Cliente HTTP resiliente con control de cuotas 429, gestor persistente de checkpoints tolerante a fallos y muestra de control calibrada de 100 títulos congelada mediante hash SHA-256.
- **Fase 2 — Clasificación Determinista y Enriquecimiento Semántico (`v0.2.0`):** Clasificador jerárquico de motores (niveles de evidencia 1-4), algoritmo multidimensional de autenticidad indie con exclusión de grandes corporaciones, detector formal de divulgación de IA y Star Schema analítico inicial.
- **Fase 3 — Ingesta Masiva y Métricas Comerciales (`v0.3.0`):** Descubrimiento por lotes vía `IStoreService/GetAppList`, barra visual interactiva en consola con cálculo dinámico de ETA, modelo de ventas y recaudación neta Boxleiter multi-era, depuración preventiva de paquetes sin precio y consolidación de **5.759 títulos (4.206 indies confirmados que representan $6.238 millones de USD netos)** en el Data Mart analítico.
- **Fase 4 — Motor de Auditoría de Viabilidad y Reportes Headless (`v0.4.0`, en desarrollo):** Modelado predictivo de ventas y pricing óptimo, cálculo de densidad competitiva en ventanas de lanzamiento, detección de nichos desatendidos vs. tags hipersaturados y generador headless de reportes ejecutivos en PDF y JSON.

---

## Principios de Ingeniería

- **TDD Invariante:** Ningún módulo de extracción, transformación o calidad se implementa sin su correspondiente suite de pruebas previa en verde (commit `test:` antes del commit `feat:`).
- **Hermeticidad total:** Pruebas unitarias y de integración que no tocan la red real; inyección de dependencias para reloj, pausas y generadores aleatorios.
- **Inmutabilidad y trazabilidad:** Los datos crudos jamás se sobreescriben; cualquier recomputación parte de la fuente original histórica.
- **Diseño sin costo:** Ejecución automatizada aprovechando infraestructura ligera y reproducible sin servidores dedicados de pago.
- **Eficiencia de ingesta:** Optimización de cuotas y rendimiento mediante endpoints autenticados por lotes (reducción del 99.4% en tiempo de catalogación y aceleración de 188x frente a endpoints anónimos; consúltese la [evaluación técnica de rendimiento](benchmarks/steam_api_throughput.md)).

---

## Configuración del Entorno

```bash
# 1. Clonar el repositorio
git clone https://github.com/Cesahz/indie-census.git
cd indie-census

# 2. Crear y activar entorno virtual
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate

# 3. Instalar dependencias exactas fijadas
pip install -r requirements.txt

# 4. Configurar variables de entorno (opcional para muestra de control, requerido para descubrimiento masivo)
cp .env.example .env
# Configurar STEAM_API_KEY en .env
```

---

## Ejecución del Pipeline

El orquestador central (`src/pipeline.py`) ofrece dos flujos principales de ejecución:

### 1. Flujo de Muestra de Control (100 Títulos Calibrados)

Ejecuta la extracción, transformación y contratos semánticos sobre el manifiesto congelado de control:

```bash
python -m src.pipeline
```

### 2. Flujo de Catálogo Masivo (Escala Global de Steam)

Descubre, extrae, normaliza y calcula métricas comerciales para subconjuntos extensos del catálogo:

```bash
# Descubrir e ingerir títulos del catálogo generando el Data Mart analítico
python -m src.pipeline --modo masivo --descubrir --max-juegos 6000 --generar-oro

# Reprocesar particiones locales existentes en Bronce sin llamadas a la red
python -m src.pipeline --modo masivo --omitir-extraccion --generar-oro
```

### Referencia de Parámetros CLI

| Parámetro | Tipo | Valor por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--modo` | `control \| masivo` | `control` | Modo de ejecución (`control` usa el manifiesto congelado; `masivo` procesa el catálogo general de Steam). |
| `--descubrir` | Flag | `False` | Activa el descubrimiento dinámico por lotes vía el endpoint autenticado `IStoreService/GetAppList`. |
| `--max-juegos` | Entero | `None` | Límite máximo de títulos a descubrir o procesar en modo masivo. |
| `--generar-oro` | Flag | `False` | Genera el Star Schema y el Data Mart relacional SQLite en capa Oro (`data/oro/indie_census_mart.db`). |
| `--sin-progreso` | Flag | `False` | Desactiva la barra visual de progreso en consola (recomendado para entornos CI/CD sin TTY interactivo). |
| `--omitir-extraccion` | Flag | `False` | Omite la extracción por red y ejecuta transformaciones sobre particiones existentes en Bronce. |
| `--fecha` | `AAAA-MM-DD` | Fecha UTC actual | Partición temporal de ejecución. |
| `--ruta-base` | Ruta de directorio | `data/` | Directorio base de las capas del lago de datos (Bronce, Plata, Oro). |
| `--manifiesto` | Ruta de archivo | `config/muestra_control.yaml` | Ruta al manifiesto YAML de la muestra de control. |

---

## Verificación de Calidad y Pruebas

La suite de pruebas garantiza la integridad y el aislamiento hermético de todos los componentes:

```bash
# Ejecutar la suite completa de pruebas automatizadas
pytest

# Ejecutar únicamente las pruebas de gobernanza y estructura de repositorio
pytest tests/gobernanza/

# Verificación de linter y formato de código
ruff check .
```

---

## Licencia

Este proyecto se distribuye bajo los términos de la [Licencia MIT](LICENSE).


