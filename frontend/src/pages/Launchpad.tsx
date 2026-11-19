import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { api, launchpad, radar, type ConceptDoc, type Workspace } from '../api'
import { hub, type Plan } from '../hub'
import { useAuth } from '../auth'
import { Deadline } from '../components/OppCardView'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { useAsync, useDebounced } from '../hooks'
import { HubIcon } from '../components/HubIcon'
import { SaveButton } from '../components/SaveButton'
import { useProject } from '../project'
import { ConceptView } from './OpportunityPage'
import { FacilitiesBuilder, Letters } from './HubTools'

/** Toolkit: tick what you need; each choice opens its own panel. A funding call is optional
 *  (needed only for the one-pager and for suggestions matched to a call). State lives in the address: ?need=a,b&opp=ID */

// The stage of the project decides which Yale steps and which follow-up tools are shown.
const STAGES = [
  { key: 'idea', label: 'Exploring an idea', text: 'Looking for people, partners and funding to get started.', icon: '💡' },
  { key: 'applying', label: 'Applying for a grant', text: 'Writing a proposal for a specific call, or about to.', icon: '📝' },
  { key: 'awarded', label: 'Just won a grant', text: 'Funded and getting the project set up at Yale.', icon: '🏆' },
  { key: 'implementing', label: 'Running the project', text: 'Need implementation support: paying, buying, shipping, travel.', icon: '⚙️' },
  { key: 'sharing', label: 'Sharing results', text: 'Publishing, sharing data and closing out.', icon: '📣' },
] as const
type Stage = typeof STAGES[number]['key']
const APPLYING = (s: string) => s === 'idea' || s === 'applying'
const STEP_NAMES = ['Your stage', 'Your project', 'Matches', 'Yale steps', 'Your plan']
const DESC_KEY = 'launchpad-desc', TEAM_KEY = 'launchpad-team', LETTER_KEY = 'launchpad-letter'
const appliesKey = (stage: string) => `launchpad-applies-${stage}`
const LETTER_INFO_KEY = 'launchpad-letter-info'
interface Fact { value: string; quote: string }
interface LetterNeed { slug: string; title: string; quote: string; guide: { title: string; path: string }; office: { name: string | null; email: string | null; url: string | null } }
interface LetterInfo { facts: Record<string, Fact | Fact[] | string>; needs: LetterNeed[]; method: 'ai' | 'rules'; file: string }
const FACT_LABELS: [string, string][] = [['project_title', 'Project'], ['funder', 'Funder'], ['award_number', 'Award number'], ['principal_investigator', 'Principal investigator'],
  ['project_period', 'Project period'], ['amount', 'Amount'], ['countries', 'Countries'], ['partner_institutions', 'Partner institutions']]
const readList = <T,>(key: string, fallback: T[] = []): T[] => { try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback } catch { return fallback } }

/** The project the person described or picked, shared by the steps and the plan page. Kept in the address and this browser. */
function useProjectState() {
  const [params] = useSearchParams()
  const id = Number(params.get('opp')) || null
  const stage = (params.get('stage') ?? (id ? 'applying' : '')) as Stage | ''
  const mode = params.get('mode') ?? 'call'          // call | link | describe
  const [desc, setDesc] = useState(() => localStorage.getItem(DESC_KEY) ?? '')
  const [team, setTeam] = useState<number[]>(() => readList<number>(TEAM_KEY))
  const toggleTeam = (fid: number) => { const t = team.includes(fid) ? team.filter(x => x !== fid) : [...team, fid]; setTeam(t); localStorage.setItem(TEAM_KEY, JSON.stringify(t)) }
  const [letter, setLetter] = useState(() => localStorage.getItem(LETTER_KEY) ?? '')
  const textMode = mode === 'describe' || mode === 'upload'          // matched on text, not on a funding call
  const projectText = mode === 'describe' ? desc.trim() : mode === 'upload' ? letter.trim() : ''
  const hasProject = textMode ? projectText.length >= 20 : !!id
  const query = (step?: number) => {
    const p = new URLSearchParams()
    if (stage) p.set('stage', stage)
    if (mode !== 'call') p.set('mode', mode)
    if (id) p.set('opp', String(id))
    if (step) p.set('step', String(step))
    return p.toString()
  }
  return { params, id, stage, mode, desc, setDesc, letter, setLetter, textMode, team, toggleTeam, hasProject, projectText, query }
}

export function Launchpad() {
  const [, setParams] = useSearchParams()
  const navigate = useNavigate()
  const { params, id, stage, mode, desc, setDesc, letter, setLetter, textMode, team, toggleTeam, hasProject, projectText, query } = useProjectState()
  // no step in the address: start at the beginning, or at "Your project" when arriving from an opportunity page
  const step = Number(params.get('step') ?? (id ? 2 : 0)) || 0

  const go = (next: { stage?: string; opp?: number | null; mode?: string; step?: number }) => {
    const p = new URLSearchParams()
    const st = next.stage ?? stage, oo = next.opp === undefined ? id : next.opp, mo = next.mode ?? mode, sp = next.step ?? step
    if (st) p.set('stage', st)
    if (mo !== 'call') p.set('mode', mo)
    if (oo) p.set('opp', String(oo))
    if (sp === 5) { navigate(`/launchpad/plan?${p}`); return }     // the plan is its own page
    if (sp) p.set('step', String(sp))
    setParams(p)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
  // matches and Yale steps: fetched once the project is known and the person has moved past "Your project"
  const wantPlan = !!stage && hasProject && step >= 3
  const [planState, retryPlan] = useAsync<Plan | null>(() => wantPlan ? hub.plan({ stage, text: projectText, opportunity_id: textMode ? null : id }) : Promise.resolve(null),
    [wantPlan, stage, mode, id, projectText])
  const cur = step >= 1 && step <= 4 ? step : 0
  if (step === 5) return <Navigate to={`/launchpad/plan?${query()}`} replace />   // old links to the last step
  const canNext = cur === 1 ? !!stage : cur === 2 ? hasProject : true

  return (
    <div className="page osf launch">
      <header className="osf-head">
        <div className="osf-head__inner">
          <p className="eyebrow eyebrow--light">Toolkit</p>
          <h1>{cur === 0 ? 'Plan your project with YIGH' : STEP_NAMES[cur - 1]}</h1>
          <p className="lede">{[
            'Tell us where your project is and what it’s about. We’ll suggest Yale collaborators, partner organizations, Yale resources and the Yale steps you’ll need, then help with a one-pager, letters of support or contacting a team.',
            'Where is your project right now?',
            'Pick a funding call, paste a link to one, describe your project, or upload your award letter.',
            'Suggestions from public Yale profiles and pages. Nobody has been contacted. Tick people to add them to your team.',
            'Tick every step that applies to your project, then press Next. Each one opens a guide with the Yale office to contact.',
          ][cur]}</p>
          {cur === 0 && <button className="btn btn--lg wiz__go" onClick={() => go({ step: 1 })}>Get started →</button>}
        </div>
      </header>

      {cur > 0 && (
        <ol className="wiz" aria-label="Steps">
          {STEP_NAMES.map((n, i) => {
            const reachable = i + 1 <= 2 || (!!stage && hasProject)
            return <li key={n} className={`wiz__s ${i + 1 < cur ? 'is-done' : ''} ${i + 1 === cur ? 'is-on' : ''}`}>
              <button disabled={!reachable} onClick={() => go({ step: i + 1 })} aria-current={i + 1 === cur ? 'step' : undefined}><span>{i + 1 < cur ? '✓' : i + 1}</span>{n}</button></li>
          })}
        </ol>
      )}

      {cur === 0 && <><Saved onUse={opp => go({ opp, mode: 'call', step: 1 })} current={id} /><ToolsToGetItDone /></>}

      {cur === 1 && (
        <section className="stage-pick wiz__panel" role="radiogroup" aria-label="Project stage">
          {STAGES.map(s => (
            <button key={s.key} role="radio" aria-checked={stage === s.key} className={`stage-pick__opt ${stage === s.key ? 'is-on' : ''}`}
                    onClick={() => go({ stage: s.key, step: 2 })}>
              <span className="stage-pick__icon" aria-hidden>{s.icon}</span><strong>{s.label}</strong><span>{s.text}</span></button>
          ))}
        </section>
      )}

      {cur === 2 && (
        <section className="launch__sec wiz__panel">
          <div className="seg" role="tablist" aria-label="How to describe your project">
            {[['call', 'Pick a funding call'], ['link', 'Paste a link'], ['describe', 'Describe my project'], ['upload', 'Upload award letter']].map(([k, l]) => (
              <button key={k} role="tab" aria-selected={mode === k} className={mode === k ? 'is-on' : ''} onClick={() => go({ mode: k })}>{l}</button>))}
          </div>
          {stage === 'awarded' && mode !== 'upload' && <p className="muted small">Already funded? Pick the call you won, upload your award letter, or describe the project, and we’ll focus on setting it up.</p>}
          {mode === 'upload' ? (
            <AwardLetter text={letter} onText={t => { setLetter(t); localStorage.setItem(LETTER_KEY, t) }}
                         onRead={() => { if (APPLYING(stage)) go({ stage: 'awarded' }) }} stageNote={APPLYING(stage)} />
          ) : mode === 'describe' ? (
            <label className="fb__field">In a paragraph: what, where and with whom?
              <textarea className="input" rows={6} value={desc} maxLength={4000} aria-label="Project description"
                        onChange={e => { setDesc(e.target.value); localStorage.setItem(DESC_KEY, e.target.value) }}
                        placeholder="e.g. A study of maternal health in rural Kenya, enrolling pregnant women at three clinics and collecting blood samples, working with a local research institute." />
              <span className="muted small">{desc.trim().length < 20 ? 'A few sentences is enough.' : `${desc.trim().split(/\s+/).length} words`}</span></label>
          ) : (
            <>{id && <Chosen id={id} onClear={() => go({ opp: null })} />}
              <Picker selected={id} onPick={opp => go({ opp })} only={mode === 'link' ? 'link' : 'list'} all={!APPLYING(stage)} /></>
          )}
        </section>
      )}

      {cur >= 3 && cur <= 4 && (
        planState.status === 'loading' || (planState.status === 'success' && !planState.data) ? <Loading label="Matching your project to Yale people, partners and resources…" />
          : planState.status === 'error' ? <ErrorState message={planState.error} onRetry={retryPlan} />
          : cur === 3 ? <Matches plan={planState.data!} team={team} toggleTeam={toggleTeam} />
          : <YaleSteps plan={planState.data!} stage={stage} />
      )}

      {cur > 0 && (
        <nav className="wiz__nav" aria-label="Step navigation">
          <button className="btn btn--ghost" onClick={() => go({ step: cur - 1 })}>← Back</button>
          <span className="muted small">Step {cur} of 4</span>
          <button className="btn" disabled={!canNext} onClick={() => go({ step: cur + 1 })}>
            {canNext ? (cur === 4 ? 'Next: see my plan →' : `Next: ${STEP_NAMES[cur]} →`) : cur === 1 ? 'Pick a stage' : 'Add your project first'}</button>
        </nav>
      )}
    </div>
  )
}

function Matches({ plan, team, toggleTeam }: { plan: Plan; team: number[]; toggleTeam: (id: number) => void }) {
  return (
    <div className="wiz__panel matches">
      {plan.opportunity && <p className="muted small">Matched to: <Link to={`/radar/${plan.opportunity.id}`}>{plan.opportunity.title}</Link></p>}
      <section className="launch__sec"><h2>Possible Yale collaborators</h2>
        {plan.faculty.length === 0 ? <p className="muted">No close matches. Try adding a topic or place to your description, or <Link to="/directory">browse the Faculty Directory</Link>.</p>
          : <ul className="mlist">{plan.faculty.map(f => (
            <li key={f.id} className={team.includes(f.id) ? 'is-on' : ''}>
              <label className="mlist__pick"><input type="checkbox" checked={team.includes(f.id)} onChange={() => toggleTeam(f.id)} /> Add to my team</label>
              <Link to={`/faculty/${f.id}`}><strong>{f.name}</strong></Link>
              <span className="muted small">{[f.title, f.school].filter(Boolean).join(' · ')}</span>
              {f.why.length > 0 && <span className="mlist__why">Matches: {f.why.join(', ')}</span>}
            </li>))}</ul>}
      </section>
      <section className="launch__sec"><h2>Partner organizations</h2>
        {plan.partners.length === 0 ? <p className="muted">No organizations matched. Mention a country in your description, or <Link to="/partners">browse partners</Link>.</p>
          : <ul className="mlist">{plan.partners.map(o => (
            <li key={o.id}>
              {o.website ? <a href={o.website} target="_blank" rel="noreferrer"><strong>{o.name}</strong> ↗</a> : <strong>{o.name}</strong>}
              <span className="muted small">{[o.country, o.type.replace(/_/g, ' ')].filter(Boolean).join(' · ')}{' '}
                <span className={`rel rel--${o.works_with_yale ? 'documented' : 'proposed'}`}>{o.works_with_yale ? 'Works with Yale' : 'No Yale link found yet'}</span></span>
              {o.why.length > 0 && <span className="mlist__why">Matches: {o.why.join(', ')}</span>}
              <SaveButton small item={{ kind: 'partner', id: o.id, title: o.name, sub: o.country, url: o.website }} />
            </li>))}</ul>}
      </section>
      <section className="launch__sec"><h2>Yale resources that fit</h2>
        <ul className="mlist">{plan.resources.map(r => (
          <li key={r.id}><a href={r.url} target="_blank" rel="noreferrer"><strong>{r.name}</strong> ↗</a><span className="small">{r.text}</span></li>))}</ul>
        <p className="muted small">Need these in a grant? The Facilities builder in Next actions turns them into a section.</p>
      </section>
    </div>
  )
}

/** Read an award letter in the browser's request only: the server extracts the text and keeps nothing. */
function AwardLetter({ text, onText, onRead, stageNote }: { text: string; onText: (t: string) => void; onRead: () => void; stageNote: boolean }) {
  const [state, setState] = useState<{ s: 'idle' | 'reading' | 'error'; msg?: string; note?: string }>({ s: 'idle' })
  const [info, setInfo] = useState<LetterInfo | null>(() => text ? readInfo() : null)
  const read = async (f: File | undefined) => {
    if (!f) return
    setState({ s: 'reading' })
    try {
      const r = await fetch(`/api/hub/award-letter?filename=${encodeURIComponent(f.name)}`, { method: 'POST', body: f, headers: { 'content-type': 'application/octet-stream' } })
      const d = await r.json()
      if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : 'We couldn’t read that file.')
      onText(d.text)
      const li: LetterInfo = { facts: d.facts, needs: d.needs, method: d.method, file: f.name }
      localStorage.setItem(LETTER_INFO_KEY, JSON.stringify(li)); setInfo(li)
      // the agreements the letter points to start ticked on the Yale steps page
      localStorage.setItem(appliesKey('awarded'), JSON.stringify(d.needs.map((n: LetterNeed) => n.slug)))
      setState({ s: 'idle', note: `Read ${f.name}. The file wasn’t saved.` })
      onRead()
    } catch (e) { setState({ s: 'error', msg: (e as Error).message }) }
  }
  return (
    <div className="award">
      {stageNote && <p className="muted small">An award letter means you’ve been funded, so we’ll switch your stage to “Just won a grant” after reading it.</p>}
      <label className={`award__drop ${state.s === 'reading' ? 'is-busy' : ''}`}
             onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); read(e.dataTransfer.files[0]) }}>
        <input type="file" accept=".pdf,.docx,.txt,application/pdf" onChange={e => read(e.target.files?.[0])} aria-label="Award letter file" />
        <strong>{state.s === 'reading' ? 'Reading your letter…' : 'Choose your award letter, or drop it here'}</strong>
        <span className="muted small">PDF, Word (.docx) or text, up to 8 MB. We only read the text to match your project; the file isn’t saved.</span>
      </label>
      {state.s === 'error' && <p className="signin__err" role="alert">{state.msg}</p>}
      {state.note && <p className="small" role="status">✓ {state.note}</p>}
      {info && <LetterSummary info={info} />}
      {text && <details className="award__text"><summary>Text we’ll use to find matches (you can edit it)</summary>
        <textarea className="input" rows={8} value={text} maxLength={4000} onChange={e => onText(e.target.value)} aria-label="Award letter text" /></details>}
    </div>
  )
}

const readInfo = (): LetterInfo | null => { try { return JSON.parse(localStorage.getItem(LETTER_INFO_KEY) ?? 'null') } catch { return null } }

/** What the reader found in an award letter, each fact with the line it came from, and the agreements it points to. */
function LetterSummary({ info, compact = false }: { info: LetterInfo; compact?: boolean }) {
  const facts = FACT_LABELS.map(([k, label]) => {
    const v = info.facts[k]
    if (!v || (Array.isArray(v) && !v.length)) return null
    const list = Array.isArray(v) ? v : [v as Fact]
    return <div key={k} className="lfact"><dt>{label}</dt><dd>{list.map(f => f.value).join(', ')}
      <span className="lfact__q" title={list.map(f => f.quote).join('\n')}>“{list[0].quote}”</span></dd></div>
  }).filter(Boolean)
  return (
    <section className="lsum" aria-label="From your award letter">
      <h3>{compact ? 'From your award letter' : 'What we found in your letter'} <span className="muted small">({info.method === 'ai' ? 'read by our AI agent' : 'read automatically'}; check against your letter)</span></h3>
      {typeof info.facts.summary === 'string' && info.facts.summary && <p>{info.facts.summary}</p>}
      {facts.length ? <dl className="lfacts">{facts}</dl> : <p className="muted small">We couldn’t find the usual award details. The matches will use the letter’s text.</p>}
      {info.needs.length > 0 && <>
        <h3>Agreements and approvals you may need</h3>
        <ul className="lneeds">{info.needs.map(n => (
          <li key={n.slug}><strong>{n.title}</strong>
            <span className="lfact__q">Because: “{n.quote}”</span>
            <span className="small">Contact: {n.office.name ?? 'see the guide'}{n.office.email && <> · <a href={`mailto:${n.office.email}`}>{n.office.email}</a></>}
              {!n.office.email && n.office.url && <> · <a href={n.office.url} target="_blank" rel="noreferrer">office page ↗</a></>} · <Link to={n.guide.path}>Read the guide →</Link></span></li>))}</ul>
      </>}
    </section>
  )
}

const TOOLS = [
  { to: '/radar', title: 'Funding opportunities', text: 'Open funding calls, checked against each funder’s own page.' },
  { to: '/directory', title: 'Faculty Directory', text: 'Find Yale faculty by topic, place or priority.' },
  { to: '/partners', title: 'Partner organizations', text: 'Organizations around the world, and which already work with Yale.' },
  { to: '/launchpad/facilities', title: 'Facilities & Resources builder', text: 'Put together the Facilities section of a grant from Yale resources.' },
  { to: '/launchpad/letters', title: 'Letters of support', text: 'Request a letter, and get templates and checklists.' },
]

/** "Resources on this page" (moved here from the Pathways page): each tool on its own, without the step-by-step. */
function ToolsToGetItDone() {
  return (
    <section className="hub-tools">
      <h2 className="home-sec__title">Resources on this page</h2>
      <div className="hub-tools__grid">
        {TOOLS.map(t => <Link key={t.to} to={t.to} className="hub-tool"><HubIcon name="tools" size={22} /><strong>{t.title}</strong><span>{t.text}</span></Link>)}
      </div>
    </section>
  )
}

function YaleSteps({ plan, stage }: { plan: Plan; stage: string }) {
  // steps the project text points to start ticked; the person ticks the rest that apply
  const [applies, setApplies] = useState<string[]>(() => readList<string>(appliesKey(stage), plan.steps.filter(x => x.why.startsWith('Your project')).map(x => x.slug)))
  useEffect(() => { localStorage.setItem(appliesKey(stage), JSON.stringify(applies)) }, [applies, stage])
  const tick = (slug: string) => setApplies(a => a.includes(slug) ? a.filter(x => x !== slug) : [...a, slug])
  return (
    <section className="launch__sec wiz__panel">
      <div className="ysteps__bar"><p className="small"><strong>{plan.stage_label}</strong> · {applies.length} of {plan.steps.length} selected</p>
        <span><button className="link-btn small" onClick={() => setApplies(plan.steps.map(x => x.slug))}>Select all</button> · <button className="link-btn small" onClick={() => setApplies([])}>Clear</button></span></div>
      <ul className="ysteps">{plan.steps.map(s => (
        <li key={s.slug} className={applies.includes(s.slug) ? 'is-on' : ''}>
          <label className="ysteps__pick"><input type="checkbox" checked={applies.includes(s.slug)} onChange={() => tick(s.slug)} aria-label={`${s.title} applies to my project`} /></label>
          <div><strong>{s.title}</strong> <Link className="small" to={s.path}>Read the guide →</Link>
            <p className="small">{s.summary}</p>
            <span className="ysteps__meta">{s.why}{s.office && <> · Office: {s.office}</>}</span></div>
        </li>))}</ul>
    </section>
  )
}

/** /launchpad/plan: everything for the project on one page: people, partners, resources, the Yale steps that apply, and what to do next. */
export function PlanPage() {
  const { id, stage, mode, textMode, team, toggleTeam, hasProject, projectText, query } = useProjectState()
  const [state, retry] = useAsync<Plan | null>(() => stage && hasProject ? hub.plan({ stage, text: projectText, opportunity_id: textMode ? null : id }) : Promise.resolve(null),
    [stage, mode, id, projectText, hasProject])
  const applies = readList<string>(appliesKey(stage))
  if (!stage || !hasProject) return <EmptyState title="Start with your project" action={<Link className="btn" to="/launchpad?step=1">Plan your project</Link>}>Pick your stage and add a funding call or a description first.</EmptyState>
  if (state.status === 'loading' || (state.status === 'success' && !state.data)) return <Loading label="Putting your plan together…" />
  if (state.status === 'error') return <ErrorState message={state.error} onRetry={retry} />
  const plan = state.data!
  const steps = applies.length ? plan.steps.filter(s => applies.includes(s.slug)) : plan.steps
  const picked = plan.faculty.filter(f => team.includes(f.id)), others = plan.faculty.filter(f => !team.includes(f.id))
  return (
    <div className="page osf launch planp">
      <nav className="crumbs small page-crumbs" aria-label="Breadcrumb"><Link to="/">Home</Link> › <Link to={`/launchpad?${query(4)}`}>Toolkit</Link> › <span>Your plan</span></nav>
      <header className="osf-head"><div className="osf-head__inner">
        <p className="eyebrow eyebrow--light">{plan.stage_label}</p>
        <h1>Your project plan</h1>
        <p className="lede">{plan.opportunity ? <>For <Link to={`/radar/${plan.opportunity.id}`}>{plan.opportunity.title}</Link>{plan.opportunity.funder && ` (${plan.opportunity.funder})`}</> : projectText}</p>
        <div className="planp__tools"><Link className="btn btn--ghost" to={`/launchpad?${query(4)}`}>← Edit my answers</Link>
          <button className="btn btn--ghost" onClick={() => window.print()}>🖶 Print or save as PDF</button></div>
      </div></header>

      {mode === 'upload' && readInfo() && <div className="planp__letter"><LetterSummary info={readInfo()!} compact /></div>}
      <div className="planp__grid">
        <section className="launch__sec"><h2>Yale faculty</h2>
          {picked.length > 0 && <><h3 className="planp__sub">Your team</h3><PeopleList list={picked} team={team} toggleTeam={toggleTeam} /></>}
          {others.length > 0 && <><h3 className="planp__sub">{picked.length ? 'Other possible collaborators' : 'Possible collaborators'}</h3><PeopleList list={others} team={team} toggleTeam={toggleTeam} /></>}
          {plan.faculty.length === 0 && <p className="muted">No close matches. <Link to="/directory">Browse the Faculty Directory</Link>.</p>}
        </section>
        <section className="launch__sec"><h2>Partner organizations</h2>
          {plan.partners.length === 0 ? <p className="muted">No organizations matched. <Link to="/partners">Browse partners</Link>.</p>
            : <ul className="plist">{plan.partners.map(o => (
              <li key={o.id}>{o.website ? <a href={o.website} target="_blank" rel="noreferrer"><strong>{o.name}</strong> ↗</a> : <strong>{o.name}</strong>}
                <span className="muted small">{[o.country, o.type.replace(/_/g, ' ')].filter(Boolean).join(' · ')} · {o.works_with_yale ? 'Works with Yale' : 'No Yale link found yet'}</span></li>))}</ul>}
        </section>
        <section className="launch__sec"><h2>Yale resources</h2>
          <ul className="plist">{plan.resources.map(r => <li key={r.id}><a href={r.url} target="_blank" rel="noreferrer"><strong>{r.name}</strong> ↗</a><span className="small">{r.text}</span></li>)}</ul>
        </section>
        <section className="launch__sec"><h2>Your Yale steps</h2>
          {!applies.length && <p className="muted small">You didn’t tick any steps, so all of them are shown. <Link to={`/launchpad?${query(4)}`}>Choose the ones that apply</Link>.</p>}
          <ol className="plist plist--steps">{steps.map(s => <li key={s.slug}><Link to={s.path}><strong>{s.title}</strong></Link><span className="muted small">{s.office ? `Office: ${s.office}` : s.section_title}</span></li>)}</ol>
        </section>
      </div>

      <h2 className="planp__next">What would you like to do next?</h2>
      <Actions stage={stage} id={id} desc={projectText} team={team} toggleTeam={toggleTeam} onPickCall={() => { window.location.href = `/launchpad?${query(2)}` }} />
      <p className="muted small planp__foot">Suggestions come from public Yale profiles and pages. Nobody has been contacted. Check details with each office.</p>
    </div>
  )
}

function PeopleList({ list, team, toggleTeam }: { list: Plan['faculty']; team: number[]; toggleTeam: (id: number) => void }) {
  return <ul className="plist">{list.map(f => (
    <li key={f.id}><Link to={`/faculty/${f.id}`}><strong>{f.name}</strong></Link>
      <span className="muted small">{[f.title, f.school].filter(Boolean).join(' · ')}</span>
      <label className="mlist__pick"><input type="checkbox" checked={team.includes(f.id)} onChange={() => toggleTeam(f.id)} /> On my team</label></li>))}</ul>
}

function Actions({ stage, id, desc, team, toggleTeam, onPickCall }: { stage: string; id: number | null; desc: string; team: number[]; toggleTeam: (id: number) => void; onPickCall: () => void }) {
  const applying = APPLYING(stage)
  const [open, setOpen] = useState<string | null>(applying ? 'onepager' : 'team')
  const needWs = applying && !!id && open === 'onepager'
  const [ws, retryWs] = useAsync<Workspace | null>(() => needWs ? radar.workspace(id!) : Promise.resolve(null), [id, needWs])
  const items: { key: string; title: string; text: string; body: React.ReactNode }[] = [
    ...(applying ? [{ key: 'onepager', title: 'Draft a one-pager', text: 'A one-page concept for your funding call.',
      body: !id ? <NeedCall onPick={onPickCall} /> : ws.status === 'success' && ws.data ? <OnePager id={id} teams={ws.data.teams.map(t => t.name)} />
        : ws.status === 'error' ? <ErrorState message={ws.error} onRetry={retryWs} /> : <Loading label="Getting suggested teams for this call…" /> },
      { key: 'letters', title: 'Get letters of support', text: 'Request a letter from YIGH, or use a template for partners.', body: <Letters embedded /> },
      { key: 'facilities', title: 'Describe Yale’s resources', text: 'Build the Facilities & Other Resources section.', body: <FacilitiesBuilder embedded /> }] : []),
    { key: 'team', title: 'Contact your team', text: team.length ? `${team.length} ${team.length === 1 ? 'person' : 'people'} picked` : 'Pick people in Matches first.',
      body: <ContactTeam team={team} toggleTeam={toggleTeam} desc={desc} stage={stage} /> },
    ...(!applying ? [{ key: 'award', title: stage === 'sharing' ? 'Share and close out' : 'Set up your award', text: 'Your Yale steps, plus help from Nexi.',
      body: <p>Work through <strong>Your Yale steps</strong> above, opening each guide to see who to contact. Not sure which office to call? <button className="link-btn" onClick={() => window.dispatchEvent(new CustomEvent('open-nexi', { detail: 'I just won a grant for global health work abroad. What do I need to set up at Yale?' }))}>Ask Nexi</button>.</p> }] : []),
  ]
  return (
    <div className="wiz__panel acts">
      {stage === 'awarded' && <p className="acts__note">🏆 Congratulations! Since you’re already funded, we’ve left out the proposal tools and focused on setting up your award.</p>}
      {items.map(it => (
        <section key={it.key} className={`acts__item ${open === it.key ? 'is-open' : ''}`}>
          <button className="acts__head" aria-expanded={open === it.key} onClick={() => setOpen(open === it.key ? null : it.key)}>
            <span><strong>{it.title}</strong><span className="muted small">{it.text}</span></span><span aria-hidden>{open === it.key ? '−' : '+'}</span></button>
          {open === it.key && <div className="acts__body">{it.body}</div>}
        </section>
      ))}
    </div>
  )
}

/** Picked people with their public emails, and an email draft that opens in the person's own mail app. Nothing is sent by GRAPPH. */
function ContactTeam({ team, toggleTeam, desc, stage }: { team: number[]; toggleTeam: (id: number) => void; desc: string; stage: string }) {
  const [people] = useAsync(() => Promise.all(team.map(fid => api.facultyDetail(fid))), [team.join(',')])
  if (!team.length) return <p className="muted">Go back to <strong>Matches</strong> and tick “Add to my team” next to the people you’d like to contact.</p>
  if (people.status === 'loading') return <Loading />
  if (people.status === 'error') return <ErrorState message={people.error} />
  const emails = people.data.map(p => p.email).filter(Boolean) as string[]
  const subject = stage === 'awarded' || stage === 'implementing' ? 'Global health project: would you like to be involved?' : 'Possible collaboration on a global health project'
  const body = `Hello,\n\nI found your profile on GRAPPH (Yale Institute for Global Health) and I’m reaching out about a project${desc ? ':\n\n' + desc : '.'}\n\nWould you be open to a short conversation?\n\nThank you,\n`
  return (
    <>
      <ul className="mlist">{people.data.map(p => (
        <li key={p.id}><strong>{p.name}</strong><span className="muted small">{p.title}</span>
          {p.email ? <a className="small" href={`mailto:${p.email}`}>{p.email}</a> : <a className="small" href={p.profile_url} target="_blank" rel="noreferrer">No public email; see profile ↗</a>}
          <button className="link-btn small" onClick={() => toggleTeam(p.id)}>Remove</button></li>))}</ul>
      {emails.length > 0 && <a className="btn" href={`mailto:${emails.join(',')}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`}>
        Open an email draft to {emails.length === 1 ? 'this person' : `all ${emails.length}`} ✉</a>}
      <p className="muted small">This opens a draft in your own email app for you to edit and send. GRAPPH doesn’t send anything or tell anyone you looked.</p>
    </>
  )
}

function Saved({ onUse, current }: { onUse: (opp: number) => void; current: number | null }) {
  const { items, remove } = useProject()
  if (!items.length) return (
    <p className="saved__hint">Tip: use <strong>+ Add to my project</strong> on any funding call, faculty profile or partner organization
      to collect them here. <Link to="/expertise">Find people</Link> · <Link to="/radar">Find funding</Link> · <Link to="/hub">Browse pathways</Link></p>)
  const groups: [string, typeof items][] = [['Funding', items.filter(i => i.kind === 'funding')],
    ['People', items.filter(i => i.kind === 'faculty')], ['Partners', items.filter(i => i.kind === 'partner')], ['Guides', items.filter(i => i.kind === 'guide')]]
  return (
    <section className="saved" aria-label="Saved to my project">
      <h2>Saved to my project <span className="muted small">(kept in this browser)</span></h2>
      <div className="saved__cols">{groups.map(([t, list]) => (
        <div key={t}><h3>{t}</h3>
          {list.length === 0 ? <p className="muted small">Nothing yet. <Link to={t === 'Funding' ? '/radar' : t === 'People' ? '/directory' : t === 'Guides' ? '/hub' : '/partners'}>Find {t.toLowerCase()} →</Link></p>
            : <ul>{list.map(i => (
              <li key={`${i.kind}-${i.id}`}>
                {i.kind === 'guide' ? <Link to={i.url ?? '/hub'}>{i.title}</Link> : i.kind === 'funding' ? <Link to={`/radar/${i.id}`}>{i.title}</Link> : i.kind === 'faculty' ? <Link to={`/faculty/${i.id}`}>{i.title}</Link>
                  : i.url ? <a href={i.url} target="_blank" rel="noreferrer">{i.title} ↗</a> : <span>{i.title}</span>}
                {i.sub && <span className="muted small">{i.sub}</span>}
                <span className="saved__acts">
                  {i.kind === 'funding' && (current === i.id ? <em className="small">Working on this</em>
                    : <button className="link-btn small" onClick={() => onUse(Number(i.id))}>Work on this call</button>)}
                  <button className="link-btn small" onClick={() => remove(i.kind, i.id)} aria-label={`Remove ${i.title}`}>Remove</button></span>
              </li>))}</ul>}
        </div>))}</div>
    </section>
  )
}

function Chosen({ id, onClear }: { id: number; onClear: () => void }) {
  const [det, retry] = useAsync(() => radar.detail(id), [id])
  if (det.status === 'loading') return <Loading label="Loading opportunity…" />
  if (det.status === 'error') return <ErrorState message={det.error} onRetry={retry} />
  const o = det.data
  return (
    <section className="launch__chosen need__chosen">
      <div><p className="eyebrow">Working on</p>
        <h2><Link to={`/radar/${o.id}`}>{o.title}</Link></h2>
        <p className="small">{o.funder ?? 'Funder not listed'} · <Deadline o={o} />{o.award_text && <> · {o.award_text}</>}</p>
        {o.verification_status !== 'verified' && <p className="small launch__warn">These details come from the page you shared or the funder’s listing. Check them on the funder’s site before applying.</p>}
      </div>
      <button className="btn btn--ghost btn--sm" onClick={onClear}>Clear</button>
    </section>
  )
}

function NeedCall({ onPick }: { onPick: () => void }) {
  return <div className="launchpad__locked"><p>A one-pager is written for a specific funding call. Choose one first, then come back here.</p>
    <button className="btn" onClick={onPick}>Choose a funding call</button></div>
}


// ---------------------------------------------------------------- funding
/** `only`: show just the list or just the link box. `all`: include closed calls (for people who already won one). */
function Picker({ selected, onPick, only, all = false }: { selected: number | null; onPick: (id: number | null) => void; only?: 'list' | 'link'; all?: boolean }) {
  const { user } = useAuth()
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [filter, setFilter] = useState('')
  const [list] = useAsync(() => radar.list({}), [])
  const opps = useMemo(() => list.status === 'success'
    ? list.data.opportunities.filter(o => all || o.status === 'open' || o.status === 'forecasted')
        .filter(o => !filter || `${o.title} ${o.funder ?? ''}`.toLowerCase().includes(filter.toLowerCase()))
        .sort((a, b) => (a.deadline ?? '9999').localeCompare(b.deadline ?? '9999')) : [], [list, filter, all])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!url.trim()) return
    setBusy(true); setMsg(null)
    try { const r = await launchpad.importLink(url.trim()); setMsg({ ok: true, text: r.message }); setUrl(''); onPick(r.id) }
    catch (x) { setMsg({ ok: false, text: (x as Error).message }) }
    finally { setBusy(false) }
  }

  return (
    <div className={only ? '' : 'launch__grid'}>
      {only !== 'link' && <div>
        <h3>{all ? 'Pick your funding call' : 'Pick an open call'}</h3>
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
          {list.status === 'success' && opps.length === 0 && <li className="muted small">No open calls match. Try a broader word (a disease, country or funder), or paste a link to a call below.</li>}
        </ul>
      </div>}
      {only !== 'list' && <div>
        <h3>{only ? 'Paste a link to a call' : 'Or paste a link to a call'}</h3>
        <p className="muted small">A funder’s call page, a Grants.gov listing or an NIH notice.</p>
        {user ? (
          <form className="launch__link" onSubmit={submit}>
            <input className="input" type="url" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://…" aria-label="Opportunity link" />
            <button className="btn" disabled={busy || !url.trim()}>{busy ? 'Reading…' : 'Use this link'}</button>
          </form>
        ) : (
          <p className="launch__locked small"><Link to={`/signin?next=${encodeURIComponent(window.location.pathname + window.location.search)}`}>Sign in</Link> to add a call from a link. Signing in lets us read the page for you and keep the call you add. It’s free with your Yale email.</p>
        )}
        {msg && <p className={`launch__msg ${msg.ok ? '' : 'is-err'}`} role="status">{msg.text}</p>}
      </div>}
    </div>
  )
}

// ---------------------------------------------------------------- people without a call
interface Org { id: number; name: string; type: string; country: string | null; website: string | null; description: string | null; documented_yale_links: unknown[] }

export function PartnerSearch() {
  const [q, setQ] = useState('')
  const dq = useDebounced(q.trim(), 300)
  const [all] = useAsync(() => fetch('/api/partners').then(r => r.json()) as Promise<{ partners: Org[] }>, [])
  const rows = all.status === 'success' ? all.data.partners.filter(o => !dq || `${o.name} ${o.country ?? ''} ${o.type} ${o.description ?? ''}`.toLowerCase().includes(dq.toLowerCase())) : []
  return (
    <>
      <input className="input need__input" type="search" value={q} onChange={e => setQ(e.target.value)}
             placeholder="A country, topic or organization, e.g. Kenya, ministry, university" aria-label="Search partner organizations" />
      {all.status === 'loading' && <Loading />}
      {all.status === 'success' && <>
        {rows.length === 0 ? <p className="muted">No organizations match “{dq}”. Try a country name or a type such as “university” or “ministry”.</p>
          : <p className="muted small">{rows.length} organization{rows.length === 1 ? '' : 's'}{dq && ' match'}.</p>}
        <ul className="launch__people need__people">{rows.slice(0, 12).map(o => (
          <li key={o.id}>{o.website ? <a href={o.website} target="_blank" rel="noreferrer"><strong>{o.name}</strong> ↗</a> : <strong>{o.name}</strong>}
            <span className="muted small">{[o.country, o.type].filter(Boolean).join(' · ')}{' '}
              <span className={`rel rel--${o.documented_yale_links.length ? 'documented' : 'proposed'}`}>{o.documented_yale_links.length ? 'Works with Yale' : 'No Yale link found yet'}</span></span>
            <SaveButton small item={{ kind: 'partner', id: o.id, title: o.name, sub: [o.country, o.type].filter(Boolean).join(' · '), url: o.website }} />
          </li>))}</ul>
      </>}
    </>
  )
}

// ---------------------------------------------------------------- matched to a call
// ---------------------------------------------------------------- one-pager
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
    <div id="one-pager">
      <p className="muted small">Write a few bullet points about what you want to accomplish. We’ll shape them into a one-page concept that lines up
        with what the call asks for, using the team you choose. Nothing is made up about anyone.</p>
      {!ready ? null : !user ? (
        <div className="launchpad__locked"><p><strong>Sign in to draft a one-pager.</strong> Drafting uses the AI writer, so it’s limited to Yale users, and signing in keeps your draft tied to you. Create a free account with your Yale email; it takes under a minute.</p>
          <Link className="btn" to={`/signin?next=${encodeURIComponent(window.location.pathname + window.location.search)}`}>Sign in</Link></div>
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
    </div>
  )
}
