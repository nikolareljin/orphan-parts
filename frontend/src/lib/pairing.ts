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
