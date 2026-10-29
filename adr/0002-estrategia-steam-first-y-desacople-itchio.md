# ADR-0002: Estrategia Steam-First y Desacople de Itch.io como Track Satelital

- **Estado:** Aceptado
- **Fecha:** 2026-10-16

## Contexto y Problema
El diseño conceptual inicial contemplaba extraer en paralelo los catálogos completos de Steam e Itch.io bajo un esquema unificado desde la Fase 2. Al auditar la documentación técnica de Itch.io, se comprobó que no existe una API REST pública para consultar el catálogo de terceros (los endpoints autenticados solo devuelven los juegos de la propia cuenta del desarrollador), dejando únicamente los feeds RSS públicos (`.xml`).

## Alternativas Consideradas
1. **Scraping HTML masivo del directorio de Itch.io:** Descartada por fragilidad ante cambios de DOM, riesgo de bloqueo por términos de servicio y ausencia total de métricas financieras o conteos de reseñas comparables a Steam.
2. **Mantener Itch.io en el camino crítico de las Fases 2 a 4:** Descartada porque retrasaría el modelado comercial (Boxleiter, precios, saturación) por una fuente que solo ofrece señales hacia adelante sin profundidad histórica.
3. **Enfoque Steam-First en el núcleo comercial (Fases 1–4) y desacople de Itch.io como extensión satelital:** Seleccionada.

## Decisión
Concentrar el 100% del camino crítico de las Fases 1 a 4 en la profundidad, escala y señales transaccionales de Steam (`appdetails`, `appreviews`, `IStoreService/GetAppList`). Itch.io queda formalmente desacoplado del núcleo analítico comercial y documentado como un módulo satelital opcional post-Fase 4, acotado exclusivamente a medir aparición relativa de motores en prototipos y game jams vía feeds RSS.

## Consecuencias y Costos Aceptados
- **Limitación de cobertura del ecosistema:** El observatorio no captura la etapa experimental pre-comercial (game jams gratuitas en navegador donde motores como Godot tienen alta presencia).
- **Beneficio determinante:** Homogeneidad estadística y validez comercial; cada título del Data Mart posee precios en USD verificables, fecha de lanzamiento exacta y volumen de reseñas auditable para estimar ingresos.

