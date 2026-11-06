# Limitaciones y Advertencias Metodológicas

Siguiendo el principio de **transparencia radical** adoptado por instituciones de datos de referencia como **Our World in Data** (*"Never mask problems"*), este documento detalla las condiciones de frontera, sesgos conocidos e incertidumbres estadísticas inherentes al dataset de **Indie Census**.

Cualquier conclusión extraída de este observatorio debe interpretarse dentro del marco de estas cinco limitaciones estructurales:

---

## 1. Cobertura Temporal y Truncamiento de Muestra en Octubre de 2026

- **Ventana de Observación:** La cohorte comprende desde el 1 de enero de 2024 hasta mediados de octubre de 2026.
- **Truncamiento de Fin de Período:** La extracción de metadatos concluyó el **18 de octubre de 2026**.
- **Impacto en las Métricas:**
  - Los meses completos del período 2024–2026 registran entre **1.800 y 2.450 lanzamientos mensuales**.
  - El mes de **octubre de 2026 contiene únicamente 123 videojuegos registrados** en la Capa Oro.
  - **Advertencia:** Esta disminución abrupta **no representa una contracción repentina de la industria**, sino un corte artificial de la ventana de recolección a mitad de mes. Para análisis de series temporales continuas, se recomienda acotar la ventana de estudio hasta septiembre de 2026 inclusive o utilizar agregaciones acumuladas.

---

## 2. Cobertura en la Detección de Motores de Videojuegos (Nivel 1)

- **Restricción de la API de Steam:** La API pública de Valve (`appdetails`) no proporciona un campo estructurado nativo que indique la tecnología o motor empleado en el desarrollo.
- **Sensibilidad de Detección Textual:**
  - El clasificador Nivel 1 implementado en esta versión busca firmas textuales y créditos explícitos en las descripciones del juego.
  - La tasa de detección en texto plano es de aproximadamente el **1.1% del catálogo total**.
- **Interpretación de los Resultados:**
  - Las cuotas de adopción relativas (Godot vs. Unity vs. Unreal) en las series mensuales son **altamente precisas en su especificidad** (cero falsos positivos verificados), pero representan una submuestra sobre el total de lanzamientos.
  - No debe asumirse que el 98.9% restante utiliza motores propietarios, sino que la mayoría de los desarrolladores no declaran su tecnología en la descripción comercial del producto.

---

## 3. Incertidumbre Estadística en el Modelo de Ingresos (Boxleiter)

- **Naturaleza de la Estimación:** Las cifras de copias vendidas e ingresos económicos **no son datos contables auditados ni reportes fiscales directos de Valve**, sino proyecciones econométricas basadas en el volumen de reseñas públicas de usuarios.
- **Intervalo de Varianza:**
  - El multiplicador Boxleiter opera con un margen de incertidumbre estadística típico de $\pm 25\%$.
  - En videojuegos con **menos de 10 reseñas**, la varianza se incrementa sensiblemente debido al sesgo de compras iniciales por parte de círculos cercanos del desarrollador (*friends & family bias*).
- **Alcance de los Ingresos:**
  - El modelo estima los ingresos derivados de la **venta directa del juego base en Steam**.
  - No incluye ingresos por compras dentro de la aplicación (*microtransacciones / IAPs* en juegos gratuitos), contenido descargable (*DLCs*), ventas en plataformas de la competencia (Epic Games Store, GOG, itch.io, consolas) ni acuerdos de licencia de catálogo (ej. suscripciones a Xbox Game Pass).

---

## 4. Normalización de Precios y Descuentos Regionales

- **Precio de Catálogo vs. Precio Real Efectivo:**
  - Todos los cálculos monetarios se basan en el **precio oficial de venta de catálogo en dólares estadounidenses (USD)** registrado en el momento de la consulta.
- **Factores no Descontados en el Precio Unitario:**
  - **Rebajas y Descuentos Estacionales:** No se descuentan los eventos periódicos de ofertas (ej. Steam Summer Sale), los cuales suelen concentrar una porción relevante de las ventas con descuentos del 20% al 70%.
  - **Precios Regionales (PPP):** No se modela la canasta regional de precios por paridad de poder adquisitivo (ej. precios reducidos en Latinoamérica, Turquía o el Sudeste Asiático), lo cual produce que el precio medio efectivo percibido por copia (*Effective Average Selling Price*) sea inferior al precio de catálogo de Estados Unidos.

---

## 5. Juegos en Acceso Anticipado (*Early Access*)

- **Fecha de Registro:** Se registra la fecha de publicación original del producto en la tienda.
- **Dinámica de Reseñas:** Aquellos títulos que debutaron en Acceso Anticipado durante 2024 o 2025 y alcanzaron su lanzamiento 1.0 en 2026 acumulan reseñas a lo largo de todo su ciclo de vida, lo que puede reflejar un volumen superior frente a títulos con lanzamiento directo 1.0 de edad comercial similar.
