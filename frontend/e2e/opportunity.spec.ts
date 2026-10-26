import { expect, test } from '@playwright/test'
import { api } from './helpers'

test('opportunity page: details match the record, sections link, Launchpad needs sign-in', async ({ page, request }) => {
  const m = await api(request, '/radar/matches?limit=1')
  const id = m.opportunities[0].opportunity.id
  const o = await api(request, `/radar/opportunities/${id}`)
  await page.goto(`/radar/${id}`)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(o.title)
  if (o.award_text) await expect(page.getByText(o.award_text).first()).toBeVisible()
  for (const sec of ['team', 'partners', 'gaps', 'launchpad', 'sources']) {
    await page.locator(`a[href="#${sec}"]`).first().click()
    await expect(page.locator(`#${sec}`)).toBeInViewport()
  }
  await expect(page.locator('#launchpad')).toContainText('Sign in to use the Launchpad')
  await page.locator('#launchpad').getByRole('link', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/signin\?next=/)
})
