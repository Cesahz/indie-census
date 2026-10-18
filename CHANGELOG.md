## [sin publicar]

### agregado

- motor de modelado predictivo y auditoria de viabilidad comercial de videojuegos (fase 4)
- calculo algoritmico de densidad competitiva en ventanas temporales de lanzamiento (fase 4)
- deteccion de nichos comerciales desatendidos vs etiquetas de tienda saturadas (fase 4)
- generador de reportes ejecutivos headless en formatos pdf y json desacoplado de interfaces web (fase 4)

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
