# Purdy Renting - Contexto de despliegue (AWS SAM)

Guia de referencia para desplegar y operar la plataforma Purdy Renting en AWS.
Refleja las decisiones tomadas y el estado del entorno `staging`.

## Arquitectura (serverless)

- **Backend**: 6 funciones Lambda (Python) en `backend/handlers/`, con servicios
  en `backend/services/` y utilidades en `backend/utils/`.
- **Frontend**: SPA React + Vite + TypeScript en `frontend/`.
- **Infraestructura**: AWS SAM, plantilla unica en `infrastructure/template.yaml`.
- **Datos**: DynamoDB single-table (`PK`/`SK` + GSI1 para consultas por usuario).
- **Archivos**: S3 (`FilesBucket`) para cargas y archivos generados.
- **Web**: S3 (`SiteBucket`) + CloudFront (OAC) sirven el SPA.
- **Auth**: Cognito User Pool NATIVO (email + password), sin Hosted UI.
- **Integraciones externas**: UiPath Orchestrator (dispara un job) y un webhook
  POST (Power Automate) para notificaciones. Ninguna factura en AWS.

## Runtime de Lambda

- Runtime: **python3.14**. NO usar python3.11 (deprecado; Lambda ya no permite
  crearlo/actualizarlo). El build local requiere tener python3.14 en PATH, o
  usar `sam build --use-container` con Docker corriendo.
- El empaquetado usa `backend/requirements.txt` (SOLO deps de runtime:
  `python-dateutil`). `boto3` ya viene en el runtime de Lambda, no se empaqueta.
- Las dependencias de test estan en `backend/requirements-dev.txt`
  (`pytest`, `hypothesis`, `moto`, `boto3`). NO deben empaquetarse en Lambda.

## Autenticacion (Cognito nativo)

- El User Pool es nativo: `AllowAdminCreateUserOnly: true` (solo el admin da de
  alta usuarios; no hay auto-registro). No hay federacion Entra ID ni Hosted UI.
- El SPA administra su propio formulario de login (`LoginPage.tsx`) usando
  Amplify v6 (`signIn` / `confirmSignIn`). Flujos habilitados en el client:
  `USER_PASSWORD_AUTH`, `USER_SRP_AUTH`, `REFRESH_TOKEN_AUTH`.
- Existe un grupo Cognito **`solicitantes`** (rol). El admin asigna el usuario
  a este grupo tras crearlo.
- Usuarios nuevos entran en estado `FORCE_CHANGE_PASSWORD`: en el primer login
  Cognito exige `NEW_PASSWORD_REQUIRED`, que `LoginPage.tsx` maneja pidiendo la
  nueva contrasena.

### IMPORTANTE: el frontend debe enviar el ID token (no el access token)

El authorizer Cognito y los handlers del backend leen los claims `email` y
`name`, que SOLO existen en el **ID token** (el access token de Cognito no
incluye atributos de perfil). En `frontend/src/config/api.ts` y
`frontend/src/services/fileService.ts` se usa `session.tokens?.idToken`. No
cambiar a `accessToken` o el backend devolvera 401.

### Crear un usuario (admin)

```bash
aws cognito-idp admin-create-user \
  --user-pool-id <UserPoolId> \
  --username <email> \
  --user-attributes Name=email,Value=<email> Name=email_verified,Value=true Name=name,Value="<Nombre>" \
  --temporary-password '<TempPassword>' \
  --message-action SUPPRESS --region us-east-1

aws cognito-idp admin-add-user-to-group \
  --user-pool-id <UserPoolId> --username <email> \
  --group-name solicitantes --region us-east-1
```

## CORS / API Gateway

- El API usa `DefaultAuthorizer: CognitoAuthorizer`, pero con
  **`AddDefaultAuthorizerToCorsPreflight: false`**. Esto es imprescindible: sin
  ello, el preflight `OPTIONS` (que el navegador envia sin token) devuelve 401
  y el navegador bloquea la peticion real. Con el flag, los OPTIONS son publicos
  y solo devuelven headers CORS.
- El origen permitido (CORS de API Gateway y S3, y las gateway responses de
  error) se controla con el parametro `FrontendDomain`. En staging apunta al
  dominio de CloudFront.

## Secretos (AWS Secrets Manager)

- Los secretos de integraciones NO se versionan ni se dejan como env vars en
  claro. Viven en un secreto de Secrets Manager con un JSON:

  ```json
  {
    "uipath_client_secret": "...",
    "notification_webhook_url": "..."
  }
  ```

- `backend/services/secrets.py` lee y cachea el secreto. `uipath_service.py` y
  `notification_service.py` resuelven sus valores desde ahi, con fallback a
  variables de entorno para desarrollo local.
- El ARN del secreto se pasa al deploy via el parametro `IntegrationsSecretArn`.
  La `CreateRequestFunction` recibe permiso IAM `secretsmanager:GetSecretValue`
  restringido a ese ARN (least-privilege), y la env var `INTEGRATIONS_SECRET_ID`.
- Los parametros `UiPathClientSecret` y `NotificationWebhookUrl` son solo
  fallback opcional (default vacio). Preferir siempre Secrets Manager.

### Actualizar/rotar el secreto

```bash
aws secretsmanager put-secret-value \
  --secret-id purdy-renting/staging/integrations \
  --secret-string '{"uipath_client_secret":"<NUEVO>","notification_webhook_url":"<URL>"}' \
  --region us-east-1
```

## Integracion UiPath

- Flujo de 2 pasos en `backend/services/uipath_service.py`: (1) auth
  `client_credentials` contra el identity server, (2) `StartJobs` (OData) en
  Orchestrator.
- `InputArguments` (STRING JSON anidado) enviado en el `StartJobs`:
  - `in_Archivo1Base64`: URL presignada GET del Listado de Precios.
  - `in_Archivo2Base64`: URL presignada GET del Catalogo DAI.
  - `in_NombreEmpresa`: nombre de la empresa del formulario.
- El disparo es **best-effort**: si falla, NO bloquea la creacion de la
  solicitud (el registro ya existe y el usuario recibio confirmacion).

### IMPORTANTE: se envian URLs presignadas, NO base64

El campo `InputArguments` de UiPath esta limitado a **10.000 caracteres**. El
contenido de los archivos en base64 lo excede (UiPath responde HTTP 400:
"InputArguments must be a string ... maximum length of '10000'"). Por eso
`create_request.py` genera **URLs presignadas GET** de S3 (vigencia por defecto
6h, env `UIPATH_URL_EXPIRY_SECONDS`) y las envia en los argumentos.

Los NOMBRES de argumento se conservan (`in_Archivo1Base64` /
`in_Archivo2Base64`) para no cambiar el contrato del bot existente, pero su
CONTENIDO es ahora una URL de descarga. El workflow de UiPath debe **descargar
el archivo con un GET a la URL**, no decodificar base64. Las URLs no requieren
credenciales AWS (la firma va en la query) y expiran.

### IMPORTANTE: User-Agent obligatorio

El identity server de UiPath (tras Cloudflare/WAF) responde **403 Forbidden**
al User-Agent por defecto de urllib (`Python-urllib/x.y`). Ambas llamadas HTTP
envian un header `User-Agent` explicito (constante `_USER_AGENT`, configurable
via env `UIPATH_USER_AGENT`). No quitarlo o UiPath devolvera 403 en auth.

## Notificaciones

- `backend/services/notification_service.py` hace POST al webhook externo
  (Power Automate) con este body:

  ```json
  {
    "destinatario": "...",
    "asunto": "...",
    "enlaceUrl": "...",
    "ejecutivoNombre": "...",
    "cuerpoHtml": "..."
  }
  ```

- Best-effort con reintentos (1s/2s/4s). No usa SES (se removio del template).

## Contrato de API relevante

- `GET /requests` devuelve **`{ "requests": [...] }`** (objeto con clave, no un
  array directo). El frontend (`requestService.getRequests`) extrae
  `data.requests`. Mantener este contrato o ajustar ambos lados.
- `GET /requests/{id}/download` devuelve `{ downloadUrl, fileName }`.
- `POST /requests` devuelve `{ requestId, message }`.
- `GET /requests` incluye tambien `detail` y `typeFailed` (resultado del RPA)
  para alimentar el modulo de seguimiento.
- Endpoints de Robot (`PUT /requests/{id}/status`, `POST /requests/{id}/file`)
  usan API key (no Cognito), con el usage plan auto-generado por SAM
  (`ApiApiKey`, quota 10k/dia, throttle 10 rps).

### Endpoint de cierre de solicitud (resultado del RPA)

- `POST /requests/{id}/result` (handler `backend/handlers/submit_result.py`)
  cierra la solicitud en una sola llamada y alimenta el seguimiento.
- Auth: **API key PROPIA** (`ResultApiKey` / `ResultUsagePlan`), distinta de la
  de los demas endpoints Robot, para poder rotarla aparte. Se envia en el header
  `x-api-key`. Throttle 5 rps / burst 10, quota 5000/dia.
- Body (JSON):
  - `status`: `"Success"` | `"Failed"` (obligatorio). Se mapea a estado interno
    via `RESULT_STATUS_MAP`: `Success -> Procesado`, `Failed -> Failed`.
  - `detail`: texto descriptivo (opcional, <= 1000 chars).
  - `type_failed`: `"Business Exception"` | `"IT Exception"` | `""` (opcional).
  - `archivo_generado`: contenido del archivo generado en base64 (opcional;
    tipico en exito). Si viene, `file_name` es obligatorio.
  - `file_name`: nombre del archivo generado (requerido si hay archivo). Se
    guarda en S3 como `generated/{id}/{file_name}` con SSE.
- Persiste `status`, `detail`, `typeFailed`, `updatedAt` y, si hay archivo,
  `generatedFileName`/`generatedFileS3Key`.
- No permite re-cerrar una solicitud ya terminal (Procesado/Failed) -> 409.
- Obtener el valor de la API key: output `ResultApiKeyId` del stack ->
  `aws apigateway get-api-key --api-key <id> --include-value`.

## Control de costo

- **S3 lifecycle** en `FilesBucket`: `uploads/` y `generated/` pasan a
  Standard-IA a los 90 dias y expiran a los 400 dias (retencion >= 12 meses).
  Multipart incompletos se abortan a 7 dias.
- **CloudWatch Logs**: retencion `LogRetentionInDays` (default 30) en los 6 log
  groups de Lambda.
- **DynamoDB PITR**: parametrizado (`EnablePitr`, default `false`). Activar en
  prod (`EnablePitr=true`).
- **API key Robot**: quota 10.000/dia + throttle 10 rps (tope duro).
- Costo estimado staging: ~1-3 USD/mes (dentro de free tier en gran parte).

## Comandos de despliegue

Directorio de trabajo: `infrastructure/`. Existe `samconfig.toml` con el
config-env `staging`.

```bash
# Build (requiere python3.14 en PATH o Docker para --use-container)
sam build

# Deploy staging (no interactivo). Los secretos vacios se omiten;
# preferir IntegrationsSecretArn.
sam deploy \
  --stack-name purdy-renting-staging \
  --region us-east-1 --resolve-s3 \
  --no-confirm-changeset --no-fail-on-empty-changeset \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    EnvironmentName=staging \
    EnablePitr=false \
    FrontendDomain='https://<cloudfront-domain>' \
    IntegrationsSecretArn='<arn-secreto>'
```

Notas del CLI:
- `sam deploy` con `--parameter-overrides` NO acepta un parametro con valor
  vacio en formato `Clave=`. Si hay que forzar vacios, omitir el parametro
  (usa el default) o usar el formato `ParameterKey=...,ParameterValue=`.
- Evitar `aws lambda update-function-configuration` manual: crea drift respecto
  a CloudFormation (el siguiente `sam deploy` lo revierte).

## Despliegue del frontend

```bash
cd frontend
# .env.production contiene VITE_API_BASE_URL, VITE_COGNITO_USER_POOL_ID,
# VITE_COGNITO_USER_POOL_CLIENT_ID, VITE_AWS_REGION.
npm install
npm run build
aws s3 sync dist/ s3://<SiteBucketName>/ --delete --region us-east-1
aws cloudfront create-invalidation --distribution-id <DistId> --paths "/*"
```

Tras el PRIMER deploy de infra (dominio CloudFront desconocido de antemano):
1. Desplegar infra con un `FrontendDomain` placeholder.
2. Tomar el output `CloudFrontDomain` y re-desplegar con
   `FrontendDomain=https://<dominio-cloudfront>` para que CORS quede correcto.
3. Construir y subir el SPA con las env vars de los outputs.

## Entorno staging actual (referencia)

- Region: **us-east-1**. Cuenta AWS: `816069124226`.
- Stack: `purdy-renting-staging`.
- Los IDs concretos (ApiBaseUrl, CloudFront, UserPoolId, buckets, etc.) se
  obtienen de los outputs del stack:

  ```bash
  aws cloudformation describe-stacks --stack-name purdy-renting-staging \
    --region us-east-1 --query "Stacks[0].Outputs" --output table
  ```

## Seguridad / pendientes

- El `client_secret` de UiPath se compartio en texto plano durante la
  configuracion; debe considerarse comprometido y **rotarse** en UiPath, luego
  actualizar el secreto en Secrets Manager (ver comando arriba).
- No versionar secretos. `.env` y variantes estan en `.gitignore`.
