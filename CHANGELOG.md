## [sin publicar]

### agregado

- planeacion del slice de itch.io mediante feeds publicos (fase 2)

## [0.1.0] - 2026-10-14

### agregado

- mvp vertical slice de steamworks con muestra de control congelada (100 titulos)
- cliente http con backoff exponencial y manejo tipado de cuotas (429)
- persistencia inmutable en capa bronce particionada por fecha y recurso
- gestor de checkpoints persistente con tolerancia a fallos y reanudacion idempotente
- transformacion determinista a capa plata con esquemas arrow y tablas parquet (dim_game, game_review_summary)
- suite de contratos bloqueantes de calidad de datos y contencion atomica
- orquestador integral e2e ejecutable con un solo comando (python -m src.pipeline)
  sha256-muestra-control: 8892528f3c2f9c7c60a3459eed3ab80c7f45b093ccd04ce42acb9c74fc6f6c7f
