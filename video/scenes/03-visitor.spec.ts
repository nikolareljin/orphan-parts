import { expect, test } from './lib'

// The demo visitor: signed out on camera, Read a label is a gallery of the demo set's photos,
// and each reading is the one recorded for that photo. Last, since it ends the session.

test('S21 signed out, the sample gallery', async ({ scene }) => {
  const { page } = scene
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
  await scene.ready()
  await scene.click(page.getByRole('button', { name: 'Sign out' }), 900)
  await expect(page.getByRole('button', { name: 'Sign in with the code' })).toBeVisible()
  await scene.click(page.getByRole('button', { name: 'Read a label', exact: true }))
  const gpu = page.getByRole('group', { name: 'EVGA GeForce 9800 GT graphics card' })
  await expect(gpu).toBeVisible()
  await scene.click(gpu.getByRole('button', { name: 'Select all photos of this item' }), 400)
  // read whole, so the shot lands on the values rather than the regions
  await scene.click(page.getByLabel('Find the label in the photo first (SAM 3.1; helps with busy photos)'), 300)
  const read = page.getByRole('button', { name: 'Read the label' })
  await scene.click(read)
  const reading = page.getByRole('article', { name: /^Reading: EVGA GeForce 9800 GT graphics card/ })
  await expect(reading).toBeVisible({ timeout: 60_000 })
  scene.mark('read')
  await scene.settle(300)
  await scene.reveal(reading.getByRole('note'), 'start')
  await scene.point(reading.getByRole('note'))
  await scene.hold(900)
  await scene.scroll(320, 900)
  await scene.hold(1600)
})
