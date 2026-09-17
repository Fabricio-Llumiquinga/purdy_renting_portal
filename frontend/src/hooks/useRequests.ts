// hooks/useRequests.ts
//
//  - Demo: datos de ejemplo (sin backend).
//  - Local/Produccion: llama al backend real via requestService.getRequests().

import { useCallback, useEffect, useState } from 'react';
import { getRequests } from '../services/requestService';
import type { Request } from '../types';
import { IS_DEMO_MODE } from '../config/demo';
import { DEMO_REQUESTS } from '../config/demoData';

const FALLBACK_ERROR_MESSAGE =
  'No se pudieron obtener las solicitudes. Por favor, intentelo de nuevo.';

export interface UseRequestsState {
  requests: Request[];
  loading: boolean;
  error: string | null;
}
export interface UseRequestsResult extends UseRequestsState {
  refresh: () => Promise<void>;
}

export function useRequests(): UseRequestsResult {
  const [requests, setRequests] = useState<Request[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    if (IS_DEMO_MODE) {
      setLoading(false);
      setError(null);
      setRequests(DEMO_REQUESTS);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await getRequests();
      setRequests(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : FALLBACK_ERROR_MESSAGE);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    if (IS_DEMO_MODE) {
      setRequests(DEMO_REQUESTS);
      setLoading(false);
      setError(null);
      return () => { active = false; };
    }
    setLoading(true);
    setError(null);
    getRequests()
      .then((data) => { if (active) setRequests(data); })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : FALLBACK_ERROR_MESSAGE);
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const refresh = useCallback((): Promise<void> => load(), [load]);
  return { requests, loading, error, refresh };
}

export default useRequests;