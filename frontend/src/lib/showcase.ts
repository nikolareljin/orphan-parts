// the first visit's welcome: a spare part from the demo set turning into what it was drawn as,
// four times over, once, with no click needed; it stays on the last drawing. < and > step through
// the parts by hand, and each part opens its item in the demo. Static files on the web host: no
// request to the backend and no model call. Shown once per browser, and again whenever the page
// is opened at #welcome; the close button puts it away at once.

export const SHOWCASE_SEEN = 'opl.showcase.seen'
export const PHASE_MS = 2800 // how long the part, then what it becomes, stays on screen

export interface Pair {
  name: string
  from: string
  to: string
  item: string // the item's name in the demo set (demo/set.yaml): ids differ between hosts
}

export const PAIRS: Pair[] = [
  { name: 'joystick', from: 'A spare joystick module', to: 'an arcade coffee table', item: 'Joystick module' },
  { name: 'dht11', from: 'A DHT11 sensor', to: 'a kitchen climate dashboard', item: 'DHT11 temperature and humidity module' },
  { name: 'hc-sr04', from: 'An ultrasonic distance sensor', to: 'a garage parking helper', item: 'HC-SR04 ultrasonic distance module' },
  { name: 'uno', from: 'A spare UNO board', to: 'a desk calendar and alarm', item: 'Elegoo UNO R3 board' },
]

// the address that plays the welcome again, whatever this browser remembers: a link to share
export const WELCOME_HASH = '#welcome'

export function askedFor(hash: string): boolean {
  return hash === WELCOME_HASH
}

// the step that shows pair i (wrapping round): its part, to be drawn on its own; with reduced
// motion, what it became at once
export function pairStep(pair: number, still: boolean): number {
  const i = ((pair % PAIRS.length) + PAIRS.length) % PAIRS.length
  return 2 * i + (still ? 1 : 0)
}

// the demo item a pair shows, by its name; null when this host has no such item
export function itemNamed(items: { id: number; name: string }[], name: string): number | null {
  const wanted = name.trim().toLowerCase()
  return items.find((i) => i.name.trim().toLowerCase() === wanted)?.id ?? null
}

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
