$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

$mongoJS = @"
const d = db.getSiblingDB("norecov_demo");

d.libros.deleteMany({});
d.libros.insertMany([
  {titulo:"Bases de datos NoSQL",autor:"Equipo NORECOV",anio:2026},
  {titulo:"Resiliencia con Docker",autor:"Laboratorio BD2",anio:2026},
  {titulo:"MongoDB y Redis",autor:"NORECOV",anio:2026}
]);

d.eventos.deleteMany({});
d.eventos.insertMany([
  {tipo:"backup",ok:true},
  {tipo:"restore",ok:true}
]);

print(JSON.stringify({
  libros:d.libros.countDocuments({}),
  eventos:d.eventos.countDocuments({})
}));
"@

$archivo = ".\scripts\seed_demo.mongo.js"
Set-Content -Path $archivo -Value $mongoJS -Encoding ASCII

Write-Host "Copiando datos de prueba a MongoDB..."

docker compose --profile demo cp $archivo mongo-source:/tmp/norecov_seed.js

if ($LASTEXITCODE -ne 0) {
    throw "Error al copiar script MongoDB"
}

Write-Host "Insertando registros MongoDB..."

docker compose --profile demo exec -T mongo-source sh -c 'mongosh --quiet --username "$DEMO_MONGO_USER" --password "$DEMO_MONGO_PASSWORD" --authenticationDatabase admin --file /tmp/norecov_seed.js'

if ($LASTEXITCODE -ne 0) {
    throw "Error al insertar datos MongoDB"
}

Write-Host "Insertando registros Redis..."

docker compose --profile demo exec -T redis-source sh -c 'REDISCLI_AUTH="$DEMO_REDIS_PASSWORD" redis-cli MSET norecov:libro:1 NoSQL norecov:libro:2 Docker norecov:estado correcto'

if ($LASTEXITCODE -ne 0) {
    throw "Error al insertar datos Redis"
}

Write-Host "Datos de demostracion cargados correctamente."

