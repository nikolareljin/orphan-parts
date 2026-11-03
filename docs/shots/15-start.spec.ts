import { expect, test } from './lib'

// Signing in and out: the header's door, the access-code dialog (the field blurred, a stand-in
// typed into it, never sent), the header once signed in, and Sign out, last, since it ends the
// session the other shots use.

test.describe.configure({ mode: 'serial' })

test.describe('signed out', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('the door and the access-code dialog', async ({ shots, page }) => {
    await page.goto('/')
    const door = page.getByRole('button', { name: 'Sign in with the code' })
    await expect(door).toBeVisible()
    await shots.take('01-signed-out')
    await door.click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByRole('form', { name: 'Access code' })).toBeVisible()
    await dialog.locator('input[type="password"]').fill('stand-in-not-a-code')
    await shots.take('02-sign-in-dialog')
  })
})

test('signed in, then Sign out', async ({ shots, page }) => {
  await page.goto('/')
  const out = page.getByRole('button', { name: 'Sign out' })
  await expect(out).toBeVisible()
  await shots.take('03-signed-in')
  await out.click()
  await expect(page.getByRole('button', { name: 'Sign in with the code' })).toBeVisible()
  await shots.take('04-signed-out-again')
})
