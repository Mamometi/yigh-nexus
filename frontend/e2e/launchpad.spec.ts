import { expect, test } from '@playwright/test'
import { removeTestUser, signIn } from './helpers'

test.setTimeout(300_000)
test.afterAll(() => removeTestUser())

test('signed out: pick from the list, see people, one-pager asks for sign-in and returns here', async ({ page }) => {
  await page.goto('/launchpad')
  await expect(page.locator('.launch__list button').first()).toBeVisible()
  await expect(page.locator('.launch__pick')).toContainText('Sign in to add an opportunity from a link')
  await page.fill('.launch__pick input[type=search]', 'emerging infections')
  const opt = page.locator('.launch__list button').first()
  const title = (await opt.locator('strong').innerText()).trim()
  await opt.click()
  await expect(page).toHaveURL(/opp=\d+/)
  await expect(page.locator('.launch__chosen h2')).toHaveText(title)
  await expect(page.locator('.launch__grid .launch__people li').first()).toBeVisible({ timeout: 120000 })
  await page.locator('#one-pager').getByRole('link', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/signin\?next=%2Flaunchpad%3Fopp%3D\d+/)
})

test('signed in: paste a known link, then draft a one-pager from goals', async ({ page }) => {
  await page.goto('/')
  await signIn(page)
  await page.goto('/launchpad')
  await page.fill('.launch__link input', 'not a link')
  await page.fill('.launch__link input', 'https://www.grants.gov/search-results-detail/364127')
  await page.getByRole('button', { name: 'Use this link' }).click()
  await expect(page.locator('.launch__msg')).toContainText('already in the Opportunities hub')
  await expect(page).toHaveURL(/opp=\d+/)
  await expect(page.locator('.launch__chosen h2')).toBeVisible({ timeout: 120000 })
  const goals = ['Study adolescent HIV care in two clinics', 'Train peer counselors']
  await page.fill('#lp-goals', goals.map(g => `- ${g}`).join('\n'))
  await expect(page.locator('.launch__row')).toContainText('2 points')
  await page.getByRole('button', { name: 'Draft my one-pager' }).click()
  const concept = page.locator('#one-pager .concept')
  await expect(concept).toBeVisible({ timeout: 120000 })
  const aims = (await concept.locator('ol li').allInnerTexts()).join(' ').toLowerCase()
  if (await concept.locator('.concept__label').count()) {          // AI draft: goals are reworded into aims
    for (const key of ['adolescent', 'clinic', 'peer counselor']) expect(aims).toContain(key)
    await expect(concept.locator('.concept__label')).toContainText('check every statement')
  } else {                                                          // basic outline: goals become the aims verbatim
    await expect(concept.locator('ol li')).toHaveText(goals.map(g => `${g}.`))
  }
  await expect(concept).not.toContainText(/no AI was used|\[Outline\]|documented/i)
})
