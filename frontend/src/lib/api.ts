// All calls to the backend go through here. In dev, Vite proxies these paths to :8000;
// in production the frontend and the API share an origin behind nginx.

export interface Readiness {
  status: 'ok' | 'degraded'
  model_api: 'live' | 'fixture' | 'record'
  data_dir_writable: boolean
  spend_usd: number
  spend_cap_usd: number
  paused: boolean
}

export interface Version {
  name: string
  version: string
  models: Record<string, string>
}

export const apiBase = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export function apiUrl(path: string): string {
  return `${apiBase}${path.startsWith('/') ? path : `/${path}`}`
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(apiUrl(path), { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
  return (await res.json()) as T
}

export const api = {
  readiness: () => getJson<Readiness>('/readyz'),
  version: () => getJson<Version>('/api/version'),
}
