# NORECOV — NoSQL Backup & Disaster Recovery Testing Manager

Proyecto académico de **Base de Datos II**, basado en los informes FD01 (Factibilidad), FD02 (Visión), FD03 (SRS) y FD04 (SAD). Versión de desarrollo 0.1.0.

## Requisitos locales

- Windows 10/11 con **Docker Desktop** abierto (contenedores Linux) y Docker Compose v2, o Linux con Docker Engine 24+.
- Mínimo sugerido para laboratorio: 8 GB de RAM disponibles y 10 GB de espacio en disco.
- Conexión a Internet para obtener imágenes Docker y dependencias en la **primera instalación**.
- Para generar los secretos: PowerShell en Windows o Python 3 en Linux/macOS.
- No ejecutar contra una base de producción sin evaluación de permisos, red, recursos y respaldos de contingencia.

## Inicio en Windows PowerShell (paso a paso)

1. Descomprime la carpeta **NORECOV** en tu PC, por ejemplo en el Escritorio.
2. Abre **Docker Desktop** y espera que el motor esté iniciado.
3. Abre PowerShell dentro de la carpeta NORECOV (donde está `docker-compose.yml`).
4. Genera las claves privadas con este comando:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
   ```

   **Guarda la contraseña que aparece en pantalla.** El usuario será `admin@norecov.local`. El archivo `.env` queda excluido de Git.

5. Inicia el sistema y las bases de laboratorio:

   ```powershell
   docker compose --profile demo up -d --build --scale worker=2
   ```

6. Revisa el estado:

   ```powershell
   docker compose --profile demo ps
   ```

7. Verifica la API en `http://localhost:8000/api/health` y abre **http://localhost:8080** para el portal. API interactiva: `http://localhost:8000/api/docs`.
8. Inserta los datos de ejemplo con PowerShell (sin instalar Python):

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\seed_demo.ps1
   ```

   Alternativa, si ya tienes Python: `py -3 .\scripts\seed_demo.py`.
9. Entra con el usuario `admin@norecov.local` y la contraseña generada.

## Primera demostración guiada

### MongoDB

1. En **Nodos NoSQL** selecciona **Registrar nodo**.
2. Nombre: `MongoDB Laboratorio`; motor: `MongoDB 6.0`; host: `mongo-source`; puerto: `27017`.
3. Usuario: `root`; contraseña: valor `DEMO_MONGO_PASSWORD` de `.env`; autenticación: `admin`. Déjalo sin TLS solo para el laboratorio local.
4. Selecciona **Verificar y registrar**. El backend comprobará la conexión y la versión.
5. En la tabla del nodo pulsa **Backup ahora**. El trabajo irá a la cola, extraerá con `mongodump --archive --gzip`, guardará cifrado y probará `mongorestore` en Sandbox.
6. Abre **Cola de trabajos** y espera que aparezca como `Completado`; en **Respaldos** deberá figurar `Validado`; en **Restauraciones**, `Validado` con el RTO.
7. Abre **Respaldos** para descargar la copia **cifrada** y la guía de restauración. Solo se habilitan si la prueba fue exitosa.

### Redis

1. Registra otro nodo: `Redis Laboratorio`, motor `Redis 7.0`, host `redis-source`, puerto `6379`.
2. Deja vacío el usuario e ingresa `DEMO_REDIS_PASSWORD` de `.env` como contraseña.
3. Ejecuta **Backup ahora**, observa la extracción `redis-cli --rdb -` y la restauración real de RDB en un contenedor `redis:7.0-alpine` aislado.
4. Comprueba el conteo de claves en **Restauraciones → Ver informe**.

### Programaciones

1. Abre **Programaciones → Nueva programación**, elige nodo.
2. Expresión `*/10 * * * *` (cada 10 minutos, horario UTC), 30 días de retención.
3. Guarda y revisa los trabajos creados por el Scheduler (sin necesidad de pulsar botones).

### Usuarios, alertas y auditoría

- Un **DBA Master** puede crear cuentas y asignar roles DBA, DevOps, Soporte y Auditor.
- En **Repositorios**, DevOps configura local o S3/MinIO. S3 requiere un bucket creado de antemano.
- En **Notificaciones**, crea un destino HTTPS o SMTP; el canal solo se activa tras una prueba satisfactoria.
- En **Auditoría** consulta acciones y descarga CSV.

## Comandos de mantenimiento

```powershell
# Ver logs del worker
 docker compose logs --tail=100 worker
# Ver logs del API
 docker compose logs --tail=100 api
# Reiniciar servicios sin borrar volúmenes
 docker compose --profile demo restart
# Parar contenedores sin borrar datos
 docker compose --profile demo down
```

**No uses `docker compose down -v` salvo que quieras perder los datos de laboratorio, MongoDB de control y los artefactos cifrados**.

## Arquitectura

```text
web (React + Vite + Nginx)
  └── API REST (FastAPI + JWT + RBAC)
          ├── MongoDB de control (usuarios, nodos, planes, cola, auditoría)
          ├── Scheduler (APScheduler, cron UTC)
          └── Worker(s) (cola persistida en MongoDB)
                 ├── Adaptador mongodump 6.0 / redis-cli 7.0
                 ├── AES-256-GCM en flujo + SHA-256
                 ├── Almacén cifrado local / S3 compatible
                 ├── Docker SDK → Sandbox sin red → restaurar → comparar
                 └── Alertas + retención
```

| Carpeta | Descripción |
|---|---|
| `backend/app/api.py` | API REST, autorización RBAC y endpoints |
| `backend/app/jobs.py` | Orquestación y cola |
| `backend/app/adapters/` | Extracción y metadata de MongoDB / Redis |
| `backend/app/crypto.py` | Formato cifrado y huellas SHA-256 |
| `backend/app/sandbox.py` | Restauración en Docker sin red |
| `backend/app/scheduler.py` | Programación recurrente |
| `backend/app/storage.py` | Archivo local y S3/MinIO |
| `backend/tests/` | Pruebas unitarias de cifrado y empaquetado |
| `web/src/` | Portal React |
| `scripts/recover_artifact.py` | Descifrado manual en recuperación controlada |
| `ESTADO_IMPLEMENTACION.md` | Matriz de cobertura y limitaciones |

## Seguridad y consideraciones de despliegue

- **Cifrado obligatorio:** la salida comprimida del extractor se cifra de forma incremental en AES-256-GCM antes de almacenarse. El archivo `.norecov` incluye nonce y etiqueta GCM. Una huella SHA-256 separada comprueba la transferencia.
- **Credenciales:** cifradas en la base de control. El administrador debe proteger `.env` y las claves de recuperación; perder `ENCRYPTION_KEY` impide recuperar los respaldos.
- **Sandbox:** se ejecuta con `network_disabled=True`, límites de CPU/memoria y sin capacidades Linux. No monta la base productiva. El descifrado se transfiere por Docker API al contenedor y no se escribe en disco del orquestador.
- **Docker socket:** el worker monta `/var/run/docker.sock`, lo cual equivale a privilegios altos sobre Docker. **Solo habilitarlo en un host de laboratorio confiable.** Para producción, sustituirlo por un host de sandboxes aislado y una API Docker protegida con mTLS.
- **HTTPS/TLS 1.3:** en este laboratorio el portal se publica localmente en HTTP `127.0.0.1:8080`. El cumplimiento TLS 1.3 requiere configurar reverse proxy y certificados antes de exponerlo públicamente.
- **NODO DE ORIGEN:** el adaptador MongoDB puede necesitar credenciales de lectura y backup; Redis RDB por replicación puede requerir permisos adicionales. No usar credenciales administrativas para producción.
- **Consistencia:** la metadata de origen se captura cerca del instante del backup, no necesariamente en un snapshot transaccional. Si hay escrituras concurrentes pueden aparecer falsos desajustes de conteo. Se requiere una estrategia de snapshots replicados para objetivos estrictos.
- **RTO/RPO:** RTO se cronometra en Sandbox; RPO mostrado es edad aproximada del punto de captura al final de la prueba, **no prueba de cumplimiento de un RPO de 15 minutos ante un desastre**.
- **Auditoría:** inserción exclusiva desde la aplicación, sin endpoints para editar/eliminar. Para un registro verificablemente inmutable se necesita almacenamiento WORM o envío a SIEM.
- **Retención:** conserva las dos últimas copias válidas por nodo. El modo WORM en S3 puede impedir la poda hasta el vencimiento.

## Pruebas y verificación

Con Python 3.12 y dependencias instaladas:

```bash
cd backend
pip install -r requirements-dev.txt
pytest -q
```

Para prueba integral:

```powershell
# API accesible, contenedores y worker
Invoke-RestMethod http://localhost:8000/api/health
docker compose --profile demo ps
docker compose logs --tail=100 worker
```

No certifica rendimiento, disponibilidad de 99.5 %, CPU del extractor ni resiliencia de 100 nodos sin pruebas bajo carga e infraestructura real.

## Recuperación manual (solo ambiente confiable)

1. Descarga el archivo `.norecov` validado y su guía.
2. Obtén `ENCRYPTION_KEY` desde un secreto externo seguro (no desde una copia publicada del repositorio).
3. Instala `cryptography`, exporta la variable `ENCRYPTION_KEY` y descifra:

```bash
python scripts/recover_artifact.py --input copia.norecov --output backup-restaurado.archive
```

4. Sigue los comandos de la guía por motor. El archivo restaurado es **plaintext**; elimínalo según la política de seguridad.

## Requisitos en desarrollo

La versión actual es un **prototipo ejecutable orientado a laboratorio**, no una plataforma de producción certificada. Consulta `ESTADO_IMPLEMENTACION.md` para la distinción entre implementación y verificaciones aún pendientes.


## Despliegue portátil con MinIO

El archivo `docker-compose.override.yml` añade MinIO al despliegue, con puertos
locales `9000` (API) y `9001` (consola). La imagen se compila desde
`minio-lab/Dockerfile`, por lo que la primera construcción requiere Internet.

En una instalación nueva, **siempre** ejecuta `scripts/setup.ps1` (Windows) o
`scripts/generate_env.py` (Python) antes de `docker compose up`. Ambos generan
las variables `NORECOV_MINIO_USER` y `NORECOV_MINIO_PASSWORD` además del resto de
secretos. Si ya existe un `.env` de una versión anterior, no se sobrescribe:
añade las dos variables a mano con credenciales seguras.

Para registrar MinIO desde la interfaz: abre `http://localhost:9001`, crea un
bucket privado `norecov-backups`, luego en **Repositorios** selecciona S3/MinIO
con endpoint `http://minio:9000`, bucket `norecov-backups`, región `us-east-1`,
access key `norecovminio` y secret key igual al valor de
`NORECOV_MINIO_PASSWORD` en `.env`.

Consulta `GUIA_DESPLIEGUE_AMIGO.md` para el procedimiento completo y los límites
de esta versión académica.
" https://organic-sniffle-wrj5776gv445f94gw-8080.app.github.dev/ "
