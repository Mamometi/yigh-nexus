import { expect, test } from '@playwright/test'
import { api } from './helpers'

const count = async (page: any) => Number(((await page.locator('.osf-count').innerText().catch(() => '')).match(/\d+/) ?? ['-1'])[0])

test.beforeEach(async ({ page }) => { await page.goto('/radar'); await expect(page.locator('.osf-count')).toBeVisible() })

test('count matches the API and view more reveals every row', async ({ page, request }) => {
  const d = await api(request, '/radar/opportunities?status=open&limit=300')
  expect(await count(page)).toBe(d.count)
  while (await page.locator('.osf-more').isVisible()) await page.locator('.osf-more').click()
  await expect(page.locator('.osf-row')).toHaveCount(d.count)
})

for (const [id, value, param] of [['f-priority', 'climate-health', 'priority'], ['f-within', '90', 'within'], ['f-geo', 'foreign_eligible', 'geo'], ['f-status', 'forecasted', 'status']]) {
  test(`dropdown ${id} filters and updates the address`, async ({ page }) => {
    await page.selectOption(`#${id}`, value)
    await expect(page).toHaveURL(new RegExp(`${param}=${value}`))
    const q = param === 'within' ? `deadline_before=${new Date(Date.now() + 90 * 864e5).toISOString().slice(0, 10)}&status=open`
      : param === 'status' ? `status=${value}` : `${param}=${value}&status=open`
    const n = (await api(page.request, `/radar/opportunities?${q}&limit=300`)).count
    await expect.poll(() => count(page)).toBe(n)
    while (await page.locator('.osf-more').isVisible()) await page.locator('.osf-more').click()
    await expect(page.locator('.osf-row')).toHaveCount(n)
    if (param === 'status') for (const s of await page.locator('.osf-row .status').allInnerTexts()) expect(s.toLowerCase()).toBe('forecasted')
    if (param === 'priority') for (let i = 0; i < n; i++) await expect(page.locator('.osf-row').nth(i).locator('.chip--priority', { hasText: 'Climate & Health' })).toHaveCount(1)
  })
}

test('choosing a funder shows its timing and only its opportunities', async ({ page, request }) => {
  await page.selectOption('#r-funder', 'agency-hhs-nih11')
  await expect(page.locator('.ftime h2')).toHaveText('National Institutes of Health')
  const t = await api(request, '/radar/funders/agency-hhs-nih11/timing')
  await expect(page.locator('.ftime__headline')).toHaveText(t.headline)
  for (const f of await page.locator('.osf-row .osf-field:has(.osf-label:text("Funder")) div').allInnerTexts()) expect(f).toContain('National Institutes of Health')
  await page.selectOption('#r-funder', 'wellcome')
  await expect(page.locator('.ftime__headline')).toContainText(/not recorded|no next round|open now/i)
})

test('search and clear all', async ({ page }) => {
  const all = await count(page)
  await page.fill('#r-q', 'malaria')
  await expect(page).toHaveURL(/q=malaria/)
  await expect.poll(() => count(page)).toBeLessThanOrEqual(all)
  await page.getByRole('button', { name: 'Clear all filters' }).click()
  await expect(page).toHaveURL(/\/radar$/)
  await expect(page.locator('#r-q')).toHaveValue('')
  await expect.poll(() => count(page)).toBe(all)
})

test('opening an opportunity and Find a team land on the right place', async ({ page }) => {
  const row = page.locator('.osf-row').first()
  const title = await row.locator('h3').innerText()
  await row.locator('h3 a').click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(title)
  await page.goBack()
  await page.locator('.osf-row').first().getByRole('link', { name: 'Find a team' }).click()
  await expect(page).toHaveURL(/#team$/)
  await expect(page.locator('#team')).toBeInViewport({ timeout: 20000 })
})

test('suggested faculty links open the right profile', async ({ page }) => {
  const link = page.locator('.osf-fields--match a[href^="/faculty/"]').first()
  const name = (await link.innerText()).trim()
  await link.click()
  await expect(page.getByRole('heading', { level: 1 })).toContainText(name)
})
