# Metodología del Observatorio Indie Census

## 1. Misión y Alcance del Observatorio

**Indie Census** es un observatorio analítico de código abierto diseñado para medir, clasificar y proyectar la dinámica económica del desarrollo independiente de videojuegos en PC (Steam). Su propósito es sustituir las narrativas anecdóticas de saturación de mercado por evidencia cuantitativa auditable, determinista y matemáticamente reproducible.

El observatorio opera sobre una cohorte temporal comprendida entre **enero de 2024 y octubre de 2026**, procesando más de 63.700 títulos y consolidando un censo de más de 57.000 videojuegos independientes legítimos.

---

## 2. Marco Conceptual: La Demarcación "Indie"

Uno de los principales desafíos metodológicos en la economía digital de los videojuegos radica en la pérdida de significado del término "indie" en las tiendas digitales. En Steam, cualquier editor o desarrollador puede asignarse voluntariamente la etiqueta comercial *"Indie"*, generando falsos positivos de gran escala (ej. megaproyectos respaldados por conglomerados corporativos cotizados en bolsa como *Dave the Diver* / Mintrocket / Nexon) y falsos negativos (proyectos unipersonales que omiten la etiqueta por razones de optimización algorítmica).

### 2.1 Los Tres Niveles de Evidencia Semántica
Para resolver esta ambigüedad sin depender de un único tag voluntario, Indie Census implementa un clasificador semántico basado en tres niveles de evidencia progresiva:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   NIVELES DE EVIDENCIA SEMÁNTICA                      │
├────────────────────────────────────────────────────────────────────────┤
│ NIVEL 1: Evidencia Textual Directa (Hard Metadata)                     │
│ ├── Búsqueda de patrones en descripciones y créditos técnicos.         │
│ └── Detección determinista de motores en texto plano.                  │
├────────────────────────────────────────────────────────────────────────┤
│ NIVEL 2: Taxonomía y Etiquetas Comunitarias (Consensus Signals)        │
│ ├── Análisis de frecuencia y dominancia de tags comunitarios.          │
│ └── Filtrado de géneros saturados vs. nichos especializados.           │
├────────────────────────────────────────────────────────────────────────┤
│ NIVEL 3: Contexto Editorial y Estructura Corporativa (Proxy Signals)   │
│ ├── Desacoplamiento de auto-publicación (Self-Published vs. Publisher).│
│ └── Detección de publishers boutique independientes (Devolver, etc.)   │
│     frente a corporaciones multinacionales (AAA / Conglomerados).      │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.2 El Puntaje Indie (*Indie Score*)
Cada videojuego es evaluado a través de una función de puntuación determinista $S \in [0.0, 1.0]$ estructurada en cinco dimensiones ponderadas (`config/taxonomy.yaml`):
1. **Presencia de etiqueta indie:** peso `0.25`.
2. **Autopublicación o publicador boutique (catálogo $\le 5$ títulos):** peso `0.25`.
3. **Precio base accesible ($\le \$35.00$ USD):** peso `0.15` (proxy de presupuesto modesto).
4. **Diversificación lingüística moderada ($\le 8$ idiomas):** peso `0.10` (proxy de esfuerzo de localización independiente).
5. **Ausencia de conglomerado multinacional / Major Publisher:** peso `0.25`.

La condición booleana de inclusión como independiente se define formalmente como:

$$\text{is\_indie} = 
\begin{cases} 
\text{True} & \text{si } S \ge 0.60 \text{ y el publicador no figura en la lista corporativa excluida} \\
\text{False} & \text{en cualquier otro caso}
\end{cases}$$

### 2.3 Ponderación del Precio como Proxy Financiero
De acuerdo con el registro arquitectónico ADR-0004, el precio interviene exclusivamente con un peso moderado del 15% como proxy de escala económica:
- Videojuegos con precio base $\le \$35.00$ USD suman el crédito de accesibilidad económica.
- Títulos con precios propios de gran presupuesto ($\ge \$50.00 - \$70.00$ USD) no reciben dicho puntaje, penalizando la probabilidad de que megaproyectos corporativos sean catalogados como independientes.

---

### 2.4 Monitoreo Ético de Inteligencia Artificial Generativa (Ventana 2020–2026)
Uno de los propósitos fundacionales de Indie Census es estudiar el impacto de la Inteligencia Artificial generativa en el ecosistema de videojuegos independientes, evitando acusaciones infundadas o estigmatización contra creadores:

- **El Experimento Natural (2020–2023 frente a 2024–2026):** En enero de 2024, Valve introdujo su política obligatoria de divulgación de IA (*AI Generated Content Disclosure*). Para cuantificar el verdadero crecimiento de la IA, el observatorio requiere la ventana histórica **2020–2023** como línea base previa a la política, permitiendo medir de forma rigurosa la aceleración en la publicación de títulos asistidos o generados por IA a partir de 2024.
- **Principio de Contención Ética (Cero Falsos Positivos):** En foros y comunidades de desarrolladores existe un desgaste evidente por acusaciones injustificadas hacia artistas y programadores que crean sus obras artesanalmente. Por ello, el clasificador proscribe categóricamente cualquier inferencia visual, estilística o probabilística no comprobable.
- **Jerarquía Estricta de Cuatro Niveles (`ai_disclosure_level`):**
  1. `declared`: Declaración formal del desarrollador en los descriptores de contenido oficiales de Steam (ej. encuestas de Steamworks).
  2. `tagged`: Presencia de etiquetas comunitarias de tienda (`ai`, `generative ai`, `artificial intelligence`).
  3. `self_reported`: Declaración textual explícita en notas de parche, descripción o créditos por parte del autor.
  4. `unknown`: Ausencia comprobable de declaraciones. Nunca se presupone uso sin evidencia primaria.

---

## 3. Modelo Econométrico de Ingresos (Boxleiter Adaptado)

Steam no publica cifras oficiales de ventas ni ingresos. Para estimar la facturación de cada título, Indie Census implementa una versión calibrada del **método Boxleiter**, ampliamente reconocido en la analítica de la industria del videojuego.

### 3.1 Proyección de Unidades Vendidas (Copias)
El número de copias vendidas $N_{\text{copias}}$ se modela a partir del volumen total de reseñas de usuarios $R$ mediante un multiplicador de conversión $M$:

$$N_{\text{copias}} = R \times M(R, \text{año})$$

Donde el multiplicador dinámico $M$ se calibra de acuerdo con la antigüedad del título y el rango de volumen:
- **Cohorte Clásica ($< 2020$):** $M = 45$ (menor propensión histórica de los jugadores a reseñar compras).
- **Cohorte de Transición ($2020 - 2023$):** $M = 35$ (expansión del ecosistema digital y adopción del hábito de reseña).
- **Cohorte Moderna ($2024+$):** $M = 30$ (ratio contemporánea de alta actividad de reseñas en Steam).
- **Banda de incertidumbre estadística:** Se computan estimaciones inferior ($M_{\min} = 20$), mediana calibrada ($M_{\text{mid}}$) y superior ($M_{\max} = 55$).

### 3.2 Ingresos Brutos (*Gross Revenue*)
Representa el volumen total facturado al precio base de catálogo $P_{\text{USD}}$:

$$\text{Revenue}_{\text{bruto}} = N_{\text{copias}} \times P_{\text{USD}}$$

*(Para videojuegos gratuitos / Free-to-Play, el ingreso directo por venta se fija en \$0.00 USD, excluyendo microtransacciones no auditables de la estimación base).*

### 3.3 Ingresos Netos (*Net Developer Revenue*)
Para calcular el capital real que percibe el equipo desarrollador tras la cadena de valor digital, se deducen tres conceptos estándar del mercado:

$$\text{Revenue}_{\text{neto}} = \text{Revenue}_{\text{bruto}} \times (1 - \tau_{\text{plataforma}}) \times (1 - \tau_{\text{impuestos}}) \times (1 - \tau_{\text{devoluciones}})$$

Parámetros estándar del observatorio:
1. **Comisión de Plataforma ($\tau_{\text{plataforma}} = 0.30$):** El 30% estándar cobrado por Valve Corporation.
2. **Impuestos Ponderados en Origen ($\tau_{\text{impuestos}} = 0.10$):** Retención media global calculada por tratados internacionales de doble imposición y retenciones fiscales (WHT).
3. **Tasa Media de Reembolsos ($\tau_{\text{devoluciones}} = 0.08$):** Promedio del 8% de devoluciones dentro de la ventana de protección de 2 horas de juego de Steam.

**Factor de Rendimiento Neto:** El desarrollador percibe aproximadamente el **58.0%** del ingreso bruto modelado ($0.70 \times 0.90 \times 0.92 = 0.5796$).

---

## 4. Arquitectura de Datos y Linaje (Lakehouse)

El procesamiento de datos sigue un flujo unidireccional y hermético de tres capas:

```
[Valve Web API / Steam Store]
             │
             ▼
┌────────────────────────────────────────┐
│  CAPA BRONCE (Raw Inmutable)           │
│  - JSONs crudos con hash SHA-256       │
│  - Preservación íntegra de respuestas  │
└──────────────────┬─────────────────────┘
                   │
                   ▼ (Limpieza, parseo de tipos y 10 contratos bloqueantes)
┌────────────────────────────────────────┐
│  CAPA PLATA (Tablas Tipadas Parquet)   │
│  - Esquema estricto Apache Arrow       │
│  - Precios en centavos enteros (int64) │
│  - Metadatos y métricas desagregadas   │
└──────────────────┬─────────────────────┘
                   │
                   ▼ (Agregaciones temporales y contratos estadísticos 3σ)
┌────────────────────────────────────────┐
│  CAPA ORO (Data Mart Analítico)        │
│  - SQLite (indie_census_mart.db)       │
│  - Tablas maestras en Apache Parquet   │
│  - Series de adopción, pricing y sat.  │
└──────────────────┬─────────────────────┘
                   │
                   ▼ (Exportación dual y verificación criptográfica)
┌────────────────────────────────────────┐
│  DATASET PÚBLICO DISTRIBUIBLE          │
│  - data/publico/ (Parquet + CSV)       │
│  - Manifiesto checksums.sha256         │
└────────────────────────────────────────┘
```

---


---

## 5. Protocolo de Minería Continua y Actualización Incremental

Indie Census no es un dataset estático cerrado en el tiempo, sino una plataforma de observatorio vivo con capacidades de minería periódica e ingesta incremental. El sistema está diseñado para incorporar nuevos lanzamientos y actualizar métricas de recepción comercial sin necesidad de reprocesar el catálogo histórico desde cero.

```
┌────────────────────────────────────────────────────────────────────────┐
│               FLUJO DE MINERÍA INCREMENTAL DE STEAM                    │
├────────────────────────────────────────────────────────────────────────┤
│ 1. Descubrimiento: IStoreService/GetAppList/v1                         │
│    └── Filtrado por min_appid (identificadores > cohorte actual)      │
│ 2. Deduplicación por Checkpoint: data/checkpoint.json                  │
│    └── Omitir los 63.770 appids ya completados e inmutables en Bronce  │
│ 3. Extracción Resiliente: Web API con Backoff Adaptativo + Jitter      │
│    └── Respeto de cuotas de Valve y gestión automática de códigos 429  │
│ 4. Ingesta a Bronce: Particionado por fecha=YYYY-MM-DD y hash SHA-256  │
│ 5. Procesamiento Streaming: Plata y Oro agregadas en < 2 minutos       │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.1 Mecanismo de Checkpointing e Idempotencia
El proceso de minería está custodiado por el gestor de checkpoints (`data/checkpoint.json`). Este archivo registra en tiempo real el conjunto de identificadores completados para cada recurso (`appdetails` y `appreviews_resumen`). 

Si una sesión de minería se interrumpe por conectividad, suspensión de la máquina o mantenimiento de los servidores de Valve, el pipeline reanuda en el juego exacto donde se detuvo sin realizar una sola llamada HTTP redundante a la tienda.

### 5.2 Control de Tasa (Rate Limiting) y Resiliencia HTTP
Valve impone restricciones dinámicas de cuota (códigos de respuesta `HTTP 429 Too Many Requests`). El cliente de extracción de Indie Census implementa:
- **Lectura activa del encabezado `Retry-After`:** Cuando Steam solicita una pausa, el cliente duerme el tiempo exacto exigido por la plataforma.
- **Backoff Exponencial con Jitter Aleatorio:** Si el encabezado no está presente, el cliente aplica una penalización exponencial con dispersión uniforme para evitar resonancias y ráfagas concurrentes.
- **Historial de Resiliencia:** Este algoritmo ha superado pruebas en entornos de estrés procesando más de 34.000 respuestas 429 sin una sola pérdida de datos ni bloqueo de IP.

### 5.3 Sharding Modular Distribuido
Para campañas de minería masiva donde se analizan decenas de miles de juegos nuevos, el extractor admite particionamiento modular determinista:

$$	ext{worker\_asignado} = 	ext{appid} \pmod{	ext{total\_workers}}$$

Esto permite distribuir la carga entre varias máquinas o instancias cloud (ej. PC Local y Google Colab Pro) coordinadas por un manifiesto maestro común (`manifest_master.json`), con sincronización por bloques empaquetados en `snapshot.tar.gz`.

### 5.4 Comando de Minería
Para ejecutar una campaña de minería incremental en el entorno local:

```bash
#minar nuevos juegos descubiertos en steam y actualizar la capa bronce
python -m src.pipeline --modo masivo --descubrir --fecha 2026-11-06

#reprocesar la transformacion de plata y oro sobre el nuevo bronce acumulado
python -m src.pipeline --omitir-extraccion --generar-oro --modo masivo
```

## 6. Quickstart de Consulta Inmediata (DuckDB / Polars)

El dataset abierto puede consultarse en memoria en milisegundos sin necesidad de instalar bases de datos cliente-servidor:

### Consulta con DuckDB (Python / SQL)
```python
import duckdb

# Conectar en memoria y consultar la dimensión de juegos limpios
con = duckdb.connect()
df_resumen = con.execute("""
    SELECT 
        engine,
        is_indie,
        COUNT(*) AS total_juegos
    FROM 'data/plata/steam/dim_game.parquet'
    GROUP BY engine, is_indie
    ORDER BY total_juegos DESC
    LIMIT 10;
""").df()

print(df_resumen)
```

### Consulta con Polars
```python
import polars as pl

# Leer serie temporal de saturación mensual en Capa Oro
df_saturacion = pl.read_parquet(
    "data/oro/gold_market_saturation_monthly.parquet"
)

# Filtrar meses con mayor volumen de indies lanzados
top_meses = (
    df_saturacion
    .filter(pl.col("indie_releases_count") > 100)
    .sort("indie_releases_count", descending=True)
)
print(top_meses.head(5))
```

---

## 7. Citación y Licencias

### Cómo Citar este Observatorio
Si utilizas los datos o la metodología de Indie Census en investigaciones académicas, reportajes periodísticos o publicaciones del sector, por favor cita el proyecto como:

```bibtex
@misc{indie_census_2026,
  author = {Indie Census Observatory Contributors},
  title = {Indie Census: Observatorio Económico y Tecnológico del Videojuego Independiente en PC},
  year = {2026},
  publisher = {GitHub},
  howpublished = {\url{https://github.com/indie-census/indie-census}},
  note = {Capa Oro Analítica, Versión v0.4.0}
}
```

### Licencias
- **Código Fuente y Scripts:** Licencia [MIT](LICENSE).
- **Datasets y Documentación:** [Creative Commons Attribution 4.0 International (CC-BY 4.0)](https://creativecommons.org/licenses/by/4.0/).

