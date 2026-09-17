# test-uipath-auth.ps1
# Paso 1 del servicio UiPath: autenticacion (client_credentials).
# NO dispara ningun job. Solo valida credenciales y obtiene el access_token.
#
# Las credenciales se leen de variables de entorno (NO hardcodear secretos):
#   $env:UIPATH_CLIENT_ID
#   $env:UIPATH_CLIENT_SECRET
# Uso:
#   $env:UIPATH_CLIENT_ID="..."; $env:UIPATH_CLIENT_SECRET="..."; ./test-uipath-auth.ps1

$ErrorActionPreference = "Stop"

$tokenUrl     = if ($env:UIPATH_TOKEN_URL) { $env:UIPATH_TOKEN_URL } else { "https://cloud.uipath.com/grupopurdyrentingcommunity/identity_/connect/token" }
$clientId     = $env:UIPATH_CLIENT_ID
$clientSecret = $env:UIPATH_CLIENT_SECRET
$scope        = if ($env:UIPATH_SCOPE) { $env:UIPATH_SCOPE } else { "OR.Queues OR.Jobs OR.Assets OR.Folders" }

if (-not $clientId -or -not $clientSecret) {
  Write-Host "Faltan credenciales. Define las variables de entorno UIPATH_CLIENT_ID y UIPATH_CLIENT_SECRET." -ForegroundColor Yellow
  exit 1
}

$body = @{
  grant_type    = "client_credentials"
  client_id     = $clientId
  client_secret = $clientSecret
  scope         = $scope
}

Write-Host "== Paso 1: Autenticacion UiPath ==" -ForegroundColor Cyan
Write-Host "POST $tokenUrl"

try {
  $resp = Invoke-RestMethod -Uri $tokenUrl -Method Post -Body $body -ContentType "application/x-www-form-urlencoded"
} catch {
  Write-Host "ERROR de autenticacion:" -ForegroundColor Red
  Write-Host $_.Exception.Message
  exit 1
}

if ($resp.access_token) {
  $tok = $resp.access_token
  Write-Host "OK: token obtenido." -ForegroundColor Green
  Write-Host ("token_type : " + $resp.token_type)
  Write-Host ("expires_in : " + $resp.expires_in + " s")
  Write-Host ("scope      : " + $resp.scope)
  Write-Host ("longitud token: " + $tok.Length)
} else {
  Write-Host "La respuesta no contiene access_token." -ForegroundColor Yellow
  exit 1
}