import { expect, test, type Page } from '@playwright/test'
import { SIGNED_OUT } from '../global-setup'

// The header's door: on a gated server there is always exactly one of Sign in with the code
// and Sign out, whatever else on the page is slow or failing, and on any width.
const code = process.env.E2E_ACCESS_CODE ?? ''

const header = (page: Page) => page.locator('header.top')
const nav = (page: Page) => page.getByRole('navigation', { name: 'Pages' })
const signInLink = (page: Page) => header(page).getByRole('button', { name: 'Sign in with the code' })
const signOutLink = (page: Page) => header(page).getByRole('button', { name: 'Sign out' })

test.describe('signed out', () => {
  test.use({ storageState: SIGNED_OUT })

  test('the header offers Sign in, then Sign out once in, then Sign in again', async ({ page }) => {
    test.skip(!code, 'the stack runs without a gate')
    await page.goto('/')
    await expect(signInLink(page)).toBeVisible()
    await expect(signOutLink(page)).toHaveCount(0)

    await signInLink(page).click()
    const gate = page.getByRole('form', { name: 'Access code' })
    // the dialog says what signing in is for now
    await expect(gate.getByText('For now, signing in uses an access code only. Proper accounts come later.')).toBeVisible()
    await gate.getByLabel('Access code').fill(code)
    await gate.getByRole('button', { name: 'Enter' }).click()
    await expect(signOutLink(page)).toBeVisible()
    await expect(signInLink(page)).toHaveCount(0)

    await signOutLink(page).click()
    await expect(signInLink(page)).toBeVisible()
    await expect(signOutLink(page)).toHaveCount(0)
  })

  test('with /readyz and /api/version failing the way in is still there', async ({ page }) => {
    test.skip(!code, 'the stack runs without a gate')
    await page.route('**/readyz', (route) => route.abort())
    await page.route('**/api/version', (route) => route.abort())
    await page.goto('/')
    await expect(page.getByText(/Cannot reach the server/)).toBeVisible()
    await expect(signInLink(page)).toBeVisible()
  })
})

test('signed in, Sign out stays with /readyz and /api/version failing', async ({ page }) => {
  test.skip(!code, 'the stack runs without a gate')
  await page.route('**/readyz', (route) => route.abort())
  await page.route('**/api/version', (route) => route.abort())
  await page.goto('/')
  await expect(page.getByText(/Cannot reach the server/)).toBeVisible()
  await expect(signOutLink(page)).toBeVisible()
  await expect(signInLink(page)).toHaveCount(0)
})

test('a failed access check is tried again until it answers', async ({ page }) => {
  test.skip(!code, 'the stack runs without a gate')
  let refused = 0
  await page.route('**/api/access', async (route) => {
    if (route.request().method() === 'GET' && refused < 2) {
      refused += 1
      await route.abort()
      return
    }
    await route.continue()
  })
  await page.goto('/')
  // unknown reads as signed out; the retry then finds the session
  await expect(signInLink(page)).toBeVisible()
  await expect(signOutLink(page)).toBeVisible({ timeout: 15_000 })
  expect(refused).toBe(2)
})

test('a session refused mid-visit brings Sign in back', async ({ page }) => {
  test.skip(!code, 'the stack runs without a gate')
  await page.goto('/')
  await expect(signOutLink(page)).toBeVisible()
  await page.route('**/api/items**', (route) =>
    route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'session expired' }) }),
  )
  await nav(page).getByRole('button', { name: 'My inventory' }).click()
  await expect(signInLink(page)).toBeVisible()
  await expect(signOutLink(page)).toHaveCount(0)
})

test('on a phone-width window the door is on screen', async ({ page }) => {
  test.skip(!code, 'the stack runs without a gate')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(signOutLink(page)).toBeInViewport()
  const box = await signOutLink(page).boundingBox()
  expect(box).not.toBeNull()
  expect(box!.x + box!.width).toBeLessThanOrEqual(390)
  // and no sideways scroll hides it
  const wide = await page.evaluate(() => document.documentElement.scrollWidth)
  expect(wide).toBeLessThanOrEqual(390)

  await page.context().clearCookies()
  await page.reload()
  await expect(signInLink(page)).toBeInViewport()
})

test('a server without a code says so in the header instead of a door', async ({ page }) => {
  // the backend answers {gated: false, granted: true} when no access code is set
  await page.route('**/api/access', (route) =>
    route.request().method() === 'GET'
      ? route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ gated: false, granted: true, live: false, token: '', expires_at: 0 }),
        })
      : route.continue(),
  )
  await page.goto('/')
  await expect(header(page).getByText('Open server (no code needed)')).toBeVisible()
  await expect(signInLink(page)).toHaveCount(0)
  await expect(signOutLink(page)).toHaveCount(0)
})

test('the footer links to the documentation and the source', async ({ page }) => {
  await page.goto('/')
  const footer = page.getByRole('contentinfo', { name: 'Service' })
  await expect(footer.getByRole('link', { name: 'Documentation' })).toHaveAttribute(
    'href',
    'https://nikolareljin.github.io/orphan-parts/',
  )
  await expect(footer.getByRole('link', { name: 'Source on GitHub' })).toHaveAttribute(
    'href',
    'https://github.com/nikolareljin/orphan-parts',
  )
})

test('the footer separates installing the phone app from pairing it', async ({ page }) => {
  await page.goto('/')
  const footer = page.getByRole('contentinfo', { name: 'Service' })
  const phone = footer.locator('details.pair')
  await phone.getByText('Phone app: install and pair').click()
  await expect(phone.getByRole('heading', { name: '1. Install the app on the phone' })).toBeVisible()
  const qr = phone.getByRole('img', { name: "QR code that opens the newest release's APK" })
  await expect(qr).toHaveAttribute('src', '/apk-qr.svg')
  await expect(phone.getByText("Scan with the phone's camera to download the app")).toBeVisible()
  await expect(phone.getByRole('link', { name: 'orphan-parts.apk' })).toHaveAttribute(
    'href',
    'https://github.com/nikolareljin/orphan-parts/releases/latest/download/orphan-parts.apk',
  )
  await expect(phone.getByRole('link', { name: 'Put the app on the phone' })).toHaveAttribute(
    'href',
    'https://nikolareljin.github.io/orphan-parts/start/local/#7-put-the-app-on-the-phone',
  )
  const file = await page.request.get('/apk-qr.svg')
  expect(file.status()).toBe(200)
  expect(file.headers()['content-type']).toContain('image/svg+xml')
  await expect(phone.getByRole('heading', { name: '2. Connect it to this web app' })).toBeVisible()
  await expect(phone.getByText('Scan to pair', { exact: true }).first()).toBeVisible()
  // the marks beside the steps are decoration: the headings carry the meaning
  await expect(phone.locator('svg.step-icon')).toHaveCount(2)
  for (const icon of await phone.locator('svg.step-icon').all()) await expect(icon).toHaveAttribute('aria-hidden', 'true')
})
