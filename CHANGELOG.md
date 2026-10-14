## [sin publicar]

### agregado

- planeacion del slice de itch.io mediante feeds publicos (fase 2)
- declaracion formal de licencia mit en la raiz del repositorio (license)

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
