# Benchmark Comparativo de Transformacion (Bronce -> Plata)

- **Fecha de Medicion:** 2026-10-31T01:22:00.844776+00:00
- **Version del Pipeline:** `0.3.5`
- **Tamano de Muestra:** 1000 juegos

## Perfil de Hardware Detectado
- **Hilos Logicos:** 12
- **Categoria:** `multiproceso_alto_rendimiento`
- **Workers Asignados:** 10
- **Tamano de Lote (Batch):** 5000

## Comparativa de Rendimiento

| Metrica | Antes (Ansioso Mono-hilo) | Despues (Streaming Adaptativo) | Factor de Mejora |
| :--- | :---: | :---: | :---: |
| Duracion de Pared | 2.27 s | 1.17 s | **1.93x** mas rapido |
| Throughput | 441.3 juegos/s | 853.5 juegos/s | +93.4% |
| Pico de Memoria RAM | 25.56 MB | 3.02 MB | **88.2%** ahorro |
| Equivalencia Matematica | Referencia | Identica (`table.equals()`) | Verificado |
