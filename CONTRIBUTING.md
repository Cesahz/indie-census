# Guía de Contribución — Indie Census

Gracias por tu interés en contribuir a este observatorio de código abierto. Este documento detalla las directrices técnicas, convenciones de código y el flujo de trabajo para enviar mejoras, módulos analíticos o correcciones.

---

## 1. Principios de Diseño del Proyecto

1. **Arquitectura Data Lakehouse Desacoplada:** El pipeline fluye estrictamente a través de Bronce (ingesta cruda inmutable con validación criptográfica SHA-256) -> Plata (normalización técnica en Apache Arrow / Parquet con contratos bloqueantes) -> Oro (modelo dimensional Star Schema y Data Mart analítico en SQLite/DuckDB).
2. **Cero Scraping HTML:** Ingesta exclusiva vía endpoints JSON de APIs oficiales de Steamworks y Storefront. Prohibido el scraping de DOM o emulación de navegador.
3. **Hermeticidad Absoluta en Pruebas:** La suite de pruebas debe ejecutarse en local y en CI sin conexión a internet ni consumo de cuotas. Toda llamada externa se prueba mediante dobles de prueba deterministas (*mocks* o *fixtures* de payloads reales).
4. **Gobernanza SemVer:** Sincronización estricta entre `src/version.py`, `CHANGELOG.md`, `README.md` y tags Git anotados.

---

## 2. Flujo de Desarrollo Guiado por Pruebas (TDD)

Todo desarrollo o corrección debe adherir al ciclo TDD:

1. **Fase Roja (`test:`):** Escribe primero la prueba unitaria en `tests/` que capture el requerimiento o reproduzca el error. Ejecuta `pytest` y confirma que falle. Realiza commit con prefijo `test:`.
2. **Fase Verde (`feat:` o `fix:`):** Implementa el código mínimo necesario en `src/` para que la prueba pase al 100%. Realiza commit con prefijo `feat:` o `fix:`.
3. **Refactorización y Calidad:** Verifica linters con `ruff check .` y confirma que la suite global se mantenga en verde (`pytest -q`).

---

## 3. Convenciones de Estilo

- **Formato y Linters:** Usamos `ruff`. Ejecuta antes de abrir cualquier PR:
  ```bash
  python -m ruff check .
  ```
- **Docstrings y Comentarios:**
  - Docstrings con mayúscula inicial y redactados en español formal.
  - Comentarios en línea estrictamente en formato `#texto` (en minúsculas y sin espacio tras la almohadilla).
- **Mensajes de Commit:** Formato convencional en minúsculas, sin tildes ni caracteres especiales (`feat:`, `test:`, `fix:`, `chore:`, `docs:`, `style:`).

---

## 4. Proceso para Enviar un Pull Request (PR)

1. Crea una rama descriptiva a partir de `main` actualizado (`feat/<tema>` o `fix/<tema>`). **Nunca** hacer commits directos en `main`.
2. Implementa tus cambios bajo el ciclo TDD.
3. Asegúrate de que todos los tests pasen y el linter esté limpio:
   ```bash
   python -m pytest tests/
   python -m ruff check .
   ```
4. Abre un Pull Request describiendo con claridad el problema resuelto y el alcance de las pruebas incluidas.
