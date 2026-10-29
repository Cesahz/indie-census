# ADR-0005: Normalización Global del Idioma en Reseñas (`language="all"`) y Prioridad Web API

- **Estado:** Aceptado
- **Fecha:** 2026-10-23

## Contexto y Problema
En la primera extracción masiva de la cohorte 2026-10-18, las consultas al endpoint de resumen de reseñas heredaron el parámetro por defecto `language="english"` del cliente HTTP. Esto provocó que los conteos `total_reviews`, `total_positive` y `total_negative` reflejaran únicamente reseñas escritas por usuarios con Steam en inglés, subestimando hasta en 14x las ventas e ingresos Boxleiter de juegos con fuerte tracción en Asia, Europa o Latinoamérica (ej. *Nine Sols*: 1.644 reseñas en inglés vs. >20.700 globales).

## Alternativas Consideradas
1. **Aplicar un multiplicador corrector estadístico sobre las reseñas en inglés:** Descartada porque la proporción de jugadores no angloparlantes varía drásticamente según el género, el estudio y los idiomas soportados por cada título.
2. **Sobrescribir en el lugar los archivos JSON de la partición `2026-10-18`:** Descartada por violar la regla de inmutabilidad de la capa Bronce (ADR-0001).
3. **Fijar `language="all"` obligatorio, priorizar `IUserReviewsService/GetAppReviews/v1/` con `STEAM_API_KEY` y emitir una nueva partición Bronce solo para los juegos válidos de Plata:** Seleccionada.

## Decisión
- Fijar de forma innegociable `language="all"` en `SteamClient.get_app_reviews_summary` y en `src/extract/pipeline.py`.
- Priorizar el endpoint autenticado de la Web API oficial (`IUserReviewsService/GetAppReviews/v1/`) cuando exista `STEAM_API_KEY`, manteniendo el endpoint público de tienda (`store.steampowered.com/appreviews/<id>?json=1&language=all&purchase_type=all&num_per_page=0`) como respaldo.
- Ejecutar una re-ingesta selectiva únicamente del recurso `appreviews_resumen` sobre los 63.770 `game_id` válidos en Plata (reutilizando los `appdetails` intactos de `2026-10-18`), promoviendo la partición más reciente al reconstruir Plata y Oro.

## Consecuencias y Costos Aceptados
- **Tiempo adicional de re-extracción:** Requiere realizar 63.770 peticiones ligeras adicionales antes de congelar el dataset público de la Fase 4.
- **Beneficio determinante:** Elimina por completo el sesgo geográfico e idiomático en las métricas comerciales Boxleiter sin re-descargar los 112.185 `appdetails` existentes.

