# Indie Census

[Read in English](README.md) · [Leer en español](README.es.md)

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Tests](https://img.shields.io/badge/tests-383%20passed-brightgreen.svg)
![Coverage](https://img.shields.io/badge/coverage-93%25-brightgreen.svg)
![Architecture](https://img.shields.io/badge/architecture-Data%20Lakehouse-orange.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Code Style](https://img.shields.io/badge/code%20style-ruff-000000.svg)

Observatorio abierto de datos del ecosistema de desarrollo de videojuegos independiente.

> **Estado del proyecto:** En desarrollo activo (`v0.3.4`). Este es un proyecto personal que se construye de forma pausada y metódica, priorizando la solidez de la ingeniería de software y el rigor analítico. Todo módulo se diseña bajo desarrollo guiado por pruebas (TDD), con suites de pruebas herméticas (sin llamadas a la red ni aleatoriedad no controlada), tipado estricto y contratos de datos inmutables antes de cada implementación.

## Visión General y Áreas de Enfoque

Los debates en torno al desarrollo independiente—adopción de motores, saturación de la tienda, dinámicas de precios o divulgación de IA generativa—suelen basarse en impresiones anecdóticas o reportes comerciales cerrados con metodologías no auditables.

Indie Census provee una plataforma de datos abierta, reproducible y verificable que transforma la conversación empírica en evidencia cuantitativa. El observatorio analiza cinco áreas principales:

1. **Adopción de Motores de Videojuegos:** Distribución y evolución de tecnologías de desarrollo (motores de código abierto como Godot, comerciales como Unity/Unreal y frameworks propios) a lo largo del catálogo.
2. **Dinámica de Precios:** Rangos de precios, patrones de lanzamiento y distribución comercial en producciones independientes.
3. **Divulgación de IA Generativa:** Monitoreo y análisis cuantitativo del uso declarado de IA en assets y código según descriptores formales de la plataforma.
4. **Datos Abiertos y Reproducibilidad:** Publicación de datasets limpios y código fuente del pipeline para que cualquier hallazgo pueda ser auditado y reproducido de forma independiente.
5. **Modelado de Viabilidad Comercial:** Modelado econométrico Boxleiter multi-era de copias e ingresos netos, cálculo de densidad competitiva en ventanas de lanzamiento y detección de nichos desatendidos.

## Arquitectura

La plataforma implementa una arquitectura Data Lakehouse de tres capas con contratos bloqueantes de calidad de datos en cada transición:

- **Capa Bronce (`data/bronce/`):** Almacenamiento inmutable del payload crudo particionado por fecha UTC y tipo de recurso (`appdetails`, `appreviews`, `applist`), validado mediante hashes criptográficos SHA-256.
- **Capa Plata (`data/plata/`):** Normalización tipada estricta mediante Apache Arrow y Parquet comprimido en Snappy, fechas ISO-8601, parseo de tablas HTML de idiomas y clasificación semántica (`dim_game`, `game_review_summary`).
- **Capa Oro (`data/oro/`):** Modelado dimensional Star Schema (`dim_game`, `dim_date`, `dim_genre_bridge`, `fact_game_performance`) exportado a un Data Mart relacional en SQLite (`data/oro/indie_census_mart.db`) con índices B-Tree para consumo en BI.

### Cronograma de Versiones e Hitos

- **Fase 0 — Gobernanza del Repositorio y CI (`v0.0.0`):** Jerarquía canónica de directorios, aislamiento en `.gitignore`, estándar de conventional commits y suite de pruebas de gobernanza.
- **Fase 1 — MVP Vertical Slice (`v0.1.0`):** Cliente HTTP resiliente con control de cuotas 429, gestor persistente de checkpoints tolerante a fallos y muestra de control calibrada de 100 títulos bloqueada mediante hash SHA-256.
- **Fase 2 — Clasificación Determinista y Semántica (`v0.2.0`):** Clasificador jerárquico de motores (niveles de evidencia 1 a 4), algoritmo multidimensional de autenticidad indie con exclusión de grandes corporaciones, detector formal de divulgación de IA y Star Schema inicial.
- **Fase 3 — Ingesta Masiva y Métricas Comerciales (`v0.3.0`):** Descubrimiento por lotes vía `IStoreService/GetAppList`, barra visual interactiva en consola con cálculo dinámico de ETA, y modelo Boxleiter de copias y recaudación neta multi-era.
- **Extensión de Fase 3 — Sharding Distribuido y Telemetría (`v0.3.1`):** Sharding modular determinista por AppID (`idx % N`) entre nodos de cómputo (PC Local y Google Colab Pro), congelación de manifiesto maestro inmutable, sincronización de snapshots tar.gz y colector de telemetría de red.
- **Extensión de Fase 3 — Reconciliación Cero-Huecos y Auditoría Forense (`v0.3.2` – `v0.3.4`):** Unificador atómico de snapshots sin huecos, auditoría de completitud al 100% contra el manifiesto maestro, Contrato 10 bloqueante de verificación criptográfica y consolidación de **63.770 títulos (57.011 indies auténticos que representan $7.120M USD netos estimados)** en el Data Mart de la capa Oro (`data/oro/indie_census_mart.db`).
- **Fase 4 — Capa Oro Analítica, CI y Dataset Abierto (`v0.4.0`, próxima fase):** Tablas maestras agregadas (penetración de motores, distribución de precios, saturación), re-extracción de reseñas para neutralizar sesgo idiomático (`language=all`), enriquecimiento de tags comunitarios, automatización en GitHub Actions y publicación del dataset abierto (Parquet/CSV).
- **Fase 5 — Data Science Aplicada y Viabilidad Comercial (`v0.5.0`):** Modelos predictivos de regresión y pricing de ventas, densidad competitiva en ventanas de lanzamiento y detección algorítmica de nichos desatendidos.
- **Fase 6 — Reportes Ejecutivos Headless (`v1.0.0`):** Generador desatendido de informes de auditoría ejecutiva exportables en PDF y JSON y CLI analítica desacoplada.

## Principios de Ingeniería

- **TDD Estricto:** Ningún módulo de extracción, transformación o calidad se implementa sin su correspondiente suite de pruebas previa en verde (flujo `test:` antes de `feat:`).
- **Hermeticidad Total:** Pruebas unitarias y de integración que no realizan llamadas a la red; inyección de dependencias para reloj, pausas y generadores aleatorios.
- **Inmutabilidad en Lakehouse:** Los datos crudos jamás se sobreescriben; toda recomputación parte deterministamente de la fuente histórica en Bronce.
- **Infraestructura de Bajo Costo (Local-First):** Ejecución automatizada y reproducible en hardware ligero sin dependencias de servidores en la nube de pago.
- **Ingesta Distribuida:** Sharding modular determinista (`idx % total_workers == worker_id`) con aceleración comprobada de 2.21x en nodos cloud y recolección de más de 101.000 títulos crudos (consúltese la [evaluación de rendimiento distribuido](benchmarks/comparativa_nodos_pc_vs_colab.md)).
- **Resiliencia HTTP y Control de Tasa:** Algoritmo automático de backoff exponencial adaptativo con jitter y lectura del encabezado `Retry-After`, gestionando con seguridad más de 34.000 respuestas HTTP 429 sin caídas de servicio (consúltese la [evaluación técnica de rendimiento](benchmarks/steam_api_throughput.md)).

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

# Reprocesar particiones locales existentes en Bronce sin llamadas a la red (63.770 títulos)
python -m src.pipeline --modo masivo --omitir-extraccion --generar-oro --fecha 2026-10-18
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

## Licencia

Este proyecto se distribuye bajo los términos de la [Licencia MIT](LICENSE).
