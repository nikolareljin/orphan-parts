/** Whether an origin in a pairing code is one a phone on the network can call. On the phone,
 * localhost is the phone itself, so a page open at localhost must not hand that out. */
export function reachableFromAPhone(origin: string): boolean {
  let host: string
  try {
    host = new URL(origin).hostname.toLowerCase()
  } catch {
    return false
  }
  return !['localhost', '127.0.0.1', '::1', '[::1]', '0.0.0.0'].includes(host) && !host.endsWith('.localhost')
}
