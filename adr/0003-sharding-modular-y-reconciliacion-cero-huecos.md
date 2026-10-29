# ADR-0003: Sharding Modular Determinista y Reconciliación Cero-Huecos

- **Estado:** Aceptado
- **Fecha:** 2026-10-20

## Contexto y Problema
Extraer más de 109.000 aplicaciones de Steam desde un único nodo secuencial requería decenas de horas debido a las cuotas de tasa del endpoint `appdetails` (~200 peticiones cada 5 minutos por IP). Se necesitaba distribuir la carga entre múltiples entornos de ejecución (PC local y nodos efímeros en la nube como Google Colab / Kaggle) sin levantar infraestructura de colas centralizadas (Redis/RabbitMQ) ni bases de datos en la nube con costo recurrente.

## Alternativas Consideradas
1. **Cola de trabajo distribuida en la nube (Redis / Cloud Tasks):** Descartada por introducir costos operativos, credenciales adicionales y dependencias de red externas.
2. **División manual por rangos de AppID:** Descartada porque la densidad de juegos válidos no es uniforme a lo largo de los rangos numéricos de Steam, provocando desbalance severo de carga entre nodos.
3. **Manifiesto maestro congelado + particionamiento por congruencia modular (`idx % total_workers == worker_id`) + reconciliación criptográfica:** Seleccionada.

## Decisión
Congelar primero el universo de AppIDs en un archivo inmutable `manifest_master.json`. Cada worker recibe el manifiesto y calcula su subconjunto determinista mediante aritmética modular sobre el índice ordenado (`idx % N == k`), empaquetando snapshots periódicos en `.tar.gz`. Al finalizar, el reconciliador local fusiona los snapshots verificando que la unión de todos los workers cubra el 100% del manifiesto sin solapamientos ni huecos (Contrato 10).

## Consecuencias y Costos Aceptados
- **Sincronización manual de artefactos `.tar.gz`:** Requiere descargar los paquetes comprimidos de los nodos remotos y ejecutar el comando de reconciliación local.
- **Beneficio determinante:** Cero colisiones entre workers sin comunicación en tiempo real, balanceo de carga estadísticamente uniforme y costo de infraestructura en la nube igual a cero.

