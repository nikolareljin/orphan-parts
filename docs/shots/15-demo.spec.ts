import { expect, openItem, test } from './lib'

// The demo visitor, with no code: Read a label is a gallery of the demo set's photos, each
// reading the one recorded for it; the inventory is the demo set's, read-only, and so are Find
// a part, Build and reuse and Profile (each skipped on a version that shows the visitor only
// the sign-in line there).

test.use({ storageState: { cookies: [], origins: [] } })

test('the visitor reads a sample', async ({ shots, page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Sign in with the code' })).toBeVisible()
  await shots.take('01-visitor-home')
  const gpu = page.getByRole('group', { name: 'EVGA GeForce 9800 GT graphics card' })
  await gpu.getByRole('button', { name: 'Select all photos of this item' }).click()
  await page.getByLabel('Find the label in the photo first (SAM 3.1; helps with busy photos)').uncheck()
  await shots.show(gpu, 'center')
  await shots.take('02-samples-picked')
  await page.getByRole('button', { name: 'Read the label' }).click()
  const reading = page.getByRole('article', { name: /^Reading: EVGA GeForce 9800 GT graphics card/ })
  await expect(reading).toBeVisible({ timeout: 60_000 })
  await shots.show(reading)
  await shots.take('03-sample-reading')
})
test('the visitor opens an item', async ({ shots, page }) => {
  await openItem(page, 'Frappé maker agitator, worn')
  await shots.take('04-visitor-item')
})

test('the visitor on Find a part', async ({ shots, page }) => {
  await page.goto('/#find')
  const table = page.getByRole('table', { name: 'Searches' })
  await table.waitFor({ state: 'visible', timeout: 10_000 }).catch(() => undefined)
  test.skip(!(await table.isVisible()), 'Find a part shows the visitor no searches on this version')
  await shots.take('05-visitor-find')
  await table.getByRole('row', { name: /all-metal agitator rod/ }).getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: /^Search all-metal agitator rod/ })
  await expect(panel).toBeVisible()
  const web = panel.getByRole('list', { name: 'Listings brought back, ranked' }).getByRole('listitem').filter({ hasText: 'found on the web' }).first()
  if (await web.count()) await shots.show(web)
  else await shots.show(panel.getByRole('table', { name: 'Candidates' }))
  await shots.take('08-visitor-search')
})

test('the visitor on Build and reuse', async ({ shots, page }) => {
  await page.goto('/#build')
  const table = page.getByRole('table', { name: 'Projects' })
  await table.waitFor({ state: 'visible', timeout: 10_000 }).catch(() => undefined)
  test.skip(!(await table.isVisible()), 'Build and reuse shows the visitor no projects on this version')
  await shots.take('06-visitor-build')
  await table.getByRole('row').filter({ hasText: /homework/i }).first().getByRole('button', { name: 'Open' }).click()
  await expect(page.getByRole('article', { name: /^Project / })).toBeVisible()
  await shots.take('09-visitor-project')
})

test('the visitor on Profile', async ({ shots, page }) => {
  await page.goto('/#profile')
  const skills = page.getByRole('table', { name: 'Skills' })
  await skills.waitFor({ state: 'visible', timeout: 10_000 }).catch(() => undefined)
  test.skip(!(await skills.isVisible()), 'Profile shows the visitor no skills on this version')
  await shots.take('07-visitor-profile')
})

test('the visitor reads the saved results', async ({ shots, page }) => {
  // the Decide cards of a build item, with its reuse card's picture and the plan chosen
  let item = await openItem(page, 'Dell U2419H monitor, 24 inch')
  const cards = item.getByRole('region', { name: 'What to do with it' })
  await cards.waitFor({ state: 'visible', timeout: 10_000 }).catch(() => undefined)
  test.skip(!(await cards.isVisible()), 'Decide shows the visitor no saved cards on this version')
  await shots.show(cards)
  await shots.take('10-visitor-decide')
  await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()
  // a sell draft in Marketplace's fields, and a give-away with how to post it
  item = await openItem(page, 'Sun flat panel monitor')
  await shots.show(item.getByRole('region', { name: 'Marketplace handoff' }))
  await shots.take('11-visitor-sell-draft')
  await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()
  item = await openItem(page, 'Older ThinkPad, type 9461')
  await shots.show(item.getByRole('region', { name: 'Marketplace handoff' }))
  await shots.take('12-visitor-give-draft')
})
