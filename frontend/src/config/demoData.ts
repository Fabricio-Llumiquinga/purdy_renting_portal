// config/demoData.ts
//
// Datos de ejemplo usados unicamente en modo demo para poblar la tabla de
// seguimiento sin necesidad de un backend desplegado.

import type { Request } from '../types';

function isoDaysAgo(days: number, hours = 0): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  d.setHours(d.getHours() - hours);
  return d.toISOString();
}

export const DEMO_REQUESTS: Request[] = [
  {
    requestId: 'demo-0001',
    userEmail: 'demo@purdyrenting.local',
    company: 'Purdy Motor',
    companyCode: 'PM',
    listadoPreciosS3Key: 'uploads/demo-0001/listado_precios_precios.xlsx',
    daiS3Key: 'uploads/demo-0001/dai_dai.xlsx',
    generatedFileName: 'Listado_Precios_PM_2024.xlsx',
    generatedFileS3Key: 'generated/demo-0001/Listado_Precios_PM_2024.xlsx',
    status: 'Procesado',
    observation: null,
    detail: 'Ejecucion exitosa',
    typeFailed: '',
    createdAt: isoDaysAgo(2, 3),
    updatedAt: isoDaysAgo(2, 1),
  },
  {
    requestId: 'demo-0002',
    userEmail: 'demo@purdyrenting.local',
    company: 'Automotriz',
    companyCode: 'AUTO',
    listadoPreciosS3Key: 'uploads/demo-0002/listado_precios_precios.csv',
    daiS3Key: 'uploads/demo-0002/dai_dai.csv',
    generatedFileName: null,
    generatedFileS3Key: null,
    status: 'Procesando',
    observation: null,
    detail: null,
    typeFailed: null,
    createdAt: isoDaysAgo(1, 5),
    updatedAt: isoDaysAgo(1, 4),
  },
  {
    requestId: 'demo-0003',
    userEmail: 'demo@purdyrenting.local',
    company: 'Purdy Motor',
    companyCode: 'PM',
    listadoPreciosS3Key: 'uploads/demo-0003/listado_precios_precios.xls',
    daiS3Key: 'uploads/demo-0003/dai_dai.xls',
    generatedFileName: null,
    generatedFileS3Key: null,
    status: 'Pendiente de Procesar',
    observation: null,
    detail: null,
    typeFailed: null,
    createdAt: isoDaysAgo(0, 2),
    updatedAt: isoDaysAgo(0, 2),
  },
  {
    requestId: 'demo-0004',
    userEmail: 'demo@purdyrenting.local',
    company: 'Automotriz',
    companyCode: 'AUTO',
    listadoPreciosS3Key: 'uploads/demo-0004/listado_precios_precios.xlsx',
    daiS3Key: 'uploads/demo-0004/dai_dai.xlsx',
    generatedFileName: null,
    generatedFileS3Key: null,
    status: 'Failed',
    observation: 'El archivo DAI no contiene las columnas esperadas.',
    detail: 'Ejecucion fallo por selectores',
    typeFailed: 'IT Exception',
    createdAt: isoDaysAgo(3, 6),
    updatedAt: isoDaysAgo(3, 5),
  },
];