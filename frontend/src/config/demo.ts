// config/demo.ts
//
// Modos de ejecucion para vista previa/pruebas locales:
//
//  - IS_DEMO_MODE  (VITE_DEMO_MODE=true): TODO simulado en el navegador, sin
//    backend. Datos de ejemplo; no sube archivos ni dispara UiPath.
//
//  - IS_LOCAL_MODE (VITE_LOCAL_MODE=true): usa el BACKEND LOCAL real
//    (local-server) via VITE_API_BASE_URL. Omite el login de Cognito pero SI
//    llama al backend (sube archivos, crea solicitud, dispara UiPath real).
//
// En produccion (ninguna de las dos activa) el comportamiento real con Cognito
// se mantiene intacto.

export const IS_DEMO_MODE: boolean =
  import.meta.env.VITE_DEMO_MODE === 'true';

export const IS_LOCAL_MODE: boolean =
  import.meta.env.VITE_LOCAL_MODE === 'true';

/**
 * True cuando se debe omitir la autenticacion Cognito (demo o local).
 */
export const SKIP_AUTH: boolean = IS_DEMO_MODE || IS_LOCAL_MODE;

/** Usuario simulado mostrado en el encabezado durante demo/local. */
export const DEMO_USER = {
  username: 'local-user',
  signInDetails: { loginId: 'local@purdyrenting.local' },
} as const;