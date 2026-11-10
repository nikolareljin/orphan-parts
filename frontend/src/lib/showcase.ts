// the first visit's welcome: a spare part from the demo set turning into what it was drawn as,
// four times over, once, with no click needed; it stays on the last drawing. Static files on the web host: no request to the
// backend and no model call. Shown once per browser; the close button puts it away at once.

export const SHOWCASE_SEEN = 'opl.showcase.seen'
export const PHASE_MS = 2800 // how long the part, then what it becomes, stays on screen

export interface Pair {
  name: string
  from: string
  to: string
}

export const PAIRS: Pair[] = [
  { name: 'joystick', from: 'A spare joystick module', to: 'an arcade coffee table' },
  { name: 'dht11', from: 'A DHT11 sensor', to: 'a kitchen climate dashboard' },
  { name: 'hc-sr04', from: 'An ultrasonic distance sensor', to: 'a garage parking helper' },
  { name: 'uno', from: 'A spare UNO board', to: 'a desk calendar and alarm' },
]

export const partSrc = (p: Pair) => `/showcase/${p.name}-part.webp`
export const builtSrc = (p: Pair) => `/showcase/${p.name}-built.webp`

type Reads = Pick<Storage, 'getItem'>
type Writes = Pick<Storage, 'setItem'>

export function local(): Storage | undefined {
  try {
    return window.localStorage
  } catch {
    return undefined // no window (rendered on the server) or storage blocked
  }
}

export function seen(storage: Reads | undefined): boolean {
  try {
    return storage?.getItem(SHOWCASE_SEEN) === '1'
  } catch {
    return false
  }
}

export function remember(storage: Writes | undefined): void {
  try {
    storage?.setItem(SHOWCASE_SEEN, '1')
  } catch {
    // a private window: it shows again next time, and closes the same way
  }
}

// step 2i is pair i's part, 2i + 1 what it becomes; one cycle, then it stays on the last
export const LAST_STEP = PAIRS.length * 2 - 1

export function stepAfter(step: number): number {
  return Math.min(step + 1, LAST_STEP)
}

// reduced motion asked for: no turning on its own, the first part shown as what it became
export function stillMotion(): boolean {
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}
