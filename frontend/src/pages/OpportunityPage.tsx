import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { radar, type ConceptDoc, type PartnerCard, type Team, type Workspace } from '../api'
import { Deadline, VERIFY_LABEL, fmtDate } from '../components/OppCardView'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { Chip, CoauthorBadge, PriorityChip } from '../components/Tags'
import { useAsync } from '../hooks'
import { useAuth } from '../auth'

export const Label = ({ text }: { text: string }) => <span className="gen-label" title="A suggestion, not a fact: please check it">{text}</span>

export function OpportunityPage() {
  const id = Number(useParams().id)
  const { hash } = useLocation()
  const [det, retryDet] = useAsync(() => radar.detail(id), [id])
  const [ws, retry] = useAsync(() => radar.workspace(id), [id])
  useEffect(() => {
    if (hash && (det.status === 'success' || ws.status === 'success')) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: 'smooth' })
  }, [det.status, ws.status, hash])
  if (det.status === 'loading') return <Loading label="Loading opportunity…" />
  if (det.status === 'error') return <div className="page"><Link to="/radar" className="back">← Opportunity Radar</Link><ErrorState message={det.error} onRetry={retryDet} /></div>
  const o = det.data
  return (
    <div className="page opp">
      <Link to="/radar" className="back">← Opportunity Radar</Link>
      <header className="opp__head card">
        <div>
          <p className="eyebrow">{o.funder}{o.opportunity_number ? ` · ${o.opportunity_number}` : ''}</p>
          <h1>{o.title}</h1>
          <div className="chips">{o.priorities.map(p => <PriorityChip key={p.slug} name={p.name} slug={p.slug} confidence={p.confidence} />)}</div>
        </div>
        <dl className="facts">
          <div><dt>Status</dt><dd><span className={`status status--${o.status}`}>{o.status}</span></dd></div>
          <div><dt>Deadline</dt><dd><Deadline o={o} />{o.deadline_text && <span className="muted small"> ({o.deadline_text})</span>}</dd></div>
          <div><dt>Award</dt><dd>{o.award_text ?? <span className="muted">Not stated by the funder</span>}</dd></div>
          <div><dt>Verification</dt><dd className={`verify verify--${o.verification.status}`}>{VERIFY_LABEL[o.verification.status]}
            {o.verification.last_verified_at && <span className="muted small"> · {fmtDate(o.verification.last_verified_at.slice(0, 10))}</span>}</dd></div>
        </dl>
        <nav className="opp__nav small" aria-label="Sections">
          <a href="#details">Details</a><a href="#team">Faculty & teams</a><a href="#partners">Partners</a><a href="#gaps">Gaps</a><a href="#launchpad">Launchpad</a><a href="#sources">Sources</a>
        </nav>
      </header>

      <section id="details" className="card">
        <h2>1 · Opportunity details</h2>
        <p className="source-label small">From the funder’s announcement</p>
        {o.description ? <p className="opp__desc">{o.description}</p> : <p className="muted">The funder didn’t include a description.</p>}
        <div className="two-col">
          <div><h3>Eligibility</h3><p className="small">{o.eligibility ?? <span className="muted">Not stated: confirm with the funder.</span>}</p>
            {o.geographic_restrictions && <p className="small"><strong>Geography:</strong> {o.geographic_restrictions}</p>}</div>
          <div><h3>Review notes</h3>{o.review_reasons.length ? <ul className="plain small">{o.review_reasons.map(r => <li key={r}>{r}</li>)}</ul> : <p className="muted small">None.</p>}</div>
        </div>
        <p className="small"><a href={o.official_url} target="_blank" rel="noreferrer">Read the official announcement ↗</a>{o.application_url && o.application_url !== o.official_url && <> · <a href={o.application_url} target="_blank" rel="noreferrer">Application page ↗</a></>}</p>
      </section>

      {ws.status !== 'success' ? (
        <section id="team" className="card">
          <h2>2 · Recommended Yale faculty</h2>
          {ws.status === 'loading' ? <Loading label="Finding faculty, teams and partners…" /> : <ErrorState message={ws.error} onRetry={retry} />}
          <span id="partners" /><span id="gaps" /><span id="launchpad" /><span id="sources" />
        </section>
      ) : <WorkspaceSections w={ws.data} id={o.id} />}
    </div>
  )
}

function WorkspaceSections({ w, id }: { w: Workspace; id: number }) {
  return (
    <>
      <section id="team" className="card">
        <h2>2 · Recommended Yale faculty</h2>
        <p className="muted small">Picked because their Yale profiles mention the topics, methods and places this call is about. {w.generated_by.startsWith('ai') ? 'Ranked with help from AI; the reasons are suggestions to check.' : 'Matched automatically from Yale profiles.'}</p>
        <div className="people">
          {w.recommended_faculty.map(f => (
            <article key={f.faculty_id} className="person">
              <div className="person__score">{f.match_score}</div>
              <div>
                <h3><Link to={`/faculty/${f.faculty_id}`}>{f.name}</Link></h3>
                <p className="muted small">{[f.school, f.departments[0]].filter(Boolean).join(' · ')}</p>
                <p className="small">{f.explanation.text} <Label text={f.explanation.label} /></p>
                <Evidence items={f.documented_evidence} />
              </div>
            </article>
          ))}
        </div>
        <h2 className="mt">3 · Proposed interdisciplinary teams</h2>
        <div className="teams">{w.teams.map(t => <TeamCard key={t.name} t={t} partners={w.external_partners.teams.find(x => x.team === t.name)?.partners ?? []} />)}</div>
        {w.teams.length === 0 && <EmptyState title="No team could be proposed">We couldn’t find enough Yale faculty whose profiles match this call.</EmptyState>}
      </section>

      <section id="partners" className="card">
        <h2>4 · Suggested external partner organizations</h2>
        <p className="muted small">{w.external_partners.method} “Connected to Yale” means a public page shows an existing link; “New suggestion” means we found none. No organization has been contacted.</p>
        {w.external_partners.teams.map(t => (
          <div key={t.team} className="partner-team">
            <h3>{t.team} <span className="muted small">· target countries: {t.target_countries.join(', ') || 'none specified'}</span></h3>
            <div className="partners">{t.partners.map(p => <Partner key={p.organization_id} p={p} />)}</div>
            {t.partners.length === 0 && <p className="muted small">No suitable organization in the partner database.</p>}
          </div>
        ))}
      </section>

      <section id="gaps" className="card">
        <h2>5 · Eligibility and collaboration gaps</h2>
        {w.eligibility_and_collaboration_gaps.length ? <ul className="gaps">{w.eligibility_and_collaboration_gaps.map(g => <li key={g}>{g}</li>)}</ul> : <p className="muted">Nothing missing that we could spot. Still read the full call.</p>}
        <h3>YIGH strategic alignment</h3>
        <ul className="plain small">{w.strategic_alignment.documented.map(a => <li key={a.priority}><strong>{a.priority}</strong>: {a.explanation}</li>)}</ul>
        <p className="small">{w.strategic_alignment.assessment.text} <Label text={w.strategic_alignment.assessment.label} /></p>
      </section>

      <Launchpad id={id} teams={w.teams} />

      <section id="sources" className="card">
        <h2>6 · Sources</h2>
        <ul className="sources small">{w.sources.map(s => <li key={s}><a href={s} target="_blank" rel="noreferrer">{s}</a></li>)}</ul>
        <ul className="plain small muted">{w.notes.map(n => <li key={n}>{n}</li>)}</ul>
      </section>
    </>
  )
}

function Evidence({ items }: { items: Workspace['recommended_faculty'][number]['documented_evidence'] }) {
  if (!items.length) return null
  return (
    <details className="evidence small">
      <summary>Why we suggested them ({items.length} from their profile)</summary>
      <ul>{items.map(e => <li key={e.id}><strong>{e.label}</strong>: “{e.quote.slice(0, 220)}” <a href={e.source_url} target="_blank" rel="noreferrer">profile ↗</a></li>)}</ul>
    </details>
  )
}

function TeamCard({ t, partners }: { t: Team; partners: PartnerCard[] }) {
  return (
    <article className="team">
      <header className="team__head">
        <h3>{t.name}</h3>
        <span className="team__score" title={t.score_explanation}>{t.match_score}<small>/100</small></span>
      </header>
      <p className="small">{t.complementarity.text} <Label text={t.complementarity.label} /></p>
      <ul className="team__members">
        {t.members.map(m => (
          <li key={m.faculty_id}>
            <Link to={`/faculty/${m.faculty_id}`}><strong>{m.name.split(',')[0]}</strong></Link>
            <span className="muted small"> · {[m.school, m.departments[0]].filter(Boolean).join(' · ')}</span>
            <div className="small">{m.proposed_role.text}</div>
            <Evidence items={m.documented_evidence} />
          </li>
        ))}
      </ul>
      {t.verified_existing_coauthors.length > 0 && <p className="small"><CoauthorBadge /> {t.verified_existing_coauthors.map(p => p.map(n => n.split(',')[0]).join(' & ')).join('; ')}</p>}
      {t.missing_expertise.length > 0 && <p className="small"><strong>Missing:</strong> {t.missing_expertise.join('; ')}</p>}
      {partners.length > 0 && <p className="small"><strong>Partner ideas:</strong> {partners.slice(0, 3).map(p => p.name).join(', ')}</p>}
    </article>
  )
}

function Partner({ p }: { p: PartnerCard }) {
  return (
    <article className={`partner partner--${p.relationship.status}`}>
      <header>
        <h4>{p.website ? <a href={p.website} target="_blank" rel="noreferrer">{p.name}</a> : p.name}</h4>
        <span className={`rel rel--${p.relationship.status}`}>{p.relationship.status === 'documented' ? 'Connected to Yale' : 'New suggestion'}</span>
      </header>
      <p className="muted small">{p.country} · {p.type.replace(/_/g, ' ')}{p.stale ? ' · needs re-verification' : ''}</p>
      <p className="small">{p.why_relevant}</p>
      {p.complements_team.length > 0 && <div className="chips">{p.complements_team.slice(0, 3).map(c => <Chip key={c}>{c}</Chip>)}</div>}
      <p className="small"><strong>Geography:</strong> {p.geographic_requirement}</p>
      <details className="evidence small">
        <summary>Their Yale connection and what to check</summary>
        <p>{p.relationship.summary}</p>
        <ul>{p.relationship.evidence.map(e => <li key={e.url + e.quote}><a href={e.url} target="_blank" rel="noreferrer">{e.quote}</a></li>)}</ul>
        <strong>Verify:</strong><ul>{p.needs_verification.map(v => <li key={v}>{v}</li>)}</ul>
        <p className="muted">{p.note}</p>
      </details>
    </article>
  )
}

function Launchpad({ id, teams }: { id: number; teams: Team[] }) {
  const { user, ready } = useAuth()
  const [team, setTeam] = useState(teams[0]?.name ?? '')
  const [state, setState] = useState<{ s: 'idle' | 'loading' } | { s: 'error'; e: string } | { s: 'done'; d: ConceptDoc }>({ s: 'idle' })
  const run = () => { if (!user) return; setState({ s: 'loading' }); radar.concept(id, team).then(d => setState({ s: 'done', d })).catch((e: Error) => setState({ s: 'error', e: e.message })) }
  return (
    <section id="launchpad" className="card launchpad">
      <p className="eyebrow">Launchpad</p>
      <h2>Draft a one-page research concept</h2>
      <p className="muted small">Pick a team. You’ll get a one-page outline built around what the call asks for and what each person works on,
        ready for the team to fill in. Nothing is made up about anyone.</p>
      {!ready ? null : !user ? (
        <div className="launchpad__locked">
          <p><strong>Sign in to use the Launchpad.</strong> Drafting research concepts is available to signed-in Yale users.</p>
          <Link className="btn" to={`/signin?next=${encodeURIComponent(`/radar/${id}#launchpad`)}`}>Sign in</Link>
        </div>
      ) : teams.length === 0 ? <p className="muted">No team to draft for.</p> : (
        <div className="launchpad__controls">
          <select value={team} onChange={e => setTeam(e.target.value)} aria-label="Team">{teams.map(t => <option key={t.name}>{t.name}</option>)}</select>
          <button className="btn" onClick={run} disabled={state.s === 'loading'}>{state.s === 'loading' ? 'Generating…' : 'Generate concept'}</button>
        </div>
      )}
      {state.s === 'error' && <ErrorState message={state.e} onRetry={run} />}
      {state.s === 'done' && <ConceptView d={state.d} />}
    </section>
  )
}

export function ConceptView({ d }: { d: ConceptDoc }) {
  const c = d.concept
  return (
    <article className="concept">
      {d.generated_by.startsWith('ai') && <p className="concept__label"><Label text={d.label} /></p>}
      <h3>{c.working_title}</h3>
      <h4>Problem and significance</h4><p>{c.problem_and_significance}</p>
      <h4>Aims</h4><ol>{c.aims.map(a => <li key={a}>{a}</li>)}</ol>
      <h4>Approach</h4><p>{c.approach}</p>
      <h4>Team and proposed roles</h4><ul>{c.team_roles.map(r => <li key={r}>{r}</li>)}</ul>
      <h4>Partnerships</h4><p>{c.partnerships}</p>
      <h4>Fit with the call’s requirements</h4>
      <table className="table"><thead><tr><th>Requirement (from the call)</th><th>How addressed</th></tr></thead>
        <tbody>{c.requirement_fit.map(r => <tr key={r.requirement}><td>{r.requirement}</td><td>{r.how_addressed}</td></tr>)}</tbody></table>
      <h4>YIGH alignment</h4><p>{c.yigh_alignment}</p>
      <h4>Open questions to resolve</h4><ul>{c.open_questions.map(q => <li key={q}>{q}</li>)}</ul>
      <button className="btn btn--ghost btn--sm" onClick={() => navigator.clipboard?.writeText(conceptText(d))}>Copy as text</button>
      <button className="btn btn--ghost btn--sm" onClick={() => window.print()}>Print</button>
    </article>
  )
}

export function conceptText(d: ConceptDoc): string {
  const c = d.concept
  return [c.working_title, '', 'Problem and significance', c.problem_and_significance, '', 'Aims', ...c.aims.map((a, i) => `${i + 1}. ${a}`), '',
    'Approach', c.approach, '', 'Team and proposed roles', ...c.team_roles.map(r => `- ${r}`), '', 'Partnerships', c.partnerships, '',
    'Fit with the call', ...c.requirement_fit.map(r => `- ${r.requirement} -> ${r.how_addressed}`), '', 'YIGH alignment', c.yigh_alignment, '',
    'Open questions', ...c.open_questions.map(q => `- ${q}`), ...(d.generated_by.startsWith('ai') ? ['', `(${d.label})`] : [])].join('\n')
}
