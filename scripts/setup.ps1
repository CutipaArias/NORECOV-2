# Uso en Windows PowerShell 5.1 o 7: powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
$ErrorActionPreference = 'Stop'
$dest = Join-Path (Split-Path $PSScriptRoot -Parent) '.env'
if (Test-Path $dest) { Write-Host 'Ya existe .env. No se sobrescribio.'; exit 0 }
function Random-Bytes([int]$count) {
  $bytes = New-Object byte[] $count
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  return ,$bytes
}
function New-Secret {
  [Convert]::ToBase64String((Random-Bytes 24)).TrimEnd('=').Replace('+','-').Replace('/','_')
}
$control = New-Secret
$admin = New-Secret
$demoMongo = New-Secret
$demoRedis = New-Secret
$minio = New-Secret
$key = [Convert]::ToBase64String((Random-Bytes 32))
$signing = New-Secret
$content = @"
CONTROL_MONGO_USER=norecov_admin
CONTROL_MONGO_PASSWORD=$control
CONTROL_MONGO_URI=mongodb://norecov_admin:$control@mongo-control:27017/admin?authSource=admin
CONTROL_DB=norecov
SECRET_KEY=$signing
ENCRYPTION_KEY=$key
ADMIN_EMAIL=admin@norecov.local
ADMIN_PASSWORD=$admin
CORS_ORIGINS=http://localhost:5173,http://localhost:8080
ARTIFACT_DIR=/data/artifacts
DEMO_MONGO_USER=root
DEMO_MONGO_PASSWORD=$demoMongo
DEMO_REDIS_PASSWORD=$demoRedis
NORECOV_MINIO_USER=norecovminio
NORECOV_MINIO_PASSWORD=$minio
"@
[System.IO.File]::WriteAllText($dest, $content, [System.Text.UTF8Encoding]::new($false))
Write-Host 'Archivo .env creado.'
Write-Host "Usuario inicial: admin@norecov.local"
Write-Host "Contrasena inicial: $admin"
Write-Host 'Guarda la contrasena en un lugar seguro.'
