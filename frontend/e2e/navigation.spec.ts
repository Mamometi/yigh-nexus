import { expect, test } from '@playwright/test'
import { watchErrors } from './helpers'

test('top menu reaches every page and marks the current one', async ({ page }) => {
  const errors = watchErrors(page)
  await page.goto('/')
  for (const [name, url, heading] of [['Opportunity Radar', '/radar', 'Funding opportunities'], ['Faculty Directory', '/directory', 'Yale faculty working in global health'],
                                      ['Team Launchpad', '/launchpad', 'From a funding call to a team and a plan'], ['Home', '/', 'Hub for Global Health at Yale']]) {
    await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name, exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`${url.replace('/', '\\/')}$`))
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(heading)
    await expect(page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name, exact: true })).toHaveClass(/active/)
  }
  expect(errors).toEqual([])
})

test('old addresses redirect and unknown ones offer a way home', async ({ page }) => {
  await page.goto('/dashboard'); await expect(page).toHaveURL(/\/$/)
  await page.goto('/constellation'); await expect(page).toHaveURL(/\/directory$/)
  await page.goto('/no-such-page')
  await expect(page.getByText('Page not found')).toBeVisible()
  await page.getByRole('link', { name: /home/i }).last().click()
  await expect(page).toHaveURL(/\/$/)
})

test('footer links work', async ({ page }) => {
  await page.goto('/')
  const footer = page.locator('.site-footer')
  for (const [name, url] of [['Opportunity Radar', '/radar'], ['Faculty Directory', '/directory'], ['Team Launchpad', '/launchpad']]) {
    await footer.getByRole('link', { name, exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`${url}$`))
  }
})
