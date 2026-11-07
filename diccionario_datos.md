# Diccionario de Datos del Observatorio Indie Census

Este documento contiene el catálogo formal y la especificación técnica de todas las columnas y variables publicadas en el dataset abierto de **Indie Census** (versión v0.4.0). Sigue el estándar de catalogación estructurada de **FiveThirtyEight** y **Our World in Data**.

---

## Índice de Tablas Maestras

| Nombre de Tabla | Capa | Granularidad | Formatos Disponibles | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| **`dim_game`** | Plata | 1 fila por videojuego (`game_id`) | Parquet, CSV | Dimensión de catálogo normalizado, clasificación indie, motor detectado y metadatos editoriales. |
| **`game_review_summary`** | Plata | 1 fila por videojuego (`game_id`) | Parquet, CSV | Métricas crudas de reseñas positivas, negativas y volumen total de interacción. |
| **`fact_game_performance`** | Oro | 1 fila por videojuego (`game_id`) | Parquet, CSV | Tabla de hechos analítica con precios en USD, copias estimadas (Boxleiter) e ingresos brutos/netos. |
| **`gold_engine_adoption_monthly`** | Oro | 1 fila por cohorte (`year_month`, `engine`, `is_indie`) | Parquet, CSV, SQLite | Adopción mensual y cuota de mercado temporal de motores (Godot, Unity, Unreal, etc.). |
| **`gold_pricing_by_genre`** | Oro | 1 fila por categoría (`genre`, `is_indie`) | Parquet, CSV, SQLite | Distribución y percentiles de precios (p25, mediana, p75) y tasas de gratuidad por género. |
| **`gold_market_saturation_monthly`** | Oro | 1 fila por cohorte (`year_month`, `genre`) | Parquet, CSV, SQLite | Serie temporal del índice de saturación mensual y volumen de lanzamientos independientes. |

---

## 1. Tabla: `dim_game` (Capa Plata)

Contiene la dimensión limpia de videojuegos catalogados en Steam tras el procesamiento de entidades y la evaluación semántica.

- **Clave Primaria:** `game_id`
- **Granularidad:** 1 fila por videojuego único (`appid`).

| Columna | Tipo Arrow / SQL | Unidad / Formato | Nulos | Definición Conceptual | Fuente Primaria |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `game_id` | `int64` / `INTEGER` | Identificador entero | No | Identificador único de aplicación en Steam (`appid`). | Valve Web API |
| `title` | `string` / `TEXT` | Texto UTF-8 | No | Título comercial oficial del videojuego en la tienda. | `appdetails` |
| `release_date` | `string` / `TEXT` | `YYYY-MM-DD` | Sí | Fecha oficial de publicación en el catálogo de Steam. | `appdetails` |
| `is_free` | `bool_` / `INTEGER` | Booleano (1/0) | No | Indica si el videojuego es de distribución gratuita (Free-to-Play). | `appdetails` |
| `price_launch_usd_cents`| `int64` / `INTEGER` | Centavos de USD | No | Precio base de catálogo en centavos (ej. 1999 = \$19.99 USD). | `appdetails` |
| `genres` | `list<string>` / `TEXT` | Lista / JSON array | No | Categorías taxonómicas oficiales asignadas en la ficha de tienda. | `appdetails` |
| `language_count` | `int32` / `INTEGER` | Conteo entero | No | Cantidad de idiomas soportados declarados por el desarrollador. | `appdetails` |
| `developers` | `list<string>` / `TEXT` | Lista / JSON array | No | Nombres de los estudios o individuos acreditados como desarrolladores. | `appdetails` |
| `publishers` | `list<string>` / `TEXT` | Lista / JSON array | No | Nombres de las entidades que publican y comercializan el juego. | `appdetails` |
| `group` | `string` / `TEXT` | Categoría | No | Clasificación editorial (`indie`, `aa_midmarket`, `aaa_major`). | Clasificador Semántico |
| `engine` | `string` / `TEXT` | Categoría | Sí | Motor tecnológico detectado (`Godot`, `Unity`, `Unreal`, `Custom/Other`). | Clasificador Nivel 1/2 |
| `engine_evidence_level` | `int8` / `INTEGER` | Nivel (1 a 4 o nulo) | Sí | Nivel de certeza de la evidencia técnica (1=Texto/Créditos, 2=Tags, 3=Firma técnica comprobada, 4=Regex descripción). | Clasificador Motor |
| `indie_score` | `float64` / `REAL` | Escala 0.00 a 1.00 | No | Puntuación continua de independencia según evidencia semántica. | Algoritmo Indie Score |
| `is_indie` | `bool_` / `INTEGER` | Booleano (1/0) | No | Booleano final de demarcación: `True` si `indie_score >= 0.60` y sin major publisher excluido. | Algoritmo Indie Score |
| `ai_disclosure_level` | `string` / `TEXT` | Categoría | No | Nivel ético y formal de declaración de IA generativa (`declared`, `tagged`, `self_reported`, `unknown`). | Clasificador Semántico (`src/classify/ai.py`) |
| `source` | `string` / `TEXT` | Categoría | No | Origen de la ingesta (ej. `steam_store`). | Extractor Bronce |
| `extracted_at` | `string` / `TEXT` | ISO-8601 UTC | No | Marca temporal en la que se extrajo el payload crudo original. | Envoltorio Bronce |
| `pipeline_version` | `string` / `TEXT` | SemVer (`vX.Y.Z`) | No | Versión del pipeline de datos con la que se procesó la fila. | Pipeline Engine |

---

## 2. Tabla: `game_review_summary` (Capa Plata)

Contiene la recepción cuantitativa de la comunidad de usuarios por videojuego.

- **Clave Primaria:** `game_id`
- **Granularidad:** 1 fila por videojuego único.

| Columna | Tipo Arrow / SQL | Unidad / Formato | Nulos | Definición Conceptual | Fuente Primaria |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `game_id` | `int64` / `INTEGER` | Identificador entero | No | Identificador del juego (clave foránea a `dim_game`). | Valve Web API |
| `total_positive` | `int64` / `INTEGER` | Conteo entero | No | Cantidad acumulada de votos y reseñas positivas emitidas. | Steam Reviews API |
| `total_negative` | `int64` / `INTEGER` | Conteo entero | No | Cantidad acumulada de votos y reseñas negativas emitidas. | Steam Reviews API |
| `total_reviews` | `int64` / `INTEGER` | Conteo entero | No | Volumen total de reseñas registradas ($\text{pos} + \text{neg}$). | Steam Reviews API |
| `extracted_at` | `string` / `TEXT` | ISO-8601 UTC | No | Marca temporal UTC de la captura de reseñas. | Envoltorio Bronce |
| `pipeline_version` | `string` / `TEXT` | SemVer (`vX.Y.Z`) | No | Versión del pipeline utilizada para normalizar las métricas. | Pipeline Engine |

---

## 3. Tabla: `fact_game_performance` (Capa Oro)

Tabla analítica central de hechos que consolida métricas económicas y proyecciones Boxleiter por título.

- **Clave Primaria:** `game_id`
- **Granularidad:** 1 fila por videojuego.

| Columna | Tipo Arrow / SQL | Unidad / Formato | Nulos | Definición Conceptual |
| :--- | :--- | :--- | :--- | :--- |
| `game_id` | `int64` / `INTEGER` | Identificador entero | No | Identificador foráneo a `dim_game`. |
| `release_date_key` | `int32` / `INTEGER` | Clave `YYYYMMDD` | Sí | Clave subrogada entera de unión hacia la dimensión de fechas (`dim_date`). |
| `price_usd` | `float64` / `REAL` | Dólares USD | No | Precio base en formato decimal normalizado. |
| `is_free` | `bool_` / `INTEGER` | Booleano (1/0) | No | Indicador de juego sin costo de compra directo. |
| `total_positive` | `int64` / `INTEGER` | Conteo entero | No | Reseñas positivas consolidadas. |
| `total_negative` | `int64` / `INTEGER` | Conteo entero | No | Reseñas negativas consolidadas. |
| `total_reviews` | `int64` / `INTEGER` | Conteo entero | No | Total de reseñas acumuladas. |
| `approval_rate` | `float64` / `REAL` | Porcentaje 0 a 100 | Sí | Ratio de aprobación de la comunidad ($\text{pos} / \text{total} \times 100$). |
| `est_copies_min` | `int64` / `INTEGER` | Unidades | No | Estimación inferior conservadora de copias vendidas. |
| `est_copies_mid` | `int64` / `INTEGER` | Unidades | No | Estimación mediana (baseline Boxleiter calibrado) de ventas. |
| `est_copies_max` | `int64` / `INTEGER` | Unidades | No | Estimación superior de copias vendidas. |
| `est_gross_revenue_usd`| `float64` / `REAL` | Dólares USD | No | Proyección de facturación bruta ($\text{est\_copies\_mid} \times \text{price\_usd}$). |
| `est_net_revenue_usd` | `float64` / `REAL` | Dólares USD | No | Rendimiento neto desarrollador tras comisión 30%, impuestos y devoluciones. |
| `language_count` | `int32` / `INTEGER` | Conteo entero | No | Diversificación lingüística del título. |

---


---

## 3.1. Tabla: `dim_date` (Capa Oro - Data Mart Relacional)

Dimensión temporal calendario para análisis multidimensional en el Data Mart analítico SQLite.

- **Clave Primaria:** `date_key`
- **Granularidad:** 1 fila por día calendario.

| Columna | Tipo SQL | Formato | Nulos | Definición Conceptual |
| :--- | :--- | :--- | :--- | :--- |
| `date_key` | `INTEGER` | `YYYYMMDD` | No | Clave primaria entera subrogada. |
| `full_date` | `TEXT` | `YYYY-MM-DD` | No | Fecha completa en formato ISO-8601. |
| `year` | `INTEGER` | Año (ej. 2024) | No | Año calendario. |
| `quarter` | `INTEGER` | 1 a 4 | No | Trimestre calendario. |
| `month` | `INTEGER` | 1 a 12 | No | Número de mes. |
| `month_name`| `TEXT` | Nombre del mes | No | Nombre del mes en inglés (ej. January). |
| `day` | `INTEGER` | 1 a 31 | No | Día del mes. |
| `day_of_week`| `TEXT` | Día de la semana | No | Nombre del día (ej. Monday). |
| `is_weekend` | `INTEGER` | 1 o 0 | No | Indicador booleano de fin de semana. |

---

## 3.2. Tabla: `dim_genre_bridge` (Capa Oro - Tabla Puente)

Tabla puente relacional para resolver la relación muchos a muchos entre videojuegos y géneros taxonómicos.

- **Clave Primaria Compuesta:** (`game_id`, `genre`)
- **Granularidad:** 1 fila por cada par videojuego-género.

| Columna | Tipo SQL | Formato | Nulos | Definición Conceptual |
| :--- | :--- | :--- | :--- | :--- |
| `game_id` | `INTEGER` | Entero | No | Clave foránea referenciando a `dim_game(game_id)`. |
| `genre` | `TEXT` | Texto | No | Nombre normalizado del género taxonómico. |

## 4. Tabla: `gold_engine_adoption_monthly` (Capa Oro)

Serie temporal agregada de adopción de tecnologías y motores de desarrollo en la cohorte independiente.

- **Clave Primaria Compuesta:** (`year_month`, `engine`, `is_indie`)
- **Granularidad:** Mensual por tecnología de desarrollo y segmento.

| Columna | Tipo Arrow / SQL | Unidad / Formato | Nulos | Definición Conceptual |
| :--- | :--- | :--- | :--- | :--- |
| `year_month` | `string` / `TEXT` | `YYYY-MM` | No | Mes calendario de publicación. |
| `is_indie` | `bool_` / `INTEGER` | Booleano (1/0) | No | Segmento analizado (`1` = Indie confirmado, `0` = No-indie). |
| `engine` | `string` / `TEXT` | Categoría | No | Nombre del motor (`Godot`, `Unity`, `Unreal`, `GameMaker`, `Custom/Other`). |
| `releases_count` | `int64` / `INTEGER` | Conteo entero | No | Cantidad de videojuegos lanzados en el mes con ese motor. |
| `monthly_share_pct` | `float64` / `REAL` | Porcentaje 0 a 100 | No | Porcentaje sobre el total de lanzamientos con motor detectado en ese mes. |
| `median_reviews` | `float64` / `REAL` | Conteo mediana | No | Mediana de reseñas capturadas por los títulos de esa tecnología. |
| `total_net_revenue_usd`| `float64` / `REAL` | Dólares USD | No | Facturación neta agregada de los títulos de esa tecnología en el mes. |
| `pipeline_version` | `string` / `TEXT` | SemVer (`vX.Y.Z`) | No | Versión del pipeline utilizada para consolidar el agregado. |

---

## 5. Tabla: `gold_pricing_by_genre` (Capa Oro)

Distribución econométrica de precios, percentiles y tasas de monetización por género.

- **Clave Primaria Compuesta:** (`genre`, `is_indie`)
- **Granularidad:** 1 fila por género y segmento editorial.

| Columna | Tipo Arrow / SQL | Unidad / Formato | Nulos | Definición Conceptual |
| :--- | :--- | :--- | :--- | :--- |
| `genre` | `string` / `TEXT` | Categoría | No | Género taxonómico analizado (ej. `Action`, `RPG`, `Strategy`, `Simulation`). |
| `is_indie` | `bool_` / `INTEGER` | Booleano (1/0) | No | Segmento (`1` = Indie, `0` = No-indie). |
| `games_count` | `int64` / `INTEGER` | Conteo entero | No | Cantidad total de títulos clasificados en este género. |
| `free_games_rate` | `float64` / `REAL` | Ratio 0.00 a 1.00 | No | Proporción de juegos Free-to-Play dentro del género. |
| `price_p25_usd` | `float64` / `REAL` | Dólares USD | No | Primer cuartil (percentil 25) de precios en el género. |
| `price_median_usd` | `float64` / `REAL` | Dólares USD | No | Mediana (percentil 50) de precios en el género. |
| `price_p75_usd` | `float64` / `REAL` | Dólares USD | No | Tercer cuartil (percentil 75) de precios en el género. |
| `median_net_revenue_usd`| `float64` / `REAL` | Dólares USD | No | Mediana de ingresos netos proyectados para los títulos del género. |
| `pipeline_version` | `string` / `TEXT` | SemVer (`vX.Y.Z`) | No | Versión del pipeline de transformación agregada. |

---

## 6. Tabla: `gold_market_saturation_monthly` (Capa Oro)

Serie temporal del índice de saturación de mercado y densidad de lanzamientos por género y ventana temporal.

- **Clave Primaria Compuesta:** (`year_month`, `genre`)
- **Granularidad:** Mensual por categoría.

| Columna | Tipo Arrow / SQL | Unidad / Formato | Nulos | Definición Conceptual |
| :--- | :--- | :--- | :--- | :--- |
| `year_month` | `string` / `TEXT` | `YYYY-MM` | No | Mes calendario de lanzamiento (`YYYY-MM`). |
| `genre` | `string` / `TEXT` | Categoría | No | Género taxonómico evaluado. |
| `indie_releases_count` | `int64` / `INTEGER` | Conteo entero | No | Cantidad de videojuegos independientes publicados en el mes. |
| `total_reviews_captured`| `int64` / `INTEGER` | Conteo entero | No | Suma acumulada de reseñas capturadas por los lanzamientos del mes. |
| `median_reviews_per_release` | `float64` / `REAL`| Mediana | No | Mediana de reseñas por título en esa cohorte mensual. |
| `saturation_index` | `float64` / `REAL` | Ratio analítico | No | Índice compuesto de presión competitiva y absorción de mercado. |
| `pipeline_version` | `string` / `TEXT` | SemVer (`vX.Y.Z`) | No | Versión del pipeline analítico. |
