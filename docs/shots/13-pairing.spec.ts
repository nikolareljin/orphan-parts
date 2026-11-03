import { expect, LAN_URL, Shots, test } from './lib'

// Pair the phone, in the footer: opened on the computer's address on the network (the stack's
// private address stands in for it), signed in and signed out, and opened on localhost, which
// a phone cannot reach. The pairing code is blurred in every shot (lib.ts).

test('the footer and Pair the phone', async ({ shots, page, browser }) => {
  await page.goto(`${LAN_URL}/`)
  const footer = page.getByRole('contentinfo', { name: 'Service' })
  await expect(footer).toContainText('recorded answers only')
  await shots.show(footer, 'end')
  await shots.take('01-footer')
  await footer.getByText('Pair the phone').click()
  await expect(footer.getByRole('img', { name: 'Pairing code for the phone' })).toBeVisible()
  await shots.show(footer, 'end')
  await shots.take('02-pair-signed-in')

  const visitor = await browser.newContext({ storageState: { cookies: [], origins: [] }, viewport: { width: 1280, height: 800 }, colorScheme: 'light' })
  const out = await visitor.newPage()
  await out.goto(`${LAN_URL}/`)
  const vfooter = out.getByRole('contentinfo', { name: 'Service' })
  await vfooter.getByText('Pair the phone').click()
  await expect(vfooter.getByRole('img', { name: 'Pairing code for the phone' })).toBeVisible()
  const other = new Shots(out, shots.guide)
  await other.show(vfooter, 'end')
  await other.take('03-pair-signed-out')
  await visitor.close()

  await page.goto('/')
  await footer.getByText('Pair the phone').click()
  await expect(footer).toContainText('which the phone cannot reach')
  await shots.show(footer, 'end')
  await shots.take('04-pair-localhost')
})
