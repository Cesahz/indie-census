# ADR-0004: Algoritmo Determinista Multivariable para Autenticidad Indie (`indie_score`)

- **Estado:** Aceptado
- **Fecha:** 2026-10-23

## Contexto y Problema
En Steam, la etiqueta `"Indie"` es auto-asignada por quien publica el juego. Confiar ciegamente en esa etiqueta introduce falsos positivos severos (subsidiarias de conglomerados AAA, distribuidores masivos con cientos de títulos en catálogo o *asset flips*) y falsos negativos (estudios independientes legítimos que omitieron el tag `"Indie"` en sus géneros principales).

## Alternativas Consideradas
1. **Filtro binario por género `"Indie"` de Steam:** Descartada por alta contaminación de publishers corporativos y pérdida de títulos independientes reales.
2. **Clasificación mediante modelos de lenguaje (LLM) por juego:** Descartada por falta de determinismo estricto, costo computacional sobre 63.000 títulos y opacidad al auditar por qué un juego fue clasificado de cierta manera.
3. **Scoring determinista multivariable auditable (`indie_score` en `[0.0, 1.0]` con umbral `>= 0.60`):** Seleccionada.

## Decisión
Implementar en `src/classify/indie.py` una función pura y determinista que calcula `indie_score` combinando:
- Presencia de etiquetas/géneros independientes y auto-publicación (`developers == publishers`).
- Regla de veto duro (`indie_score = 0.0`) si el desarrollador o publisher pertenece a la lista curada de conglomerados AAA/AA en `config/taxonomy.yaml` o si el tamaño del catálogo del publisher en la cohorte supera el umbral de distribuidor masivo (>25 títulos).
- Penalizaciones graduales por precio de lanzamiento superior a umbrales indie ($40/$60 USD) e hiper-localización industrial (>15 idiomas).

## Consecuencias y Costos Aceptados
- **Mantenimiento de `config/taxonomy.yaml`:** La lista de conglomerados y filiales requiere curaduría periódica cuando aparecen nuevos sellos editoriales grandes.
- **Beneficio determinante:** Clasificación 100% reproducible, auditable columna por columna y libre de alucinaciones, separando con precisión los 57.011 títulos independientes reales dentro de los 63.770 juegos del catálogo.

