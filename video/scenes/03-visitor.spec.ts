import { expect, test } from './lib'

// The demo visitor: signed out on camera, Read a label is a gallery of the demo set's photos,
// and each reading is the one recorded for that photo, SAM 3.1's regions with it. Last, since
// it ends the session.

test('S21 signed out, the sample gallery', async ({ scene }) => {
  const { page } = scene
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
  await scene.ready()
  await scene.click(page.getByRole('button', { name: 'Sign out' }), 900)
  await expect(page.getByRole('button', { name: 'Sign in with the code' })).toBeVisible()
  await scene.click(page.getByRole('button', { name: 'Read a label', exact: true }))
  // the Sun monitor's label photo, the one sample where SAM 3.1 finds a label: the region over
  // the photo, the label crop, then what Muse Spark read off it
  const sun = page.getByRole('group', { name: 'Sun flat panel monitor' })
  await expect(sun).toBeVisible()
  await scene.click(sun.getByRole('checkbox').first(), 400)
  const sam = page.getByLabel('Find the label in the photo first (SAM 3.1; helps with busy photos)')
  if (!(await sam.isChecked())) await scene.click(sam, 300)
  await scene.point(sam)
  await scene.hold(500)
  const read = page.getByRole('button', { name: 'Read the label' })
  await scene.click(read)
  const reading = page.getByRole('article', { name: /^Reading: Sun flat panel monitor/ })
  await expect(reading).toBeVisible({ timeout: 60_000 })
  scene.mark('read')
  await scene.settle(300)
  const overlay = reading.getByRole('img', { name: 'Photo with the found regions drawn over it' })
  await scene.reveal(overlay, 'start')
  await scene.point(overlay)
  await scene.hold(1800)
  const regions = reading.getByRole('list', { name: 'Regions' })
  if (await regions.count()) {
    await scene.point(regions)
    await scene.hold(1200)
  }
  await scene.reveal(reading.getByRole('note'), 'start')
  await scene.point(reading.getByRole('note'))
  await scene.hold(900)
  await scene.scroll(320, 900)
  await scene.hold(1400)
})
