## [sin publicar]

### agregado

- expansion masiva de catalogo de steam con getapplist y control de supervivencia (fase 3)
- ingesta particionada en capa bronce para cohortes 2024-2026 con checkpoints tolerantes a fallos
- agregacion de resenas y derivacion de metricas comerciales boxleiter a escala

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
