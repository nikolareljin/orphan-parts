import { expect, openItem, test } from './lib'

// Story A, the frappé maker: the worn agitator in the inventory, the app's question about the
// device it came from, the label under the mixer's base as the answer, the web search for the
// maker's part, its fit and the questions for the seller, and the decision to keep and fix it.
// The stage (video/generate.sh) loads the demo set with the agitator's device left unanswered.
// Shot names are the storyboard's (video/storyboard/main.md).

const AGITATOR = 'Frappé maker agitator, worn'
const PHOTOS = process.env.SCENES_PHOTOS ?? '/photos'

test.describe.configure({ mode: 'serial' })

test('S05 the app asks which device the part came from', async ({ scene }) => {
  const { page } = scene
  await page.goto('/')
  await scene.ready()
  const item = await openItem(scene, AGITATOR)
  const question = item.getByRole('region', { name: 'Which device it came from' })
  await expect(question).toContainText("We couldn't tell which device this part came from.")
  await scene.hold(600)
  await scene.point(item.getByRole('img', { name: 'Item photo 1' }))
  await scene.hold(900)
  await scene.point(question.getByText(/couldn't tell which device/))
  await scene.hold(2500)
})

test('S07 the label under the base answers it', async ({ scene }) => {
  const { page } = scene
  await page.goto('/#inventory')
  await scene.ready()
  const item = await openItem(scene, AGITATOR)
  const question = item.getByRole('region', { name: 'Which device it came from' })
  const input = question.getByLabel('Add a photo of the device')
  await scene.point(input)
  await scene.hold(400)
  await input.setInputFiles(`${PHOTOS}/hamilton-729-label.jpg`)
  scene.mark('sent')
  await expect(question).toHaveCount(0, { timeout: 90_000 })
  const came = item.locator('.came-from')
  await expect(came).toContainText('Came from:')
  scene.mark('answered')
  await scene.settle(300)
  await scene.point(came)
  await scene.hold(1500)
  await scene.point(item.getByRole('img', { name: 'Device photo 1' }))
  await scene.hold(1800)
})

test('S08 Search the web brings back the maker part, then its fit', async ({ scene }) => {
  const { page } = scene
  await page.goto('/')
  await scene.ready()
  await scene.click(page.getByRole('button', { name: 'Find a part', exact: true }))
  await scene.click(page.getByRole('table', { name: 'Searches' }).getByRole('row', { name: /all-metal agitator rod/ }).getByRole('button', { name: 'Open' }))
  const panel = page.getByRole('article', { name: /^Search all-metal agitator rod/ })
  const plan = panel.getByRole('region', { name: 'Plan the search' })
  await scene.click(plan.getByRole('button', { name: 'Search the web' }))
  await expect(plan).toContainText(/Added \d+ pages? to the listings/, { timeout: 120_000 })
  scene.mark('found')
  await scene.settle(300)
  const web = panel
    .getByRole('list', { name: 'Listings brought back, ranked' })
    .getByRole('listitem')
    .filter({ hasText: 'found on the web' })
    .first()
  await scene.reveal(web, 'start')
  await scene.point(web.locator('.source-link'))
  await scene.hold(1600)
  await scene.click(web.getByRole('button', { name: 'Check fit' }))
  const fit = web.getByLabel(/^Fit of listing/)
  await expect(fit).toBeVisible({ timeout: 120_000 })
  scene.mark('fit')
  await scene.settle(300)
  await scene.reveal(fit)
  await scene.point(fit.locator('.badge').first())
  await scene.hold(1200)
  const questions = fit.locator('ul.questions')
  if (await questions.count()) await scene.point(questions.first())
  await scene.hold(2600)
})

test('S09 Decide: keep and fix', async ({ scene }) => {
  const { page } = scene
  await page.goto('/#inventory')
  await scene.ready()
  const item = await openItem(scene, AGITATOR)
  const decide = item.getByRole('region', { name: 'Decide' })
  await scene.click(item.getByRole('navigation', { name: 'Sections' }).getByRole('button', { name: 'Decide', exact: true }), 1000)
  await scene.click(decide.getByRole('button', { name: 'What should I do with it?' }))
  const cards = decide.getByRole('region', { name: 'What to do with it' })
  const fix = cards.getByRole('article', { name: 'Keep and fix' })
  await expect(fix).toBeVisible({ timeout: 120_000 })
  scene.mark('cards')
  await scene.settle(300)
  await scene.reveal(fix, 'start')
  await scene.point(fix.getByRole('list', { name: 'Steps' }))
  await scene.hold(1500)
  await scene.click(fix.getByRole('button', { name: 'Choose this: Keep and fix' }))
  await expect(decide.getByRole('status', { name: 'Decision made' })).toContainText('Keep and fix')
  await scene.hold(1500)
})
