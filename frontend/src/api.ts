// Typed client for the FastAPI backend. All data comes from the database via /api.

export type Confidence = 'high' | 'medium' | 'low'

export interface PriorityTag { name: string; slug: string; confidence: Confidence }

export interface FacultyCard {
  id: number
  name: string
  title: string | null
  school: string | null
  department: string | null
  keywords: string[]
  priorities: PriorityTag[]
  regions: string[]
  has_bio: boolean
  bio_excerpt: string | null
  directory: 'yigh' | 'ysph'
  photo_url?: string | null
}

export interface Activity {
  title: string | null
  type: string | null
  start: string | null
  end: string | null
  locations: string[]
  synopsis: string | null
}

export interface Evidence { field: string; term?: string; snippet?: string }

export interface GeneratedTag {
  name: string
  confidence: Confidence
  explanation: string
  evidence: Evidence[]
  method: string
}

export interface FacultyDetail extends FacultyCard {
  email: string | null
  profile_url: string
  inclusion_reasons: string[]
  source: {
    bio: string | null
    appointments: { department: string; title: string | null; type: string | null }[]
    research_interests: string[]
    activities: Activity[]
    organizations: { name: string; url: string | null }[]
    yale_coauthors: { name: string; profile_url: string | null; faculty_id: number | null }[]
  }
  generated: { priorities: GeneratedTag[]; keywords: GeneratedTag[]; regions: GeneratedTag[] }
}

export interface FilterOption { value: string; label: string; count: number; kind?: string }
export interface Filters {
  schools: FilterOption[]
  keywords: FilterOption[]
  priorities: FilterOption[]
  regions: FilterOption[]
  directories: FilterOption[]
  total_faculty: number
}

export type Criterion = 'shared_interests' | 'complementary_expertise' | 'geography' | 'strategic_priorities' | 'cross_school'

export interface MatchEvidence { faculty_id: number; faculty: string; field: string | null; text: string | null }
export interface MatchReason { criterion: Criterion; text: string; evidence: MatchEvidence[]; tag: string | null }

export interface Match {
  rank: number
  score: number
  already_coauthors: boolean
  faculty: { id: number; name: string; title: string | null; school: string | null; departments: string[]; profile_url: string }
  breakdown: Record<Criterion, { score: number; weight: number; contribution: number }>
  summary: string
  highlights: Record<Exclude<Criterion, 'cross_school'>, string[]>
  reasons: MatchReason[]
}

export interface CollaboratorResponse {
  faculty: { id: number; name: string; school: string | null; profile_url: string }
  weights: Record<Criterion, number>
  disclaimer: string
  matches: Match[]
}

export interface NetworkNode {
  id: number
  name: string
  title: string | null
  school: string | null
  departments: string[]
  primary_priority: { name: string; confidence: Confidence } | null
  priorities: string[]
  keywords: string[]
  degree: number
  profile_url: string
}

export interface NetworkEdge {
  id: string
  source: number
  target: number
  score: number
  already_coauthors: boolean
  summary: string
  highlights: Match['highlights']
  breakdown: Match['breakdown']
  reasons: MatchReason[]
}

export interface NetworkResponse { nodes: NetworkNode[]; edges: NetworkEdge[]; candidates: number; disclaimer: string }
export interface NetworkQuery { school?: string; keyword?: string; priority?: string; size?: number; new_connections_only?: boolean }

export interface DirectoryQuery { q?: string; school?: string; keyword?: string; priority?: string; region?: string; directory?: string }

async function get<T>(path: string, params: Record<string, string | number | boolean | undefined> = {}): Promise<T> {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== '') qs.set(k, String(v)) })
  const url = `/api${path}${qs.toString() ? `?${qs}` : ''}`
  let res: Response
  try {
    res = await fetch(url)
  } catch {
    throw new Error('Could not reach the Constellation server. Is the API running?')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ? String(body.detail) : `Request failed (${res.status})`)
  }
  return res.json() as Promise<T>
}

export const api = {
  filters: () => get<Filters>('/filters'),
  faculty: (q: DirectoryQuery) => get<FacultyCard[]>('/faculty', { ...q }),
  facultyDetail: (id: number) => get<FacultyDetail>(`/faculty/${id}`),
  network: (q: NetworkQuery) => get<NetworkResponse>('/network', { ...q }),
  collaborators: (id: number, opts: { limit?: number; cross_school_only?: boolean; new_connections_only?: boolean } = {}) =>
    get<CollaboratorResponse>(`/faculty/${id}/collaborators`, opts),
}

// ---------------------------------------------------------------- Radar / Nexus / partners / dashboard

export interface OppCard {
  id: number; uid: string; opportunity_number: string | null; title: string; funder: string | null
  deadline: string | null; deadline_text: string | null; days_left: number | null; award_text: string | null; status: string
  priorities: { slug: string; name: string; confidence: Confidence }[]
  verification_status: string; needs_review: boolean; official_url: string; first_seen_at: string; last_changed_at: string | null
}

export interface OppDetail extends OppCard {
  description: string | null; award_floor: number | null; award_ceiling: number | null; currency: string | null
  eligibility: string | null; geographic_restrictions: string | null; application_url: string | null; posted_date: string | null
  status_reason: string | null; review_reasons: string[]; suspicious_content: boolean
  verification: { status: string; last_verified_at: string | null; history: { checked_at: string; method: string; url: string; status: string }[] }
  priority_evidence: { priority: string; confidence: string; explanation: string }[]
  sources: { source: string; url: string; retrieved_at: string }[]
  changes: { type: string; field: string | null; old: string | null; new: string | null; detected_at: string }[]
  note: string
}

export interface Labelled { text: string; label: string }
export interface DocEvidence { id: string; kind: string; label: string; quote: string; source_url: string; origin: string; confidence: string | null }
export interface RecPerson { faculty_id: number; name: string; title: string | null; school: string | null; departments: string[]; profile_url: string; directory: string }
export interface TeamMember extends RecPerson { proposed_role: Labelled; contribution: Labelled; documented_evidence: DocEvidence[] }
export interface Team {
  name: string; match_score: number; score_explanation: string; complementarity: Labelled; members: TeamMember[]
  requirements_covered: string[]; missing_expertise: string[]; schools: string[]; verified_existing_coauthors: string[][]
}
export interface PartnerCard {
  organization_id: number; name: string; type: string; country: string | null; website: string | null; score: number
  why_relevant: string; capabilities: { area: string; evidence: string | null; url: string | null }[]; complements_team: string[]
  geographic_requirement: string
  relationship: { status: 'documented' | 'proposed'; summary: string; with_team_members: string[]; evidence: { url: string; quote: string }[] }
  needs_verification: string[]; last_verified: string | null; stale: boolean; evidence_urls: string[]; note: string
}
export interface Workspace {
  opportunity: OppDetail
  recommended_faculty: (RecPerson & { match_score: number; stage_a_score: number; explanation: Labelled; documented_evidence: DocEvidence[] })[]
  teams: Team[]
  external_partners: { teams: { team: string; target_countries: string[]; partners: PartnerCard[]; collaboration_gaps: string[] }[]; requires_local_partner: boolean; method: string }
  eligibility_and_collaboration_gaps: string[]
  strategic_alignment: { documented: { priority: string; confidence: string; explanation: string }[]; assessment: Labelled }
  generated_by: string; validation: { unsupported_claims_removed: string[]; model_error: string | null }; notes: string[]; sources: string[]
}
export interface ConceptDoc {
  team: string; generated_by: string; label: string
  concept: { working_title: string; problem_and_significance: string; aims: string[]; approach: string; team_roles: string[]
             partnerships: string; requirement_fit: { requirement: string; how_addressed: string }[]; yigh_alignment: string; open_questions: string[] }
  removed_unsupported_claims: string[]; model_error: string | null; sources: string[]; goals?: string[]
}
export interface Brief {
  run: Record<string, any> | null; generated_at: string | null; highlights: OppCard[]; new: OppCard[]; updated: OppCard[]
  closing_soon: OppCard[]; open_by_priority: Record<string, number>; review_queue: number
}
export interface Dashboard {
  faculty: { total: number; by_directory: Record<string, number>; by_school: Record<string, number> }
  opportunities: { total: number; open: number; verified_open: number; needs_review: number }
  partners: { organizations: number; documented_yale_links: number }
  watchlist: { sources: number; automated: number; by_method: Record<string, number> }
  priorities: Record<string, { faculty: number; open_opportunities: number }>
  last_discovery_run: Record<string, any> | null
  recent_matches: { opportunity: { id: number; title: string; funder: string | null; deadline: string | null }; generated_by: string; top_faculty: string[]; teams: number }[]
}
export interface RadarQuery { q?: string; status?: string; priority?: string; funder?: string; deadline_before?: string; geo?: string }

async function send<T>(path: string, params: Record<string, string | undefined> = {}): Promise<T> {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][])
  const res = await fetch(`/api${path}${qs.toString() ? `?${qs}` : ''}`, { method: 'POST' })
  if (!res.ok) {
    const b = await res.json().catch(() => null)
    throw new Error(b?.detail ? String(b.detail) : `Request failed (${res.status})`)
  }
  return res.json()
}

export interface TimingOpp { id: number; title: string; status: string; posted_date: string | null; deadline: string | null; deadline_text: string | null; first_seen_at: string; official_url: string }
export interface FunderTiming {
  funder: { slug: string; name: string; website: string | null }; headline: string
  open_now: TimingOpp[]; forecasted: TimingOpp[]; last_opened: TimingOpp | null; first_recorded: TimingOpp | null; last_closed: TimingOpp | null
  watch: { name: string; official_url: string; access_method: string; last_checked_at: string | null; last_status: string | null; page_change_pending: boolean; page_last_changed_at: string | null; notes: string | null }[]
  note: string
}

export const launchpad = {
  importLink: (url: string) => postJson<{ id: number; title: string; how: 'existing' | 'grants_gov' | 'page'; message: string }>('/launchpad/import', { url }),
  onePager: (opportunity_id: number, goals: string[], team?: string) => postJson<ConceptDoc>('/launchpad/one-pager', { opportunity_id, goals, team }),
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!res.ok) {
    const b = await res.json().catch(() => null)
    throw new Error(typeof b?.detail === 'string' ? b.detail : `Request failed (${res.status})`)
  }
  return res.json()
}

export const radar = {
  funderTiming: (slug: string) => get<FunderTiming>(`/radar/funders/${encodeURIComponent(slug)}/timing`),
  dashboard: () => get<Dashboard>('/dashboard'),
  brief: () => get<Brief>('/radar/brief'),
  funders: () => get<FilterOption[]>('/radar/funders'),
  list: (q: RadarQuery) => get<{ count: number; opportunities: OppCard[]; note: string }>('/radar/opportunities', { ...q, limit: 300 }),
  detail: (id: number) => get<OppDetail>(`/radar/opportunities/${id}`),
  workspace: (id: number) => get<Workspace>(`/radar/opportunities/${id}/workspace`),
  concept: (id: number, team?: string) => send<ConceptDoc>(`/nexus/opportunities/${id}/concept`, { team }),
  facultyPartners: (id: number) => get<{ organization: { id: number; name: string; country: string; type: string; website: string | null }; link: string; evidence_url: string }[]>(`/faculty/${id}/partners`),
}

export interface WatchSource {
  id: string; name: string; official_url: string; endpoint: string | null; access_method: 'api' | 'rss' | 'html_listing' | 'page_monitor' | 'manual'
  enabled: boolean; notes: string | null; funder: string | null; last_status: string | null; last_checked_at: string | null
  last_success_at: string | null; last_error: string | null; opportunities: { total: number; open: number }
  page_change_pending: boolean; last_snapshot_at: string | null
}
export interface ChangedPage { id: number; source_id: number; source: string; url: string; retrieved_at: string; excerpt: string | null }

export const watch = {
  sources: () => get<WatchSource[]>('/radar/sources'),
  review: () => get<{ changed_pages: ChangedPage[]; opportunities: OppCard[] }>('/radar/review'),
  markReviewed: (id: number) => send<{ id: number; reviewed: boolean }>(`/radar/page-changes/${id}/reviewed`),
}

export interface MatchedOpp {
  opportunity: { id: number; title: string; funder: string | null; deadline: string | null; deadline_text: string | null; status: string
                 priorities: string[]; verification_status: string }
  top_faculty: { id: number; name: string }[]
  potential_partners: { id: number; name: string; country: string | null; relationship: 'documented' | 'proposed'; website: string | null }[]
  partner_gaps: string[]
}
export const matches = { list: (limit = 20) => get<{ count: number; opportunities: MatchedOpp[]; note: string }>('/radar/matches', { limit }) }
