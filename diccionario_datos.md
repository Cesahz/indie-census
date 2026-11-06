# Diccionario de Datos del Observatorio Indie Census

Este documento contiene el catálogo formal y la especificación técnica de todas las columnas y variables publicadas en el dataset abierto de **Indie Census** (versión v0.4.0). Sigue el estándar de catalogación estructurada de **FiveThirtyEight** y **Our World in Data**.

---

## Índice de Tablas Maestras

| Nombre de Tabla | Capa | Granularidad | Formatos Disponibles | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| **`plata_steam_catalogo_limpio`** | Plata | 1 fila por videojuego (`appid`) | Parquet, CSV | Catálogo de metadatos, clasificación indie y características editoriales. |
| **`plata_steam_metricas_limpias`** | Plata | 1 fila por videojuego (`appid`) | Parquet, CSV | Precios en centavos/USD, reseñas estimadas e ingresos brutos/netos. |
| **`gold_engine_adoption_monthly`** | Oro | 1 fila por mes y motor (`anio_mes`, `motor`) | Parquet, CSV, SQLite | Adopción y cuota de mercado temporal de Godot, Unity, Unreal, etc. |
| **`gold_pricing_by_genre`** | Oro | 1 fila por género (`genero`) | Parquet, CSV, SQLite | Distribución y percentiles de precios (p25, p50, p75) por categoría. |
| **`gold_market_saturation_monthly`** | Oro | 1 fila por mes (`anio_mes`) | Parquet, CSV, SQLite | Volumen de lanzamientos mensuales, ratio de indies y tasa de saturación. |

---

## 1. Tabla: `plata_steam_catalogo_limpio`

Contiene el registro normalizado de títulos relevados, tras pasar por los filtros de limpieza, validación de cardinalidad y clasificación semántica.

- **Clave Primaria:** `appid`
- **Granularidad:** Nivel título / videojuego único.

| Columna | Tipo Arrow / SQL | Unidad / Formato | Nulos | Definición Conceptual | Fuente Primaria |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `appid` | `int64` / `INTEGER` | Identificador entero | No | Identificador único del juego en el ecosistema Steam. | Valve Web API |
| `nombre` | `string` / `TEXT` | Texto UTF-8 | No | Nombre oficial del videojuego en la tienda de Steam. | `appdetails` |
| `desarrolladores` | `list<string>` / `TEXT` | Lista / JSON array | No | Lista de nombres de los estudios o personas desarrolladoras. | `appdetails` |
| `editores` | `list<string>` / `TEXT` | Lista / JSON array | No | Lista de entidades que actúan como editores o publishers comerciales. | `appdetails` |
| `es_autoeditado` | `bool_` / `INTEGER` | Booleano (1/0) | No | Indica si el desarrollador y el editor coinciden (self-published). | Inferencia Plata |
| `fecha_lanzamiento` | `date32` / `TEXT` | `YYYY-MM-DD` | Sí | Fecha oficial de lanzamiento al mercado según la ficha de tienda. | `appdetails` |
| `generos` | `list<string>` / `TEXT` | Lista / JSON array | No | Categorías taxonómicas asignadas por la tienda de Steam. | `appdetails` |
| `etiquetas_comunitarias` | `list<string>` / `TEXT` | Lista / JSON array | No | Tags asignados por la comunidad de usuarios de Steam. | Steam Tags |
| `motor_detectado` | `string` / `TEXT` | Categoría | Sí | Motor gráfico/lógico identificado (ej. Godot, Unity, Unreal, Custom). | Clasificador Nivel 1/2 |
| `es_indie` | `bool_` / `INTEGER` | Booleano (1/0) | No | Clasificación final del observatorio: `True` si cumple el umbral indie. | Clasificador Semántico |
| `puntaje_indie` | `float64` / `REAL` | Escala 0.00 a 1.00 | No | Puntuación compuesta de independencia según evidencia semántica. | Algoritmo Indie Score |

---

## 2. Tabla: `plata_steam_metricas_limpias`

Contiene los cálculos económicos y las métricas de recepción de los usuarios por título.

- **Clave Primaria:** `appid`
- **Granularidad:** Nivel videojuego único.

| Columna | Tipo Arrow / SQL | Unidad / Formato | Nulos | Definición Conceptual | Fuente Primaria |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `appid` | `int64` / `INTEGER` | Identificador entero | No | Identificador del juego (clave foránea a catálogo). | Valve Web API |
| `precio_centavos_usd` | `int64` / `INTEGER` | Centavos de USD | No | Precio base de catálogo en centavos (ej. 1999 = \$19.99 USD). | `appdetails` |
| `precio_usd` | `float64` / `REAL` | USD normalizado | No | Precio base en dólares estadounidenses decimales. | Inferencia Plata |
| `es_gratuito` | `bool_` / `INTEGER` | Booleano (1/0) | No | Indica si el juego es de acceso gratuito (Free-to-Play). | `appdetails` |
| `resenas_positivas` | `int64` / `INTEGER` | Conteo entero | No | Cantidad acumulada de reseñas positivas registradas. | Steam Reviews API |
| `resenas_negativas` | `int64` / `INTEGER` | Conteo entero | No | Cantidad acumulada de reseñas negativas registradas. | Steam Reviews API |
| `total_resenas` | `int64` / `INTEGER` | Conteo entero | No | Suma de reseñas positivas y negativas ($R = \text{pos} + \text{neg}$). | Steam Reviews API |
| `ratio_positivas` | `float64` / `REAL` | Ratio 0.00 a 1.00 | Sí | Porcentaje de satisfacción de la comunidad ($\text{pos} / \text{total}$). | Inferencia Plata |
| `copias_estimadas` | `int64` / `INTEGER` | Unidades estimadas | No | Proyección de copias vendidas mediante el método Boxleiter calibrado. | Modelo Boxleiter |
| `ingresos_brutos_usd` | `float64` / `REAL` | Dólares USD | No | Facturación bruta estimada ($\text{copias} \times \text{precio}$). | Modelo Boxleiter |
| `ingresos_netos_usd` | `float64` / `REAL` | Dólares USD | No | Rendimiento neto desarrollador deduciendo tasas (58% del bruto). | Modelo Boxleiter |

---

## 3. Tabla: `gold_engine_adoption_monthly`

Agregado mensual de penetración de motores de juego en la industria independiente.

- **Clave Primaria Compuesta:** (`anio_mes`, `motor`)
- **Granularidad:** Mensual por tecnología de desarrollo.

| Columna | Tipo Arrow / SQL | Unidad / Formato | Nulos | Definición Conceptual |
| :--- | :--- | :--- | :--- | :--- |
| `anio_mes` | `string` / `TEXT` | `YYYY-MM` | No | Mes calendario de la cohorte analizada. |
| `motor` | `string` / `TEXT` | Categoría | No | Nombre del motor (`Godot`, `Unity`, `Unreal`, `GameMaker`, `Custom/Other`). |
| `total_lanzamientos` | `int64` / `INTEGER` | Conteo entero | No | Cantidad total de videojuegos lanzados en el mes con ese motor. |
| `cuota_mercado_pct` | `float64` / `REAL` | Porcentaje 0 a 100 | No | Porcentaje sobre el total de lanzamientos con motor detectado en ese mes. |
| `fecha_corte` | `date32` / `TEXT` | `YYYY-MM-DD` | No | Marca temporal de ejecución y congelamiento del Data Mart. |

---

## 4. Tabla: `gold_pricing_by_genre`

Distribución de precios y bandas estadísticas por género de videojuego.

- **Clave Primaria:** `genero`
- **Granularidad:** 1 fila por género taxonómico.

| Columna | Tipo Arrow / SQL | Unidad / Formato | Nulos | Definición Conceptual |
| :--- | :--- | :--- | :--- | :--- |
| `genero` | `string` / `TEXT` | Categoría | No | Nombre del género analizado (ej. `Action`, `RPG`, `Strategy`, `Simulation`). |
| `total_juegos` | `int64` / `INTEGER` | Conteo entero | No | Cantidad de videojuegos de la muestra clasificados en este género. |
| `precio_promedio_usd` | `float64` / `REAL` | Dólares USD | No | Media aritmética de los precios de venta en dólares. |
| `precio_p25_usd` | `float64` / `REAL` | Dólares USD | No | Primer cuartil (percentil 25) de precios en el género. |
| `precio_p50_usd` | `float64` / `REAL` | Dólares USD | No | Mediana (percentil 50) de precios en el género. |
| `precio_p75_usd` | `float64` / `REAL` | Dólares USD | No | Tercer cuartil (percentil 75) de precios en el género. |
| `fecha_corte` | `date32` / `TEXT` | `YYYY-MM-DD` | No | Marca temporal de ejecución y congelamiento del Data Mart. |

---

## 5. Tabla: `gold_market_saturation_monthly`

Serie temporal de saturación del catálogo de Steam y proporción de oferta independiente.

- **Clave Primaria:** `anio_mes`
- **Granularidad:** Mensual.

| Columna | Tipo Arrow / SQL | Unidad / Formato | Nulos | Definición Conceptual |
| :--- | :--- | :--- | :--- | :--- |
| `anio_mes` | `string` / `TEXT` | `YYYY-MM` | No | Mes calendario de lanzamiento (`YYYY-MM`). |
| `total_lanzamientos` | `int64` / `INTEGER` | Conteo entero | No | Cantidad absoluta de videojuegos publicados en Steam ese mes. |
| `total_lanzamientos_indie`| `int64` / `INTEGER` | Conteo entero | No | Cantidad de videojuegos confirmados como independientes en ese mes. |
| `porcentaje_indie` | `float64` / `REAL` | Porcentaje 0 a 100 | No | Proporción de títulos indie sobre el total de publicaciones mensuales. |
| `fecha_corte` | `date32` / `TEXT` | `YYYY-MM-DD` | No | Marca temporal de ejecución y congelamiento del Data Mart. |
