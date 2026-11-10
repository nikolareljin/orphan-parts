import { expect, test } from '@playwright/test'
import { SIGNED_OUT } from '../global-setup'

// a browser that has never opened the web app: no session, nothing remembered
test.use({ storageState: { cookies: [], origins: [] } })

const PHASE_MS = 2800 // frontend/src/lib/showcase.ts

test('the first visit plays the showcase once on its own; × puts it away and a reload does not bring it back', async ({ page }) => {
  await page.clock.install({ time: 0 })
  await page.clock.pauseAt(1000)
  await page.goto('/')
  const showcase = page.getByRole('region', { name: 'What a spare part can become' })
  await expect(showcase).toBeVisible()
  await expect(showcase.getByRole('heading', { name: 'Every spare part has a second life' })).toBeVisible()
  await expect(showcase.getByText('A spare joystick module')).toBeVisible()
  // no click: the part turns into what it was drawn as, then the next part comes
  await page.clock.runFor(PHASE_MS)
  await expect(showcase.locator('.showcase-pair.is-current.is-built')).toHaveCount(1)
  const arrow = showcase.locator('.showcase-arrow')
  await expect(arrow).toHaveAttribute('aria-hidden', 'false')
  await expect(arrow).toContainText('an arcade coffee table')
  await page.clock.runFor(PHASE_MS)
  await expect(showcase.getByText('A DHT11 sensor')).toBeVisible()
  await expect(arrow).toHaveAttribute('aria-hidden', 'true') // what it becomes is not said yet
  // the pair before stays as drawn under the one fading in
  await expect(showcase.locator('.showcase-pair.is-before.is-built')).toHaveCount(1)
  // one cycle, a phase at a time (each next timer is set once React has drawn the step):
  // the part, then what it becomes, for the last two pairs
  for (let step = 3; step <= 7; step++) {
    await page.clock.runFor(PHASE_MS)
    await expect(arrow).toHaveAttribute('aria-hidden', step % 2 ? 'false' : 'true')
  }
  // then it stays on the last drawing
  await page.clock.runFor(PHASE_MS * 4)
  await expect(showcase.getByText('A spare UNO board')).toBeVisible()
  await expect(arrow).toHaveAttribute('aria-hidden', 'false')
  await expect(arrow).toContainText('a desk calendar and alarm')
  // the images come from the web host, not the backend
  const paths = await showcase.locator('img').evaluateAll((imgs) => imgs.map((i) => new URL((i as HTMLImageElement).src).pathname))
  expect(paths.length).toBeGreaterThan(0)
  for (const path of paths) expect(path).toMatch(/^\/showcase\/[a-z0-9-]+-(part|built)\.webp$/)

  await showcase.getByRole('button', { name: 'Close the welcome' }).click()
  await expect(showcase).toHaveCount(0)
  // the keyboard goes on from the page that is open
  await expect(page.getByRole('button', { name: 'Read a label' })).toBeFocused()
  await page.reload()
  await expect(page.getByRole('button', { name: 'My inventory' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'What a spare part can become' })).toHaveCount(0)
})

test('the showcase is shown once: a second visit without closing it does not show it again', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('region', { name: 'What a spare part can become' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: 'My inventory' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'What a spare part can become' })).toHaveCount(0)
})

test('with reduced motion asked for, the showcase stands still on the first part and what it became', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.clock.install({ time: 0 })
  await page.clock.pauseAt(1000)
  await page.goto('/')
  const showcase = page.getByRole('region', { name: 'What a spare part can become' })
  await expect(showcase.locator('.showcase-arrow')).toHaveAttribute('aria-hidden', 'false')
  await expect(showcase.locator('.showcase-arrow')).toContainText('an arcade coffee table')
  await page.clock.runFor(PHASE_MS * 4)
  await expect(showcase.getByText('A spare joystick module')).toBeVisible()
  await expect(showcase.getByText('A DHT11 sensor')).toHaveCount(0)
})

test('< and > step through the parts by hand, wrapping round, and each goes on from there', async ({ page }) => {
  await page.clock.install({ time: 0 })
  await page.clock.pauseAt(1000)
  await page.goto('/')
  const showcase = page.getByRole('region', { name: 'What a spare part can become' })
  const caption = showcase.locator('.showcase-caption strong')
  await expect(caption).toHaveText('A spare joystick module')
  await showcase.getByRole('button', { name: 'Next part' }).click()
  await expect(caption).toHaveText('A DHT11 sensor')
  // from the part chosen, it goes on by itself to what it became
  await page.clock.runFor(PHASE_MS)
  await expect(showcase.locator('.showcase-arrow')).toHaveAttribute('aria-hidden', 'false')
  await showcase.getByRole('button', { name: 'Previous part' }).click()
  await expect(caption).toHaveText('A spare joystick module')
  await showcase.getByRole('button', { name: 'Previous part' }).click()
  await expect(caption).toHaveText('A spare UNO board') // round to the last
  await showcase.getByRole('button', { name: 'Next part' }).click()
  await expect(caption).toHaveText('A spare joystick module') // and round to the first
})

test.describe('seen before', () => {
  test.use({ storageState: SIGNED_OUT })

  test('#welcome plays it again, and the footer link does the same', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('button', { name: 'My inventory' })).toBeVisible()
    const showcase = page.getByRole('region', { name: 'What a spare part can become' })
    await expect(showcase).toHaveCount(0)
    await page.getByRole('link', { name: 'Play the welcome' }).click()
    await expect(showcase).toBeVisible()
    await expect(showcase.locator('.showcase-caption strong')).toHaveText('A spare joystick module')
    await showcase.getByRole('button', { name: 'Close the welcome' }).click()
    await expect(showcase).toHaveCount(0)
    expect(new URL(page.url()).hash).toBe('') // closed: the link works again
    await page.getByRole('link', { name: 'Play the welcome' }).click()
    await expect(showcase).toBeVisible()
    // and opened at the address itself, as a shared link is
    await page.goto('/')
    await page.goto('/#welcome')
    await page.reload()
    await expect(showcase).toBeVisible()
  })
})

test('a part opens its item in the demo', async ({ page, playwright, baseURL }) => {
  const code = process.env.E2E_ACCESS_CODE ?? ''
  test.skip(!code, 'the stack runs without a gate')
  // the owner puts the joystick module on the public shelf, as the demo set does
  const owner = await playwright.request.newContext({ baseURL })
  expect((await owner.post('/api/access', { data: { code } })).ok()).toBe(true)
  const listed = (await (await owner.get('/api/items')).json()) as { id: number; name: string }[]
  let id = listed.find((i) => i.name === 'Joystick module')?.id
  if (id === undefined) {
    const made = await owner.post('/api/items', { data: { name: 'Joystick module', item_type: 'joystick module' } })
    expect(made.status()).toBe(201)
    id = ((await made.json()) as { id: number }).id
  }
  expect((await owner.post(`/api/items/${id}/public`, { data: { public: true } })).ok()).toBe(true)
  await owner.dispose()

  await page.goto('/')
  const showcase = page.getByRole('region', { name: 'What a spare part can become' })
  await showcase.getByRole('button', { name: 'See the Joystick module in the demo' }).click()
  await expect(page.getByRole('button', { name: 'My inventory' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('article', { name: 'Item Joystick module' })).toBeVisible()
})
