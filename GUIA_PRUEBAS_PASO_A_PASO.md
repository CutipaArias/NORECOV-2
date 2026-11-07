# Guía de pruebas: NORECOV en Windows + Docker Desktop

Esta guía está pensada para demostrar ante el docente que la restauración **no es simulada**. No ejecutes estas instrucciones contra datos de producción.

## A. Antes de abrir la web

En PowerShell, situado en la carpeta NORECOV:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
docker compose --profile demo up -d --build --scale worker=2
docker compose --profile demo ps
(Invoke-RestMethod http://localhost:8000/api/health).status
```

**Resultado esperado:** API `ok`, servicios `api`, `web`, `mongo-control`, `scheduler`, `worker`, `mongo-source`, `redis-source` en estado levantado. La primera construcción depende de Internet.

Si no aparece `ok`, revisa:

```powershell
docker compose logs --tail=70 api
docker compose logs --tail=70 mongo-control
```

## B. Crear datos recuperables

En Windows PowerShell, sin instalar Python:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\seed_demo.ps1
```

Alternativamente, con Python: `py -3 .\scripts\seed_demo.py`.

**Resultado esperado:** MongoDB con **3 libros y 2 eventos** en `norecov_demo`; Redis con **3 claves**.

## C. Comprobar backup MongoDB

1. Abre `http://localhost:8080` e inicia sesión con la contraseña mostrada por `setup.ps1` (o guardada cuando generaste `.env`).
2. Ve a **Nodos NoSQL** → **Registrar nodo**.
3. Completa MongoDB 6.0, `mongo-source`, `27017`, `root`, contraseña `DEMO_MONGO_PASSWORD` del `.env`, autenticación `admin`.
4. Pulsa **Verificar y registrar**.
5. En la fila del nodo, haz clic en **Backup ahora**.
6. Abre **Cola de trabajos**. El estado debería transitar `En cola` → `Ejecutando` → `Completado`.
7. Abre **Restauraciones** → **Ver informe** y comprueba las colecciones `libros: 3` y `eventos: 2` tanto en origen como en Sandbox.
8. En **Respaldos** verifica el estado **Validado** y descarga la copia cifrada y guía.

Para comprobar operaciones reales desde Docker:

```powershell
docker compose logs --tail=130 worker
docker ps --filter label=norecov.sandbox=true
```

Después de concluir, el segundo comando no debe mostrar contenedores de Sandbox en ejecución.

## D. Comprobar backup Redis

1. Registra Redis 7.0 como nodo en `redis-source:6379`, usuario vacío, password `DEMO_REDIS_PASSWORD` del `.env`.
2. Pulsa **Backup ahora**.
3. Revisa **Restauraciones**: el detalle debe comparar el número de claves del origen y Sandbox, que con los datos iniciales son 3 en DB0.
4. Comprueba de nuevo que no queden contenedores etiquetados `norecov.sandbox=true`.

## E. Verificar una política de backup

1. Ve a **Programaciones** → **Nueva programación**.
2. Selecciona el nodo de MongoDB y cron `*/10 * * * *` (cada diez minutos, horario UTC).
3. Espera al siguiente intervalo programado, actualiza **Cola de trabajos** y comprueba que se añadió un trabajo automático.
4. Comprueba que hay nuevos archivos `.norecov`, no `.archive` ni `.rdb` sin cifrar, en el repositorio.

## F. Cifrado, alertas y auditoría

1. Descarga un archivo `.norecov` validado: si lo abres como texto, no debe contener los documentos JSON originales.
2. Descarga la guía de producción: debe advertir que NORECOV no restaura automáticamente el nodo original.
3. En **Usuarios y roles**, crea una cuenta de auditor y verifica que solo pueda leer los módulos autorizados.
4. En **Auditoría**, exporta CSV y comprueba el registro `backup.created`, `restore.validated`, `auth.login`.
5. En **Notificaciones**, registra un webhook HTTPS propio o SMTP y usa **Probar** para confirmar conectividad antes de habilitarlo.

## G. Si falla una prueba

- `503` en API: MongoDB de control no está disponible o los secretos no corresponden a su volumen persistente.
- `connection refused` al registrar nodo: verifica host (`mongo-source`, no `localhost`) y que el perfil `demo` está levantado.
- `permission denied` al crear Sandbox: revisa el montaje del Docker socket y que Docker Desktop use contenedores Linux.
- `no such image`: Docker no pudo descargar `mongo:6.0` o `redis:7.0-alpine`.
- `Crítico / corrupto`: consulta el campo de error del trabajo y compara los conteos. En bases con escrituras concurrentes el conteo previo puede variar.
- NO cambies `.env` sin respaldar las claves: cambiar `ENCRYPTION_KEY` vuelve irrecuperables los artefactos anteriores.

## H. Evidencias que conviene entregar

Captura del login, dashboard, nodos registrados, programación cron, backup validado MongoDB, backup validado Redis, reporte de comparación de conteos, job completado, bitácora, y el estado Docker tras eliminar Sandbox.

**Nota:** los objetivos de 99.5 % de disponibilidad, RPO menor a 15 min y RTO menor a 30 min requieren una campaña de pruebas aparte; las capturas del laboratorio no los certifican automáticamente.
