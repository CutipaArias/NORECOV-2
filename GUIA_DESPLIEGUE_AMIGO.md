# NORECOV - Guía de despliegue en otra computadora

## Alcance

Este ZIP procede de la carpeta local NORECOV y conserva las correcciones del
Sandbox de MongoDB y Redis, la integración con MinIO y la carga de datos para
PowerShell. Es una versión de laboratorio: las bases de datos, archivos de
respaldo, usuarios, programaciones e historial de la computadora original **no**
viajan dentro del ZIP. La validación de contenidos completos y la protección
para publicar en Internet requieren más trabajo.

## Instalación en Windows

1. Instala Docker Desktop con motor Linux y WSL 2. Abre Docker Desktop.
2. Descomprime `NORECOV-ENTREGA-VERIFICADA.zip`; abre PowerShell en la carpeta
   `NORECOV`, donde está `docker-compose.yml`.
3. Genera **nuevas** claves locales con:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
   ```

   Guarda la contraseña inicial del portal; no compartas el `.env`.
4. Inicia los servicios (la imagen local de MinIO se compila la primera vez):

   ```powershell
   docker compose --profile demo config --quiet
   docker compose --profile demo up -d --build --scale worker=2
   docker compose --profile demo ps
   ```

5. Abre `http://localhost:8080` y accede como `admin@norecov.local` con la
   contraseña que imprimió el script. API de salud: `http://localhost:8000/api/health`.
6. Crea datos de laboratorio si necesitas hacer demostraciones:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\seed_demo.ps1
   ```

7. En **Nodos NoSQL**, registra MongoDB con host `mongo-source`, puerto `27017`,
   usuario `root`, contraseña `DEMO_MONGO_PASSWORD` (valor real de `.env`) y auth
   DB `admin`. Registra Redis con host `redis-source`, puerto `6379`, usuario vacío
   y contraseña `DEMO_REDIS_PASSWORD` (valor real de `.env`).
8. Prueba respaldos, restauración y los informes de conteos desde la interfaz.

## MinIO / S3 en laboratorio

- Abre `http://localhost:9001` con el usuario `NORECOV_MINIO_USER` y la contraseña
  `NORECOV_MINIO_PASSWORD` de `.env`.
- Crea el bucket **privado** `norecov-backups`.
- En **Repositorios -> Nuevo repositorio**, selecciona S3/MinIO: endpoint
  `http://minio:9000` (sin localhost), bucket `norecov-backups`, región
  `us-east-1`, access key `norecovminio`, secret key de `.env`.
- Crea una programación que use ese repositorio para validar que aparecen objetos
  bajo `backups/`. Borra la programación temporal cuando termine la prueba.
- En esta versión, la restauración se ha probado con los conteos de registros.
  No equivale a comprobar todos los valores de cada registro.

## Advertencias y comprobaciones

- No copies el `.env` de otra computadora: allí están los secretos.
- No ejecutes `docker compose down -v` en un entorno con datos que deseas conservar;
  elimina volúmenes persistentes.
- El acceso del worker al socket Docker es privilegiado. Los puertos se publican
  solo en `127.0.0.1`. Este despliegue **no** debe exponerse directamente a Internet
  sin rediseñar el acceso, TLS, permisos y aislamiento del orquestador.
- No se incluyen los volúmenes MongoDB, Redis, MinIO ni los `.norecov` anteriores.
- Para revisar problemas: `docker compose --profile demo logs --tail 80 worker` o
  `docker compose --profile demo logs --tail 80 scheduler`.
