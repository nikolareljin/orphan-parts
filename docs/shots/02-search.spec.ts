import { expect, test } from './lib'

// Find a part, the recorded parts: the searches, the agitator's search with its plan section,
// the listings brought back, Search the web and Check fit on what it found.

test.describe.configure({ mode: 'serial' })

const TITLE = /all-metal agitator rod/

test('the searches and a new search', async ({ shots, page }) => {
  await page.goto('/#find')
  await expect(page.getByRole('table', { name: 'Searches' })).toBeVisible()
  await shots.take('01-searches')
  await shots.show(page.getByRole('form', { name: 'New search' }))
  await shots.take('02-new-search')
})

test('the search, its plan and its listings', async ({ shots, page }) => {
  await page.goto('/#find')
  await page.getByRole('table', { name: 'Searches' }).getByRole('row', { name: TITLE }).getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: /^Search all-metal agitator rod/ })
  await expect(panel).toBeVisible()
  await shots.take('03-search-open')
  await shots.show(panel.getByRole('region', { name: 'Plan the search' }))
  await shots.take('04-plan-section')
  await shots.show(panel.getByRole('table', { name: 'Candidates' }))
  await shots.take('05-candidates')
})

test('Search the web, then Check fit on a page it found', async ({ shots, page }) => {
  await page.goto('/#find')
  await page.getByRole('table', { name: 'Searches' }).getByRole('row', { name: TITLE }).getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: /^Search all-metal agitator rod/ })
  const plan = panel.getByRole('region', { name: 'Plan the search' })
  await plan.getByRole('button', { name: 'Search the web' }).click()
  await expect(plan).toContainText(/Added \d+ pages? to the listings/, { timeout: 120_000 })
  const web = panel
    .getByRole('list', { name: 'Listings brought back, ranked' })
    .getByRole('listitem')
    .filter({ hasText: 'found on the web' })
    .first()
  await shots.show(web)
  await shots.take('06-web-finds')
  await web.getByRole('button', { name: 'Check fit' }).click()
  const fit = web.getByLabel(/^Fit of listing/)
  await expect(fit).toBeVisible({ timeout: 120_000 })
  await shots.show(web)
  await shots.take('07-check-fit')
  const questions = fit.locator('ul.questions')
  if (await questions.count()) {
    await shots.show(questions.first(), 'center')
    await shots.take('08-seller-questions')
  }
})
