/** Whether an origin in a pairing code is one a phone on the network can call. On the phone,
 * localhost is the phone itself, so a page open at localhost must not hand that out: the
 * whole loopback range, the unspecified address and the .localhost names. A relative API
 * base means the page's own origin. */
export function reachableFromAPhone(origin: string): boolean {
  let host: string
  try {
    const page = typeof window !== 'undefined' ? window.location.origin : undefined
    host = new URL(origin, page).hostname.toLowerCase()
  } catch {
    return false
  }
  return (
    host !== '' &&
    !['localhost', '::1', '[::1]', '0.0.0.0', '[::]', '[::ffff:7f00:1]'].includes(host) &&
    !host.startsWith('127.') &&
    !host.startsWith('[::ffff:127.') &&
    !host.endsWith('.localhost')
  )
}

/** What the pairing code under the footer carries, as the line under it says: the address
 * alone without a gate; with one, a pairing that claims the phone's own code for a caller
 * through the door, or the address alone for the demo visitor, whose phone is the demo too. */
export function pairingText(gated: boolean, signedIn: boolean): string {
  if (!gated) return "It contains this server's address."
  if (!signedIn) {
    return "It contains only this server's address, so the phone opens the demo. Sign in here first to sign the phone in too."
  }
  return (
    "It contains this server's address and a sign-in that lasts a few minutes. With it the phone gets its own access code, " +
    'which ends when yours does, or sooner if revoked on the server; your own code is never given to the phone. ' +
    'Until the sign-in expires, anyone who scans it is signed in, so keep it off projectors and out of recordings.'
  )
}

/** How long the footer's pairing code stays before it is drawn again: a minute before the
 * pairing in it ends (never sooner than 15 s), or 10 minutes when the code says no end. The
 * seconds left by the server's clock come first, so a page whose clock is off redraws in time;
 * the end in Unix seconds, read against the page's clock, only when those are not said. */
export function redrawAfterMs(expiresAt: number, nowMs: number, expiresIn: number | null = null): number {
  if (expiresIn !== null && expiresIn >= 0) return Math.max(15_000, expiresIn * 1000 - 60_000)
  if (!expiresAt) return 10 * 60_000
  return Math.max(15_000, expiresAt * 1000 - nowMs - 60_000)
}
