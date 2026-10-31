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
  if (!gated) return 'It carries this address.'
  if (!signedIn) {
    return 'It carries this address alone: the phone joins as the demo. Sign in here first to give it a code of its own.'
  }
  return (
    'It carries this address and a pairing good for a few minutes; with it the phone claims an access code of its own, ' +
    'which ends with the code you signed in with, or sooner when revoked on the server. That code stays here.'
  )
}
