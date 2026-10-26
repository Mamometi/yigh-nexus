import { useMemo, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { launchpad, radar, type ConceptDoc, type Workspace } from '../api'
import { useAuth } from '../auth'
import { Deadline } from '../components/OppCardView'
import { ErrorState, Loading } from '../components/StateViews'
import { useAsync } from '../hooks'
import { ConceptView } from './OpportunityPage'

export function Launchpad() {
  const [params, setParams] = useSearchParams()
  const id = Number(params.get('opp')) || null
  const choose = (n: number | null) => { const p = new URLSearchParams(params); n ? p.set('opp', String(n)) : p.delete('opp'); setParams(p) }

  return (
    <div className="page launch osf">
      <header className="osf-head">
        <div className="osf-head__inner">
          <p className="eyebrow eyebrow--light">Team Launchpad</p>
          <h1>From a funding call to a team and a draft</h1>
          <p className="lede">Pick a funding opportunity, see which Yale faculty and partner organizations could work on it with you,
            then turn your ideas into a one-page concept to share.</p>
          <ol className="launch__steps" aria-label="Steps">
            <li className={!id ? 'is-on' : 'is-done'}><span>1</span>Choose an opportunity</li>
            <li className={id ? 'is-on' : ''}><span>2</span>Find people to reach out to</li>
            <li className={id ? 'is-on' : ''}><span>3</span>Draft a one-pager</li>
          </ol>
        </div>
        <svg className="wave" viewBox="0 0 1440 80" preserveAspectRatio="none" aria-hidden><path d="M0,40 C360,90 1080,-10 1440,40 L1440,80 L0,80 Z" /></svg>
      </header>

      <Picker selected={id} onPick={choose} />
      {id && <Workspace key={id} id={id} />}
    </div>
  )
}

function Picker({ selected, onPick }: { selected: number | null; onPick: (id: number | null) => void }) {
  const { user } = useAuth()
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [filter, setFilter] = useState('')
  const [list] = useAsync(() => radar.list({}), [])
  const opps = useMemo(() => list.status === 'success'
    ? list.data.opportunities.filter(o => o.status === 'open' || o.status === 'forecasted')
        .filter(o => !filter || `${o.title} ${o.funder ?? ''}`.toLowerCase().includes(filter.toLowerCase()))
        .sort((a, b) => (a.deadline ?? '9999').localeCompare(b.deadline ?? '9999')) : [], [list, filter])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!url.trim()) return
    setBusy(true); setMsg(null)
    try { const r = await launchpad.importLink(url.trim()); setMsg({ ok: true, text: r.message }); setUrl(''); onPick(r.id) }
    catch (x) { setMsg({ ok: false, text: (x as Error).message }) }
    finally { setBusy(false) }
  }

  return (
    <section className="launch__pick" aria-label="Choose an opportunity">
      <div className="launch__col">
        <h2><span className="launch__n">1a</span>Paste a link</h2>
        <p className="muted small">A funder’s call page, a Grants.gov listing or an NIH notice.</p>
        {user ? (
          <form className="launch__link" onSubmit={submit}>
            <input className="input" type="url" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://…" aria-label="Opportunity link" />
            <button className="btn" disabled={busy || !url.trim()}>{busy ? 'Reading…' : 'Use this link'}</button>
          </form>
        ) : (
          <p className="launch__locked small"><Link to="/signin?next=/launchpad">Sign in</Link> to add an opportunity from a link.</p>
        )}
        {msg && <p className={`launch__msg ${msg.ok ? '' : 'is-err'}`} role="status">{msg.text}</p>}
      </div>
      <div className="launch__or" aria-hidden>or</div>
      <div className="launch__col">
        <h2><span className="launch__n">1b</span>Pick from the Opportunities hub</h2>
        <input className="input" type="search" value={filter} onChange={e => setFilter(e.target.value)} placeholder="Search open opportunities" aria-label="Search opportunities" />
        {list.status === 'loading' && <Loading label="Loading opportunities…" />}
        {list.status === 'error' && <ErrorState message={list.error} />}
        <ul className="launch__list" role="listbox" aria-label="Open opportunities">
          {opps.map(o => (
            <li key={o.id} role="option" aria-selected={o.id === selected}>
              <button className={o.id === selected ? 'is-on' : ''} onClick={() => onPick(o.id)}>
                <strong>{o.title}</strong><span className="muted small">{o.funder} · <Deadline o={o} /></span>
              </button>
            </li>
          ))}
          {list.status === 'success' && opps.length === 0 && <li className="muted small">No open opportunities match.</li>}
        </ul>
      </div>
    </section>
  )
}

function Workspace({ id }: { id: number }) {
  const [det, retryDet] = useAsync(() => radar.detail(id), [id])
  const [ws, retry] = useAsync(() => radar.workspace(id), [id])
  if (det.status === 'loading') return <Loading label="Loading opportunity…" />
  if (det.status === 'error') return <ErrorState message={det.error} onRetry={retryDet} />
  const o = det.data
  return (
    <>
      <section className="launch__chosen">
        <p className="eyebrow">Your opportunity</p>
        <h2><Link to={`/radar/${o.id}`}>{o.title}</Link></h2>
        <p className="small">{o.funder ?? 'Funder not listed'} · <Deadline o={o} />{o.award_text && <> · {o.award_text}</>}</p>
        {o.verification_status !== 'verified' && <p className="small launch__warn">These details come from the page you shared or the funder’s listing. Check them on the funder’s site before applying.</p>}
      </section>

      {ws.status === 'loading' && <section className="launch__sec"><h2><span className="launch__n">2</span>People to reach out to</h2>
        <Loading label="Matching Yale faculty and partner organizations to this call… (the first time can take up to a minute)" /></section>}
      {ws.status === 'error' && <section className="launch__sec"><ErrorState message={ws.error} onRetry={retry} /></section>}
      {ws.status === 'success' && <People w={ws.data} id={id} />}
    </>
  )
}

function People({ w, id }: { w: Workspace; id: number }) {
  const partners = w.external_partners.teams[0]?.partners ?? []
  return (
    <>
      <section className="launch__sec">
        <h2><span className="launch__n">2</span>People to reach out to</h2>
        <p className="muted small">Suggestions based on public Yale profiles. Nobody has been contacted, and nothing here means they’re available or interested.</p>
        <div className="launch__grid">
          <div>
            <h3>Yale faculty</h3>
            {w.recommended_faculty.length === 0 ? <p className="muted">We couldn’t find Yale faculty whose profiles match this call.</p> : (
              <ul className="launch__people">{w.recommended_faculty.map(f => (
                <li key={f.faculty_id}>
                  <Link to={`/faculty/${f.faculty_id}`}><strong>{f.name}</strong></Link>
                  <span className="muted small">{[f.title, f.school].filter(Boolean).join(' · ')}</span>
                  <p className="small">{f.explanation.text}</p>
                </li>))}</ul>
            )}
            {w.teams.length > 0 && <>
              <h3>Team ideas</h3>
              <ul className="launch__teams">{w.teams.map(t => (
                <li key={t.name}><strong>{t.name}</strong><span className="small"> · {t.members.map(m => m.name.split(',')[0]).join(', ')}</span>
                  <p className="muted small">{t.complementarity.text}</p></li>))}</ul>
            </>}
          </div>
          <div>
            <h3>Organizations to work with</h3>
            {partners.length === 0 ? <p className="muted">{w.external_partners.teams[0]?.collaboration_gaps[0] ?? 'No partner organizations suggested for this call.'}</p> : (
              <ul className="launch__people">{partners.map(p => (
                <li key={p.organization_id}>
                  {p.website ? <a href={p.website} target="_blank" rel="noreferrer"><strong>{p.name}</strong> ↗</a> : <strong>{p.name}</strong>}
                  <span className="muted small">{p.country}{' '}<span className={`rel rel--${p.relationship.status}`}>{p.relationship.status === 'documented' ? 'Connected to Yale' : 'New suggestion'}</span></span>
                  <p className="small">{p.why_relevant}</p>
                </li>))}</ul>
            )}
            {w.eligibility_and_collaboration_gaps.length > 0 && <>
              <h3>Worth checking</h3>
              <ul className="launch__gaps small">{w.eligibility_and_collaboration_gaps.slice(0, 5).map(g => <li key={g}>{g}</li>)}</ul>
            </>}
          </div>
        </div>
      </section>

      <OnePager id={id} teams={w.teams.map(t => t.name)} />
    </>
  )
}

function OnePager({ id, teams }: { id: number; teams: string[] }) {
  const { user, ready } = useAuth()
  const [goals, setGoals] = useState('')
  const [team, setTeam] = useState(teams[0] ?? '')
  const [state, setState] = useState<{ s: 'idle' | 'loading' } | { s: 'error'; e: string } | { s: 'done'; d: ConceptDoc }>({ s: 'idle' })
  const list = goals.split('\n').map(g => g.replace(/^\s*[-*•\d.)]+\s*/, '').trim()).filter(Boolean)
  const run = async (e?: FormEvent) => {
    e?.preventDefault()
    setState({ s: 'loading' })
    try { setState({ s: 'done', d: await launchpad.onePager(id, list, team || undefined) }) }
    catch (x) { setState({ s: 'error', e: (x as Error).message }) }
  }
  return (
    <section className="launch__sec" id="one-pager">
      <h2><span className="launch__n">3</span>Draft a one-pager</h2>
      <p className="muted small">Write a few bullet points about what you want to accomplish. We’ll shape them into a one-page concept that lines up
        with what the call asks for, using the team you choose. Nothing is made up about anyone.</p>
      {!ready ? null : !user ? (
        <div className="launchpad__locked"><p><strong>Sign in to draft a one-pager.</strong> It’s available to signed-in Yale users.</p>
          <Link className="btn" to={`/signin?next=${encodeURIComponent(`/launchpad?opp=${id}#one-pager`)}`}>Sign in</Link></div>
      ) : (
        <form className="launch__form" onSubmit={run}>
          <label htmlFor="lp-goals" className="osf-label">What do you want to accomplish? (one point per line)</label>
          <textarea id="lp-goals" className="input" rows={5} value={goals} onChange={e => setGoals(e.target.value)}
                    placeholder={'- Map heat-related illness in two cities\n- Test an early-warning text message system\n- Train community health workers'} />
          <div className="launch__row">
            {teams.length > 0 && <label className="small">Team <select value={team} onChange={e => setTeam(e.target.value)}>{teams.map(t => <option key={t}>{t}</option>)}</select></label>}
            <span className="muted small">{list.length} point{list.length === 1 ? '' : 's'}</span>
            <button className="btn" disabled={state.s === 'loading' || teams.length === 0}>{state.s === 'loading' ? 'Drafting…' : 'Draft my one-pager'}</button>
          </div>
          {teams.length === 0 && <p className="muted small">A one-pager needs at least one suggested team, and none could be put together for this call.</p>}
        </form>
      )}
      {state.s === 'error' && <ErrorState message={state.e} onRetry={() => run()} />}
      {state.s === 'done' && <ConceptView d={state.d} />}
    </section>
  )
}
