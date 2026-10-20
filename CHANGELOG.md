## [sin publicar]

### agregado

- capa oro analitica agregada con tablas maestras de penetracion de motores y saturacion relativa (fase 4)
- pipeline programado en integracion continua con monitoreo de cuotas y alertas (fase 4)
- contratos estadisticos de calidad y deteccion de deriva de esquema en capa oro (fase 4)
- publicacion del dataset abierto en parquet y csv con metodologia, diccionario y limitaciones (fase 4)
- enriquecimiento de etiquetas comunitarias de tienda mediante dataset externo para clasificacion de motores nivel 2

## [0.3.3] - 2026-10-20

### corregido

- capitalizacion formal de excepciones de validacion en pipeline y transformacion oro
- saneamiento de exclusiones de herramientas en gitignore trasladadas a git info exclude
- normalizacion de comentarios en modulo de comparativa de benchmarks
- actualizacion de directorios canonicos en suite de pruebas de gobernanza

## [0.3.2] - 2026-10-20

### agregado

- reconciliador cero-huecos y unificador atomico de snapshots distribuidos en capa bronce (src/quality/reconciliacion.py)
- auditoria automatizada de completitud contra manifest_master y barrido residual tolerante a fallos
- contrato 10 bloqueante de reconciliacion y verificacion criptografica sha-256 de integridad pre-plata
- modulo de consolidacion y analisis comparativo de telemetria entre nodos pc local y google colab (src/analysis/comparativa_benchmark.py)

### corregido

- descarte en modo masivo para juegos con fechas de lanzamiento fuera de la ventana de catalogo 1997-2030 (src/transform/plata.py)

## [0.3.1] - 2026-10-19

### agregado

- sharding distribuido multi-nodo con particionamiento modular por appid (src/extract/pipeline.py)
- congelacion inmutable de manifiesto maestro para cohorte moderna (manifest_master.json)
- empaquetado atomico periodico a snapshot tar.gz para sincronizacion en la nube (src/extract/pipeline.py)
- colector de telemetria y benchmark por nodo con medicion de throughput, reintentos y 429 (src/extract/benchmark.py)
- captura limpia de sigint e interrupciones manuales con volcado persistente de checkpoints y telemetria

## [0.3.0] - 2026-10-18

### agregado

- extraccion masiva autenticada via istore service getapplist con paginacion perezosa (src/extract/client.py)
- ingesta particionada en capa bronce para cohortes y catalogo completo con checkpoints idempotentes tolerantes a fallos (src/extract/pipeline.py)
- barra visual de progreso en consola con calculo dinamico de eta y resiliencia de codificacion cp1252/ascii (src/extract/progress.py)
- modelo analitico calibrado de ventas y recaudacion neta boxleiter multi-era con retencion neta (src/analysis/boxleiter.py)
- enriquecimiento de capa oro fact_game_performance con ingresos netos e integracion star schema sqlite
- orquestador masivo cli con soporte para descubrimiento, limites y contencion de contratos (src/pipeline.py)
- lista de exclusion corporativa ampliada con valve y grandes multinacionales en taxonomia (config/taxonomy.yaml)
- saneamiento de datos en capa plata para titulos sin fecha de lanzamiento o paquetes sin precio unitario (src/transform/plata.py)

## [0.2.0] - 2026-10-17

### agregado

- motor de clasificacion determinista de motores de juego con jerarquia de evidencia niveles 1 a 4 (src/classify/engine.py)
- algoritmo multidimensional de autenticidad indie y exclusion de major publishers (src/classify/indie.py)
- clasificador de divulgacion formal de ia con prueba de contencion etica (src/classify/ai.py)
- configuracion taxonomica declarativa con esquemas pydantic y lista de exclusion corporativa (config/taxonomy.yaml)
- suite de calibracion estadistica con precision >= 0.95 en evidencia niveles 1-2 (tests/classify/test_calibracion.py)
- enriquecimiento de dim_game en capas plata y oro con atributos semanticos (engine, indie_score, is_indie, ai_disclosure_level)
- contrato bloqueante de calidad de datos para clasificacion semantica (src/quality/contratos.py)
- star schema de capa oro y data mart analitico relacional sqlite para power bi

## [0.1.0] - 2026-10-14

### agregado

- mvp vertical slice de steamworks con muestra de control congelada (100 titulos)
- cliente http con backoff exponencial y manejo tipado de cuotas (429)
- persistencia inmutable en capa bronce particionada por fecha y recurso
- gestor de checkpoints persistente con tolerancia a fallos y reanudacion idempotente
- transformacion determinista a capa plata con esquemas arrow y tablas parquet (dim_game, game_review_summary)
- suite de contratos bloqueantes de calidad de datos y contencion atomica
- orquestador integral e2e ejecutable con un solo comando (python -m src.pipeline)
  sha256-muestra-control: b1fe0c86c1adda42594b5a1ebbf9c889ed06329dec11487eb291ede0a615c8bd
