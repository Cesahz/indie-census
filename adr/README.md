# Registros de Decisiones de Arquitectura (ADR)

Este directorio documenta de forma inmutable las decisiones de arquitectura, diseño de datos y compromisos técnicos (*trade-offs*) adoptados en **Indie Census**.

Cada documento sigue una estructura de cuatro secciones obligatorias:
1. **Contexto y Problema:** La restricción real de ingeniería o de negocio que motivó la decisión.
2. **Alternativas Consideradas:** Las opciones técnicas evaluadas y las razones explícitas de su descarte.
3. **Decisión:** El diseño adoptado y sus invariantes en el código.
4. **Consecuencias y Costos Aceptados:** Los costos operativos, de almacenamiento o de rendimiento asumidos de forma consciente sin endulzarlos.

---

## Índice de Decisiones

| ID | Título | Estado | Fecha |
| :--- | :--- | :---: | :---: |
| [ADR-0001](0001-arquitectura-lakehouse-tres-capas.md) | Arquitectura Lakehouse Inmutable de Tres Capas (Bronce, Plata, Oro) | Aceptado | 2026-10-14 |
| [ADR-0002](0002-estrategia-steam-first-y-desacople-itchio.md) | Estrategia Steam-First y Desacople de Itch.io como Track Satelital | Aceptado | 2026-10-16 |
| [ADR-0003](0003-sharding-modular-y-reconciliacion-cero-huecos.md) | Sharding Modular Determinista y Reconciliación Cero-Huecos | Aceptado | 2026-10-20 |
| [ADR-0004](0004-algoritmo-autenticidad-indie-multivariable.md) | Algoritmo Determinista Multivariable para Autenticidad Indie (`indie_score`) | Aceptado | 2026-10-23 |
| [ADR-0005](0005-normalizacion-idioma-resenas-sin-sesgo.md) | Normalización Global del Idioma en Reseñas (`language="all"`) y Prioridad Web API | Aceptado | 2026-10-23 |
