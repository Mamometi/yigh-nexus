// GRAPPH hub API: pathways, Facilities & Resources builder, letters of support
export interface TopicCard { section: string; slug: string; title: string; summary: string }
export interface Section { slug: string; title: string; short?: string; icon: string; color: string; summary: string; topics: TopicCard[]; links?: { title: string; path: string }[] }
export interface PlanPerson { id: number; name: string; title: string | null; school: string | null; why: string[] }
export interface PlanOrg { id: number; name: string; country: string | null; type: string; website: string | null; works_with_yale: boolean; why: string[] }
export interface PlanResource { id: string; name: string; url: string; category: string; text: string }
export interface PlanStep extends TopicCard { section_title: string; why: string; office: string | null; path: string }
export interface Plan { stage: string; stage_label: string; opportunity: { id: number; title: string; funder: string | null } | null;
  faculty: PlanPerson[]; partners: PlanOrg[]; resources: PlanResource[]; steps: PlanStep[] }
export interface Office { name: string; url?: string | null; email?: string | null; topics: TopicCard[] }
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
  plan: (b: { stage: string; text: string; opportunity_id: number | null }) => call<Plan>('/api/hub/plan', { method: 'POST', body: JSON.stringify(b) }),
  offices: () => call<Office[]>('/api/hub/offices'),
  feedback: (b: { page: string; page_title: string; kind: string; message: string; email: string }) => call<{ ok: boolean }>('/api/hub/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }),
  topic: (section: string, slug: string) => call<Topic>(`/api/hub/topics/${section}/${slug}`),
  search: (q: string) => call<SearchHit[]>(`/api/hub/search?q=${encodeURIComponent(q)}`),
  facilities: () => call<Facility[]>('/api/hub/facilities'),
  draftFacilities: (body: { ids: string[]; project: string; site_text: string; polish: boolean }) =>
    call<{ text: string; mode: string; sources: { name: string; url: string }[]; note?: string }>('/api/hub/facilities/draft', { method: 'POST', body: JSON.stringify(body) }),
  templates: () => call<Templates>('/api/hub/templates'),
  letters: () => call<LetterRequest[]>('/api/hub/letters'),
  requestLetter: (body: Record<string, unknown>) => call<LetterRequest>('/api/hub/letters', { method: 'POST', body: JSON.stringify(body) }),
}
