// GRAPPH hub API: pathways, Facilities & Resources builder, letters of support
export interface TopicCard { section: string; slug: string; title: string; summary: string }
export interface Section { slug: string; title: string; icon: string; color: string; summary: string; topics: TopicCard[] }
export interface Link_ { title: string; url: string; note?: string }
export interface Topic extends TopicCard {
  office?: { name: string; url?: string; email?: string }
  key_considerations?: string[]
  steps?: { title: string; detail: string; url?: string }[]
  resources?: Link_[]
  good_to_know?: string[]
  important?: string
  related: TopicCard[]
  sources?: string[]
  last_reviewed?: string
  section_info: Section
  siblings: TopicCard[]
}
export interface Facility { id: string; category: string; name: string; url: string; text: string }
export interface Templates {
  letters: { id: string; title: string; use: string; body: string }[]
  checklists: { id: string; title: string; items: string[]; related: string[] }[]
}
export interface LetterRequest { id: number; signer: string; project_title: string; funder: string; deadline: string; summary: string
  confirm: string; status: string; created_at: string; warning?: string | null }
export interface SearchHit { title: string; summary: string; kind: string; path: string }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { credentials: 'same-origin', ...init,
    headers: init?.body ? { 'content-type': 'application/json' } : undefined })
  if (!r.ok) {
    let msg = `Request failed (${r.status})`
    try { const d = await r.json(); msg = typeof d.detail === 'string' ? d.detail : Array.isArray(d.detail) ? 'Please check the form: ' + d.detail.map((x: { loc: string[] }) => x.loc.at(-1)).join(', ') : msg } catch { /* keep default */ }
    throw new Error(msg)
  }
  return r.json()
}

export const hub = {
  sections: () => call<Section[]>('/api/hub/sections'),
  topic: (section: string, slug: string) => call<Topic>(`/api/hub/topics/${section}/${slug}`),
  search: (q: string) => call<SearchHit[]>(`/api/hub/search?q=${encodeURIComponent(q)}`),
  facilities: () => call<Facility[]>('/api/hub/facilities'),
  draftFacilities: (body: { ids: string[]; project: string; site_text: string; polish: boolean }) =>
    call<{ text: string; mode: string; sources: { name: string; url: string }[]; note?: string }>('/api/hub/facilities/draft', { method: 'POST', body: JSON.stringify(body) }),
  templates: () => call<Templates>('/api/hub/templates'),
  letters: () => call<LetterRequest[]>('/api/hub/letters'),
  requestLetter: (body: Record<string, unknown>) => call<LetterRequest>('/api/hub/letters', { method: 'POST', body: JSON.stringify(body) }),
}
