import { expect, openItem, PHOTOS, test } from './lib'

// My inventory, first part: a part with no device asks which device it came from, and a photo
// of the label under the device's base answers it. The first specs run in the order the demo
// video's scenes do, so each request is the one recorded for the video and replays as such.

const AGITATOR = 'Frappé maker agitator, worn'

test.describe.configure({ mode: 'serial' })

test('the app asks which device the part came from', async ({ shots, page }) => {
  const item = await openItem(page, AGITATOR)
  const question = item.getByRole('region', { name: 'Which device it came from' })
  await expect(question).toContainText("We couldn't tell which device this part came from.")
  await shots.take('10-device-question')
})

test('a photo of the label under the base answers it', async ({ shots, page }) => {
  const item = await openItem(page, AGITATOR)
  const question = item.getByRole('region', { name: 'Which device it came from' })
  await question.getByLabel('Add a photo of the device').setInputFiles(`${PHOTOS}/hamilton-729-label.jpg`)
  await expect(question).toHaveCount(0, { timeout: 90_000 })
  await expect(item.locator('.came-from')).toContainText('Came from:')
  await shots.show(item.locator('.came-from'), 'center')
  await shots.take('11-device-answered')
})
