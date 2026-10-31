// The header's door: exactly one control on a gated server, a quiet note on an open one.
// What is known about access comes from GET /api/access alone, fetched apart from the
// service checks, so a slow or failed /readyz or /api/version never takes the door away.

export interface AccessState {
  gated: boolean
  granted: boolean
}

// null while the server has not answered yet (or every try so far has failed)
export type KnownAccess = AccessState | null

export type Door = 'sign-in' | 'sign-out' | 'open'

// Unknown reads as signed out: the way in is offered, and opening it checks again.
export function doorOf(access: KnownAccess): Door {
  if (access === null) return 'sign-in'
  if (!access.gated) return 'open'
  return access.granted ? 'sign-out' : 'sign-in'
}

// The demo door, for the pages: gated and known to be without a session.
export function isDemo(access: KnownAccess): boolean {
  return access !== null && access.gated && !access.granted
}

// Whether the upload inputs may show: only once the server has said so, signed in or open.
// Unknown (no answer yet, or every try failed) reads as the visitor: the samples and the
// sign-in line, never a file input the server would refuse.
export function uploadsAllowed(access: KnownAccess): boolean {
  return access !== null && (!access.gated || access.granted)
}

// What the tab knows right after the person acts, before the server is asked again.
export const SIGNED_IN: AccessState = { gated: true, granted: true }
export const SIGNED_OUT: AccessState = { gated: true, granted: false }

// The wait before the next try after `failures` failed status checks in a row: 1 s, 2 s,
// 4 s, ... up to 30 s, and then every 30 s for as long as the page is open.
export function retryDelayMs(failures: number): number {
  const n = Math.max(1, Math.floor(failures))
  return Math.min(30_000, 1000 * 2 ** (n - 1))
}
