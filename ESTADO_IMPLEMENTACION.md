# NORECOV — Matriz honesta de cobertura (versión 0.1.0)

Fecha: 2026-11-05. Fuente: documentación FD01, FD02, FD03 (SRS) y FD04 (SAD) suministrada.

Convenciones: **Implementado en código** significa que existe una ruta funcional programada, **pendiente de prueba integral** significa que no se ha comprobado contra un Docker Engine real en el entorno de construcción. No equivale a requisito certificado.

| RF | Implementación en código | Límites conocidos / prueba pendiente |
|---|---|---|
| RF-01 | API CRUD de nodos MongoDB 6.0 y Redis 7.0; prueba de enlace; credenciales cifradas. | Cassandra no implementado; verificar autenticación TLS en topologías reales. |
| RF-02 | Plan cron UTC en MongoDB + APScheduler y cola persistente. | Probar programaciones y ejecución tras reinicio de contenedores. |
| RF-03 | `mongodump --archive --gzip`, `redis-cli --rdb -`, verificación CLI y reintentos. | Validar RDB binario y rendimiento real; Cassandra pendiente. |
| RF-04 | Flujo AES-256-GCM; MongoDB genera archivo comprimido GZIP desde CLI. | Redis RDB usa su formato nativo y no se comprime adicionalmente; zstd no implementado. |
| RF-05 | SHA-256 durante cifrado, comparación al leer y tras subir S3. | Ensayo de transferencia S3 en host real. |
| RF-06 | Docker SDK, versión `mongo:6.0`/`redis:7.0-alpine`, límites y red deshabilitada. | Prueba integral de Docker pendiente; usar host aislado para producción. |
| RF-07 | Streaming de descifrado a tar Docker; `mongorestore` o carga del RDB antes del inicio Redis. | Verificación con contenedores reales pendiente. |
| RF-08 | Conteos por colección y DB en MongoDB; por DB en Redis; igualdad estricta. | Snapshot fuente no transaccional; escrituras concurrentes podrían causar falsos fallos. |
| RF-09 | RTO en milisegundos; tiempo de backup; antigüedad estimada del punto. | RPO real ante desastre no demostrado; umbrales formales no probados. |
| RF-10 | `finally` elimina el contenedor de Sandbox y sus volúmenes temporales. | Verificar que nunca quedan recursos colgados tras fallos fuertes del daemon. |
| RF-11 | Guardado de alertas y distribución HTTPS webhook/SMTP con prueba de canal. | Falta probar canales reales Slack, Teams y SMTP. |
| RF-12 | Retención diaria y manual, preservando dos copias válidas por nodo. | Verificar WORM y podas tras vencimiento; faltan políticas avanzadas. |
| RF-13 | Destino local y cliente boto3 para S3/MinIO, test de escritura/lectura, metadatos y Object Lock opcional. | Integración S3/MinIO real pendiente; GCS nativo no incluido. |
| RF-14 | Dashboard React, tasa de éxito, espacio cifrado, RTO e historial. | Medir 1.5 s y mejorar filtros avanzados. |
| RF-15 | JWT + roles DBA Master/DBA/DevOps/Soporte/Auditor en API e interfaz. | Faltan pruebas automatizadas RBAC y rotación de claves/contraseñas. |
| RF-16 | Auditoría append-only desde API y worker; exportación CSV. | Inmutabilidad física/WORM y exportación PDF/SIEM pendientes. |
| RF-17 | Descarga de artefacto validado y guía de restauración + CLI manual. | Ensayo completo de recuperación ante desastre pendiente. |

## Riesgos antes de producción

1. **Nunca** montar Docker socket en host compartido o expuesto en Internet.
2. Ejecutar un proxy con TLS 1.3 y autenticación reforzada (MFA) en producción; versión local es HTTP loopback.
3. Backups con grandes datasets necesitan tests de carga, diseño de colas de alta disponibilidad y snapshot consistente de origen.
4. El entorno local de desarrollo no dispone de Docker Engine ni acceso npm útil para ejecutar toda la batería de integración; no afirmar aprobación de estas pruebas.
5. Los binarios nativos del worker MongoDB y Redis corresponden a las versiones objetivo del SAD; validación con imágenes reales indispensable.
