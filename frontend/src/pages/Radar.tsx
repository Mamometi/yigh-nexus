import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { matches, radar, type MatchedOpp, type OppCard, type RadarQuery } from '../api'
import { Deadline, VERIFY_LABEL } from '../components/OppCardView'
import { PRIORITY_COLORS, PriorityChip } from '../components/Tags'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { FunderTimingPanel } from '../components/FunderTiming'
import { useAsync, useDebounced } from '../hooks'

const PRIORITIES = [['climate-health', 'Climate & Health'], ['digital-health-ai', 'Digital Health & AI'],
                    ['health-diplomacy-security', 'Health Diplomacy & Security'], ['health-sovereignty', 'Health Sovereignty']]
const GEO = [['foreign_eligible', 'Non-US institutions mentioned as eligible'], ['lmic_lead', 'LMIC-based applicants / focus'], ['us_only', 'US institutions only']]
const WINDOWS = [['30', 'Next 30 days'], ['90', 'Next 90 days'], ['180', 'Next 6 months']]

export function Radar() {
  const [params, setParams] = useSearchParams()
  const [text, setText] = useState(params.get('q') ?? '')
  const q = useDebounced(text.trim(), 300)
  const get = (k: string) => params.get(k) ?? undefined
  const status = params.get('status') ?? 'open'
  const win = get('within')
  const deadline_before = win ? new Date(Date.now() + Number(win) * 864e5).toISOString().slice(0, 10) : undefined
  const query: RadarQuery = { q: q || undefined, status: status === 'all' ? undefined : status, priority: get('priority'), funder: get('funder'),
                              geo: get('geo'), deadline_before }
  const [list, retry] = useAsync(() => radar.list(query), [q, status, get('priority'), get('funder'), get('geo'), win])
  const [funders] = useAsync(radar.funders, [])
  const [matched] = useAsync(() => matches.list(60), [])
  const byId = useMemo(() => new Map(matched.status === 'success' ? matched.data.opportunities.map(m => [m.opportunity.id, m]) : []), [matched])
  const set = (k: string, v?: string) => { const n = new URLSearchParams(params); v ? n.set(k, v) : n.delete(k); setParams(n, { replace: true }) }
  const review = params.get('review') === '1'
  const rows = useMemo(() => list.status === 'success' ? list.data.opportunities.filter(o => !review || o.needs_review) : [], [list, review])

  const [shown, setShown] = useState(PAGE)
  const facets: [string, string, string[][], string?][] = [
    ['priority', 'Strategic priority', PRIORITIES], ['within', 'Deadline', WINDOWS], ['geo', 'Geographic eligibility', GEO],
    ['status', 'Status', [['open', 'Open'], ['forecasted', 'Forecasted'], ['closed', 'Closed'], ['unknown', 'Status unknown'], ['all', 'All']], 'open'],
  ]

  return (
    <div className="page radar osf">
      <header className="osf-head">
        <div className="osf-head__inner">
        <p className="eyebrow eyebrow--light">Opportunity Radar</p>
        <h1>Funding opportunities</h1>
        <p className="lede">Opportunities are collected every Monday from official sources (Grants.gov, the NIH Guide, funder pages) and checked
          against the funder’s own record. Each opportunity aligned with a YIGH priority lists suggested Yale faculty and potential external partners, based on their public Yale profiles and past partnerships. Nobody has been contacted.</p>
              </div>
        <svg className="wave" viewBox="0 0 1440 80" preserveAspectRatio="none" aria-hidden><path d="M0,40 C360,90 1080,-10 1440,40 L1440,80 L0,80 Z" /></svg>
      </header>

      <section className="osf-filters" aria-label="Filters">
        <div className="osf-filters__search">
          <label htmlFor="r-q" className="osf-label">Search</label>
          <input id="r-q" className="input" value={text} onChange={e => { setText(e.target.value); setShown(PAGE); set('q', e.target.value || undefined) }} placeholder="e.g. malaria, climate, polio" />
          <label htmlFor="r-funder" className="osf-label">Funder</label>
          <select id="r-funder" value={get('funder') ?? ''} onChange={e => { setShown(PAGE); set('funder', e.target.value || undefined) }}>
            <option value="">All funders</option>
            {funders.status === 'success' && funders.data.map(f => <option key={f.value} value={f.value}>{f.label} ({f.count})</option>)}
          </select>
        </div>
        <div className="osf-drops">
          {facets.map(([k, label, opts, def]) => (
            <div className="field" key={k}>
              <label htmlFor={`f-${k}`} className="osf-label">{label}</label>
              <select id={`f-${k}`} value={params.get(k) ?? def ?? ''} onChange={e => { setShown(PAGE); set(k, e.target.value === (def ?? '') ? undefined : e.target.value) }}>
                {!def && <option value="">Any</option>}
                {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
          ))}
        </div>
        <div className="osf-filters__foot">
          <label className="toggle"><input type="checkbox" checked={review} onChange={e => set('review', e.target.checked ? '1' : undefined)} /> <span>Only items flagged for review</span></label>
          {params.toString() && <button className="link-btn" onClick={() => { setText(''); setShown(PAGE); setParams(new URLSearchParams(), { replace: true }) }}>Clear all filters</button>}
        </div>
        <p className="muted small">Geographic eligibility is matched on the funder’s own eligibility text; always confirm on the official page.</p>
      </section>

      {get('funder') && <FunderTimingPanel slug={get('funder')!} />}

      <section aria-live="polite" className="osf-results">
        {list.status === 'success' && <p className="osf-count"><strong>{rows.length}</strong> {rows.length === 1 ? 'Opportunity' : 'Opportunities'} Found</p>}
        {list.status === 'loading' && <Loading label="Loading opportunities…" />}
        {list.status === 'error' && <ErrorState message={list.error} onRetry={retry} />}
        {list.status === 'success' && rows.length === 0 && (
          <EmptyState title="No opportunities match" action={<button className="btn" onClick={() => setParams(new URLSearchParams(), { replace: true })}>Clear filters</button>}>
            Try a different status or remove a filter.
          </EmptyState>
        )}
        <div className="osf-list">{rows.slice(0, shown).map(o => <OppRow key={o.id} o={o} m={byId.get(o.id)} loading={matched.status === 'loading'} />)}</div>
        {rows.length > shown && <button className="osf-more" onClick={() => setShown(shown + PAGE)}>View more opportunities ({rows.length - shown} remaining)</button>}
      </section>

    </div>
  )
}

const PAGE = 10

function OppRow({ o, m, loading }: { o: OppCard; m?: MatchedOpp; loading: boolean }) {
  const field = (label: string, v: React.ReactNode) => v ? <div className="osf-field"><span className="osf-label">{label}</span><div>{v}</div></div> : null
  return (
    <article className="osf-row" style={{ '--c': o.priorities[0] ? PRIORITY_COLORS[o.priorities[0].slug] : 'var(--line)' } as React.CSSProperties}>
      <h3><Link to={`/radar/${o.id}`}>{o.title}</Link></h3>
      <div className="osf-fields">
        {field('Funder', [o.funder, o.opportunity_number].filter(Boolean).join(' · '))}
        {field('Status', <span className={`status status--${o.status}`}>{o.status}</span>)}
        {field('Deadline', <Deadline o={o} />)}
        {field('Award', o.award_text)}
        {field('Strategic priorities', o.priorities.length > 0 && <div className="chips">{o.priorities.map(p => <PriorityChip key={p.slug} name={p.name} slug={p.slug} confidence={p.confidence} />)}</div>)}
        {field('Verification', <span className={`verify verify--${o.verification_status}`}>{VERIFY_LABEL[o.verification_status] ?? o.verification_status}{o.needs_review ? ' · needs review' : ''}</span>)}
      </div>
      {(m || loading) && o.priorities.length > 0 && <div className="osf-fields osf-fields--match">
        {field('Suggested Yale faculty', m ? (m.top_faculty.length ? <span className="small">{m.top_faculty.map((f, i) => <span key={f.id}>{i > 0 && ', '}<Link to={`/faculty/${f.id}`}>{f.name.split(',')[0]}</Link></span>)}</span>
                                                : <span className="muted small">None suggested</span>) : <span className="muted small">Matching…</span>)}
        {field('Potential external partners', m ? (m.potential_partners.length ? (
          <ul className="plain matched__partners small">{m.potential_partners.map(p => (
            <li key={p.id}>{p.website ? <a href={p.website} target="_blank" rel="noreferrer">{p.name}</a> : p.name}
              {p.country && <span className="muted"> ({p.country})</span>}{' '}
              <span className={`rel rel--${p.relationship}`}>{p.relationship === 'documented' ? 'Connected to Yale' : 'New suggestion'}</span></li>))}</ul>
        ) : <span className="muted small">{m.partner_gaps[0] ?? 'None suggested'}</span>) : <span className="muted small">Matching…</span>)}
      </div>}
      <p className="osf-row__actions">
        <a href={o.official_url} target="_blank" rel="noreferrer">Official source ↗</a>
        <Link className="btn btn--sm" to={`/radar/${o.id}#team`}>Find a team</Link>
      </p>
    </article>
  )
}
