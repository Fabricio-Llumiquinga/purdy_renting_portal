// local-server/server.mjs
//
// Backend LOCAL ligero para probar el proyecto end-to-end sin AWS.
// Implementa las mismas rutas que la API real (API Gateway + Lambdas):
//   POST /requests/presigned-url  -> devuelve una "uploadUrl" local
//   PUT  /local-upload/:key       -> recibe el archivo (sustituye al PUT a S3)
//   POST /requests                -> crea la solicitud y DISPARA UiPath real
//   GET  /requests                -> lista solicitudes
//   GET  /requests/:id/download   -> devuelve la URL del archivo generado
//
// Persistencia: archivos en ./uploads y ./generated; solicitudes en db.json.
// NO usa Cognito (modo local sin auth). NO requiere dependencias externas.
//
// SEGURIDAD: el client_secret de UiPath se lee de variables de entorno; si no
// esta, se usa el valor de desarrollo. Rotar el secreto antes de produccion.

import http from 'node:http';
import https from 'node:https';
import { URL, URLSearchParams } from 'node:url';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const UPLOADS = path.join(__dirname, 'uploads');
const GENERATED = path.join(__dirname, 'generated');
const DB_FILE = path.join(__dirname, 'db.json');
const PORT = process.env.PORT || 3000;

// ---- UiPath config (mismos valores que el servicio backend) ----
const UIPATH = {
  tokenUrl: process.env.UIPATH_TOKEN_URL || 'https://cloud.uipath.com/identity_/connect/token',
  clientId: process.env.UIPATH_CLIENT_ID || '8f64dac1-9ba3-4e42-a0f3-ca11aaff7dc2',
  clientSecret: process.env.UIPATH_CLIENT_SECRET || '',
  scope: process.env.UIPATH_SCOPE || 'OR.Jobs OR.Execution OR.Folders',
  jobsUrl: process.env.UIPATH_JOBS_URL || 'https://cloud.uipath.com/grupopurdyrentingcommunity/DefaultTenant/orchestrator_/odata/Jobs/UiPath.Server.Configuration.OData.StartJobs',
  releaseKey: process.env.UIPATH_RELEASE_KEY || '94b379af-77fa-4320-b792-1682ef8171ac',
  orgUnitId: process.env.UIPATH_ORG_UNIT_ID || '8073429',
  // Si es "false", NO dispara el job real (util para probar el flujo sin ejecutar RPA).
  enabled: (process.env.UIPATH_ENABLED || 'true') !== 'false',
};

const VALID_COMPANIES = { 'Purdy Motor': 'PM', 'Automotriz': 'AUTO' };

// ---- Persistencia simple ----
function loadDb() {
  try { return JSON.parse(fs.readFileSync(DB_FILE, 'utf8')); }
  catch { return { requests: [] }; }
}
function saveDb(db) { fs.writeFileSync(DB_FILE, JSON.stringify(db, null, 2)); }

// ---- Helpers HTTP ----
function send(res, status, obj, extraHeaders = {}) {
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Api-Key',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,OPTIONS',
    ...extraHeaders,
  });
  res.end(body);
}
function sendErr(res, status, code, message) {
  send(res, status, { error: { code, message } });
}
function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

// ---- UiPath: autenticacion + start job ----
function httpsRequest(urlStr, options, bodyBuffer) {
  return new Promise((resolve, reject) => {
    const u = new URL(urlStr);
    const req = https.request(
      { hostname: u.hostname, path: u.pathname + u.search, method: options.method, headers: options.headers },
      (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString('utf8') }));
      }
    );
    req.on('error', reject);
    if (bodyBuffer) req.write(bodyBuffer);
    req.end();
  });
}

async function uipathAuthenticate() {
  const form = new URLSearchParams({
    grant_type: 'client_credentials',
    client_id: UIPATH.clientId,
    client_secret: UIPATH.clientSecret,
    scope: UIPATH.scope,
  }).toString();
  const resp = await httpsRequest(UIPATH.tokenUrl,
    { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': Buffer.byteLength(form) } },
    Buffer.from(form));
  if (resp.status < 200 || resp.status >= 300) {
    console.error('[UiPath] auth fallo HTTP', resp.status, resp.body.slice(0, 300));
    return null;
  }
  try { return JSON.parse(resp.body).access_token || null; } catch { return null; }
}

async function uipathStartJob(token, archivo1B64, archivo2B64) {
  const inputArguments = JSON.stringify({ in_Archivo1Base64: archivo1B64, in_Archivo2Base64: archivo2B64 });
  const body = JSON.stringify({
    startInfo: { ReleaseKey: UIPATH.releaseKey, Strategy: 'ModernJobsCount', JobsCount: 1, InputArguments: inputArguments },
  });
  const resp = await httpsRequest(UIPATH.jobsUrl,
    { method: 'POST', headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-UIPATH-OrganizationUnitId': UIPATH.orgUnitId,
        'Content-Length': Buffer.byteLength(body),
      } },
    Buffer.from(body));
  const ok = resp.status >= 200 && resp.status < 300;
  console.log(ok ? '[UiPath] job disparado OK (HTTP ' + resp.status + ')'
                 : '[UiPath] StartJobs fallo HTTP ' + resp.status + ' ' + resp.body.slice(0, 400));
  return ok;
}

async function triggerUiPath(listadoKey, daiKey, requestId) {
  if (!UIPATH.enabled) { console.log('[UiPath] deshabilitado (UIPATH_ENABLED=false); no se dispara job.'); return; }
  try {
    const f1 = fs.readFileSync(path.join(UPLOADS, listadoKey));
    const f2 = fs.readFileSync(path.join(UPLOADS, daiKey));
    const token = await uipathAuthenticate();
    if (!token) { console.error('[UiPath] sin token para request', requestId); return; }
    await uipathStartJob(token, f1.toString('base64'), f2.toString('base64'));
  } catch (e) {
    console.error('[UiPath] excepcion para request', requestId, e.message);
  }
}

// ---- Rutas ----
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const pathName = url.pathname;

  if (req.method === 'OPTIONS') { send(res, 204, {}); return; }

  try {
    // POST /requests/presigned-url
    if (req.method === 'POST' && pathName === '/requests/presigned-url') {
      const body = JSON.parse((await readBody(req)).toString('utf8') || '{}');
      const { fileName, fileType } = body;
      if (!fileName || !fileType) return sendErr(res, 400, 'MISSING_REQUIRED_FIELD', 'Falta fileName o fileType.');
      const key = `${fileType}_${Date.now()}_${crypto.randomBytes(4).toString('hex')}_${fileName}`;
      const uploadUrl = `http://localhost:${PORT}/local-upload/${encodeURIComponent(key)}`;
      return send(res, 200, { uploadUrl, s3Key: key });
    }

    // PUT /local-upload/:key  (sustituye el PUT directo a S3)
    if (req.method === 'PUT' && pathName.startsWith('/local-upload/')) {
      const key = decodeURIComponent(pathName.substring('/local-upload/'.length));
      const data = await readBody(req);
      fs.writeFileSync(path.join(UPLOADS, key), data);
      console.log('[upload] guardado', key, `(${data.length} bytes)`);
      return send(res, 200, { ok: true });
    }

    // POST /requests
    if (req.method === 'POST' && pathName === '/requests') {
      const body = JSON.parse((await readBody(req)).toString('utf8') || '{}');
      const { listadoPreciosS3Key, daiS3Key, company } = body;
      if (!listadoPreciosS3Key || !daiS3Key || !company)
        return sendErr(res, 400, 'MISSING_REQUIRED_FIELD', 'Faltan campos obligatorios.');
      const companyCode = VALID_COMPANIES[company];
      if (!companyCode) return sendErr(res, 400, 'INVALID_COMPANY', 'La empresa seleccionada no es valida.');

      const requestId = crypto.randomUUID();
      const now = new Date().toISOString();
      const db = loadDb();
      const record = {
        requestId, userEmail: 'local@purdyrenting.local', company, companyCode,
        listadoPreciosS3Key, daiS3Key,
        generatedFileName: null, generatedFileS3Key: null,
        status: 'Pendiente de Procesar', observation: null,
        createdAt: now, updatedAt: now,
      };
      db.requests.unshift(record);
      saveDb(db);
      console.log('[requests] creada', requestId, company);

      // Dispara UiPath (no bloqueante para la respuesta).
      triggerUiPath(listadoPreciosS3Key, daiS3Key, requestId);

      return send(res, 201, {
        requestId,
        message: `Su solicitud ha sido creada exitosamente. Numero de solicitud: ${requestId}. Estado: Pendiente de Procesar.`,
      });
    }

    // GET /requests
    if (req.method === 'GET' && pathName === '/requests') {
      const db = loadDb();
      return send(res, 200, db.requests);
    }

    // GET /requests/:id/download
    const dl = pathName.match(/^\/requests\/([^/]+)\/download$/);
    if (req.method === 'GET' && dl) {
      const db = loadDb();
      const r = db.requests.find((x) => x.requestId === dl[1]);
      if (!r) return sendErr(res, 404, 'REQUEST_NOT_FOUND', 'La solicitud indicada no existe.');
      if (!r.generatedFileS3Key) return sendErr(res, 404, 'REQUEST_NOT_FOUND', 'Aun no hay archivo generado.');
      return send(res, 200, { downloadUrl: '#local', fileName: r.generatedFileName || 'archivo.xlsx' });
    }

    return sendErr(res, 404, 'NOT_FOUND', 'Ruta no encontrada.');
  } catch (e) {
    console.error('[error]', e);
    return sendErr(res, 500, 'INTERNAL_ERROR', 'Error interno del servidor local.');
  }
});

server.listen(PORT, () => {
  console.log(`Backend LOCAL escuchando en http://localhost:${PORT}`);
  console.log(`UiPath: ${UIPATH.enabled ? 'HABILITADO (disparara job real)' : 'deshabilitado'}`);
});