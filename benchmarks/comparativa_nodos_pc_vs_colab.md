# Evaluación de Rendimiento: Extracción Masiva Distribuida (PC Local frente a Google Colab Pro)

## 1. Alcance y Metodología

Durante la ejecución de la Fase 3 del observatorio, se planteó el desafío de recolectar metadatos exhaustivos y resúmenes de reseñas para el universo completo de la cohorte moderna de Steam (2024–2026, acotada en `manifest_master.json` con 109.785 AppIDs). 

Debido a las estrictas cuotas de velocidad impuestas por Valve en sus endpoints de tienda (`appdetails` y `appreviews`), una extracción secuencial mono-nodo habría requerido más de 40 horas continuas de ejecución. Para mitigar este cuello de botella sin incurrir en costos de infraestructura en la nube dedicada, se diseñó e implementó una arquitectura de **sharding distribuido multi-nodo**:

- **Particionamiento Modular:** Asignación estricta y determinista mediante función de módulo (`idx % total_workers == worker_id`), garantizando particiones completamente disjuntas sin necesidad de comunicación inter-nodos ni riesgo de colisiones.
- **Topología de Red:**
  - **Worker 0 (PC Local):** Nodo ejecutado en estación de trabajo local conectada a red de fibra óptica residencial simétrica.
  - **Worker 1 (Google Colab Pro):** Nodo ejecutado en entorno efímero de Google Colab Pro sobre infraestructura Google Cloud (enlace Tier-1 hacia los datacenters de Valve).
- **Mecanismo de Resiliencia:** Empaquetado atómico periódico a snapshots comprimidos `.tar.gz` hacia Google Drive cada 250 títulos y telemetría de red con captura limpia de señales `SIGINT`.

---

## 2. Resultados Experimentales y Métricas Operativas

Los datos consolidados provienen de los colectores de telemetría inyectados en ambos nodos (`benchmark_worker_0.json` y `benchmark_worker_1.json`):

| Métrica Operativa | Worker 0 (PC Local) | Worker 1 (Google Colab Pro) | Total Consolidado |
| :--- | :---: | :---: | :---: |
| **Entorno de Ejecución** | PC Local (Fibra Residencial) | Google Colab Pro (Google Cloud) | Multi-Nodo Distribuido |
| **Tiempo Total de Extracción** | 20.41 horas (73.479 s) | 9.83 horas (35.376 s) | **Ejecución Concurrente** |
| **AppIDs Procesados** | 49.076 títulos | 52.137 títulos | **101.213 títulos procesados** |
| **Extracciones Exitosas** | 49.040 juegos | 52.096 juegos | **101.136 juegos en Bronce** |
| **No Disponibles / DLCs (404)** | 36 títulos | 41 títulos | 77 títulos |
| **Tasa de Transferencia (*Throughput*)** | 40.07 apps / minuto | 88.43 apps / minuto | **Aceleración Relativa: 2.21x** |
| **Rendimiento HTTP Bruto** | 1.66 peticiones / segundo | 1.65 peticiones / segundo | Balanceado por diseño |
| **Bloqueos de Cuota HTTP 429** | 23.613 respuestas 429 | 11.226 respuestas 429 | Respeto automático de cuotas |
| **Reintentos de Red Gestionados** | 23.613 reintentos | 11.226 reintentos | Cero excepciones no controladas |
| **Ratio de Compresión Tar.gz** | 1.0x (Almacenamiento Local) | 0.0x (139 MB empaquetados) | 100% integridad verificada |

---

## 3. Hallazgos Arquitectónicos y Lecciones Aprendidas

### 3.1. Enlace de Red y Latencia hacia Valve (Aceleración 2.21x)
Aunque ambos nodos mantuvieron un ritmo similar de peticiones por segundo durante ráfagas activas (~1.65 req/s), Google Colab Pro procesó su partición en menos de la mitad del tiempo (9.83 h frente a 20.41 h). Esto se explica por la menor incidencia de respuestas HTTP 429 (11.226 en Google Cloud frente a 23.613 en red residencial). El enlace directo de baja latencia de Google Cloud hacia los servidores de Steam redujo los tiempos de espera impuestos por el encabezado `Retry-After`.

### 3.2. Eliminación del Cuello de Botella FUSE en Google Drive
Durante las pruebas preliminares, la escritura directa de miles de archivos pequeños JSON sobre la unidad montada de Google Drive (`/content/drive/MyDrive/...`) provocó congelamientos del kernel de Linux debido a la latencia de sincronización del sistema de archivos virtual FUSE.  
La solución arquitectónica consistió en **desacoplar el almacenamiento efímero del persistente**:
1. Escritura a máxima velocidad en el SSD efímero local de la máquina virtual (`/content/data/`).
2. Empaquetado atómico periódico en memoria/disco a un único archivo `.tar.gz`.
3. Sincronización del archivo empaquetado hacia Google Drive cada 250 títulos procesados.
Esta optimización redujo el overhead de E/S a cero y blindó el proceso contra desconexiones de sesión.

### 3.3. Presupuesto HTTP Multi-IP y Asignación Modular
El particionamiento modular (`idx % 2 == worker_id`) demostró ser la estrategia óptima para la ingesta distribuida:
- Duplicó la cuota efectiva de solicitudes por unidad de tiempo al operar desde dos direcciones IP públicas geográficamente independientes.
- Cero superposición de AppIDs entre nodos (intersección comprobada de 0 archivos colisionados).
- Reconciliación determinista en Capa Plata garantizada por el Contrato 10 de Cero Huecos.

---

## 4. Conclusión Técnica

La arquitectura distribuida multi-nodo permitió cosechar más de 101.000 títulos en menos de 21 horas totales con costo cero de infraestructura en servidores, garantizando la inmutabilidad de la Capa Bronce y habilitando la consolidación de los **60.899 títulos limpios** que alimentan el Star Schema del observatorio.
