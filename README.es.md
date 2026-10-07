# Indie Census

[Read in English](README.md) · [Leer en español](README.es.md)

Observatorio abierto de datos del ecosistema de desarrollo de videojuegos independiente.

---

> **Estado del proyecto:** En desarrollo activo. Este es un proyecto personal que se construye de forma pausada y metódica, priorizando la solidez de la ingeniería de software y el rigor analítico. Todo módulo se diseña bajo desarrollo guiado por pruebas (TDD), con suites de pruebas herméticas (sin llamadas a la red ni aleatoriedad no controlada), tipado estricto y contratos de datos inmutables antes de cada implementación.

---

## Intención y Visión

Este observatorio nace como una iniciativa personal con el propósito de aportar valor y datos abiertos a la comunidad de desarrollo de videojuegos, analistas e investigadores.

El debate sobre la industria del videojuego independiente —motores utilizados, saturación de tiendas, precios y la irrupción de nuevas tecnologías— suele estar dominado por impresiones anecdóticas, discusiones polarizadas en foros o análisis comerciales que no publican sus datos crudos ni su metodología.

**Indie Census** busca aportar a la comunidad una **fuente pública, citable y metodológicamente auditable** que transforme la conversación empírica en evidencia cuantitativa abierta.

El proyecto no busca validar una postura particular ni se restringe a una herramienta específica, sino medir con neutralidad las transformaciones reales del sector:

1. **Adopción y transición de motores técnicos:** Cómo evolucionan y se distribuyen las tecnologías de desarrollo (motores de código abierto, motores comerciales y herramientas propias) en el catálogo independiente.
2. **Dinámica de precios y sostenibilidad comercial:** Rangos de precios, estrategias de lanzamiento y supervivencia económica de producciones de pequeña escala.
3. **Divulgación de Inteligencia Artificial generativa:** Detección y análisis cuantitativo de las declaraciones de uso de IA en assets y código según las políticas públicas de las plataformas de distribución.
4. **Metodología y datos abiertos:** Publicación no solo de conclusiones o gráficos, sino de los datasets limpios y el código del pipeline para que cualquier persona en la comunidad pueda reproducir o auditar los resultados.

---

## Definición del MVP (Producto Mínimo Viable)

El objetivo del MVP (`v0.1.0`) es establecer las bases de ingeniería de datos y verificar de punta a punta la viabilidad técnica y metodológica con costo cero de infraestructura:

- **Ingesta resiliente y reproducible:** Cliente HTTP con control estricto de cuotas, backoff exponencial con jitter ante respuestas 429 y checkpoints atómicos para reanudación segura ante interrupciones.
- **Muestra de control calibrada:** Selección inicial de 100 títulos representativos en Steam (con balance de motores y categorías) congelada mediante hash SHA-256 para auditar la precisión de los clasificadores.
- **Arquitectura de capas de datos:**
  - **Bronce:** Almacenamiento inmutable del payload crudo particionado por fecha y origen, garantizado con verificación de integridad criptográfica.
  - **Plata:** Normalización, tipado estricto con Pydantic/Arrow y contratos de calidad de datos que bloquean anomalías.
  - **Oro:** Datasets agregados listos para análisis y cálculo de métricas.
- **Entrega reproducible:** Un primer dataset preliminar limpio y verificable en formatos abiertos (Parquet/CSV), respaldado por una suite de pruebas automatizada en integración continua.

---

## Principios de Ingeniería

- **TDD Invariante:** Ningún módulo de extracción, transformación o calidad se implementa sin su correspondiente suite de pruebas previa en verde.
- **Hermeticidad total:** Pruebas unitarias y de integración que no tocan la red real; inyección de dependencias para reloj, pausas y generadores aleatorios.
- **Inmutabilidad y trazabilidad:** Los datos crudos jamás se sobreescriben; cualquier recomputación parte de la fuente original histórica.
- **Diseño sin costo:** Ejecución automatizada aprovechando infraestructura ligera y reproducible sin servidores dedicados de pago.
