import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { radar, type OppDetail } from '../api'
import { useAuth } from '../auth'
import { ErrorState, Loading } from '../components/StateViews'
import { hub, type LetterRequest } from '../hub'
import { useAsync } from '../hooks'

const WAVE = <svg className="wave" viewBox="0 0 1440 80" preserveAspectRatio="none" aria-hidden><path d="M0,40 C360,90 1080,-10 1440,40 L1440,80 L0,80 Z" /></svg>
/** The Launchpad opportunity these tools are working on (?opp=ID), if any */
function useLaunchOpp(): OppDetail | null {
  const [params] = useSearchParams()
  const id = Number(params.get('opp')) || null
  const [o, setO] = useState<OppDetail | null>(null)
  useEffect(() => { if (id) radar.detail(id).then(setO).catch(() => setO(null)) }, [id])
  return id ? o : null
}

function LaunchContext({ o }: { o: OppDetail | null }) {
  if (!o) return <p className="small muted">Tip: start from the <Link to="/launchpad?stage=applying&step=2">Toolkit</Link> and pick a funding call, and this page fills it in for you.</p>
  return (
    <div className="lp-ctx"><span><span className="eyebrow">Working on</span><br /><strong>{o.title}</strong>{o.funder && <span className="muted"> · {o.funder}</span>}</span>
      <Link className="btn btn--ghost btn--sm" to={`/launchpad?stage=applying&opp=${o.id}&step=5`}>← Back to your plan</Link></div>
  )
}

const CATS: [string, string][] = [['institutes', 'Institutes and schools'], ['computing', 'Computing'], ['data', 'Data and library'],
                                  ['labs', 'Labs and core facilities'], ['support', 'Research support']]

function download(name: string, text: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
  a.download = name
  a.click()
  URL.revokeObjectURL(a.href)
}

function Copy({ text }: { text: string }) {
  const [done, setDone] = useState(false)
  return <button className="btn btn--ghost btn--sm" onClick={() => navigator.clipboard.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1500) })}>{done ? 'Copied ✓' : 'Copy'}</button>
}

/** /launchpad/facilities (Launchpad step 5) — Facilities & Other Resources builder */
/** `embedded`: shown inside a Launchpad step, so the page header and banner are left out. */
export function FacilitiesBuilder({ embedded = false }: { embedded?: boolean }) {
  const [list, retry] = useAsync(hub.facilities, [])
  const [picked, setPicked] = useState<string[]>([])
  const [project, setProject] = useState('')
  const [site, setSite] = useState('')
  const [polish, setPolish] = useState(false)
  const [q, setQ] = useState('')
  const [out, setOut] = useState<{ s: 'idle' } | { s: 'busy' } | { s: 'err'; m: string } | { s: 'done'; text: string; mode: string; note?: string; sources: { name: string; url: string }[] }>({ s: 'idle' })
  const opp = useLaunchOpp()
  useEffect(() => { if (opp && !project) setProject(opp.title) }, [opp]) // eslint-disable-line react-hooks/exhaustive-deps
  const toggle = (id: string) => setPicked(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id])
  const items = list.status === 'success' ? list.data.filter(f => !q || (f.name + f.text).toLowerCase().includes(q.toLowerCase())) : []

  const build = async () => {
    setOut({ s: 'busy' })
    try { setOut({ s: 'done', ...(await hub.draftFacilities({ ids: picked, project, site_text: site, polish })) }) }
    catch (e) { setOut({ s: 'err', m: (e as Error).message }) }
  }

  return (
    <div className={embedded ? 'hub hub--embedded' : 'page osf hub'}>
      {!embedded && <><header className="osf-head"><div className="osf-head__inner">
        <p className="eyebrow eyebrow--light"><Link to="/launchpad">Toolkit</Link></p>
        <h1>Facilities & Resources builder</h1>
        <p className="lede">Most grants ask what facilities and resources you can use. Pick the Yale resources that matter for your project,
          add a few lines about your partner site, and get a draft section to paste into your application.</p>
      </div>{WAVE}</header>

      <LaunchContext o={opp} /></>}
      <div className="fr">
        <section className="card fr__pick">
          <div className="fr__bar"><h2>1. Pick resources <span className="count">({picked.length} picked)</span></h2>
            <input type="search" className="input" placeholder="Filter" value={q} onChange={e => setQ(e.target.value)} aria-label="Filter resources" /></div>
          {list.status === 'loading' && <Loading />}
          {list.status === 'error' && <ErrorState message={list.error} onRetry={retry} />}
          {list.status === 'success' && list.data.length === 0 && <p className="muted">The resource list is being prepared.</p>}
          {CATS.map(([c, label]) => {
            const g = items.filter(f => f.category === c)
            return g.length > 0 && (
              <fieldset key={c} className="fr__group"><legend>{label}</legend>
                {g.map(f => (
                  <label key={f.id} className={`fr__item ${picked.includes(f.id) ? 'is-on' : ''}`}>
                    <input type="checkbox" checked={picked.includes(f.id)} onChange={() => toggle(f.id)} />
                    <span><strong>{f.name}</strong><span className="small muted">{f.text}</span>
                      <a className="small" href={f.url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>Source ↗</a></span>
                  </label>
                ))}
              </fieldset>
            )
          })}
        </section>

        <section className="card fr__form">
          <h2>2. Add your details</h2>
          <div className="field"><label htmlFor="fr-p">Project title (optional)</label>
            <input id="fr-p" className="input" value={project} onChange={e => setProject(e.target.value)} maxLength={300} /></div>
          <div className="field"><label htmlFor="fr-s">Partner site facilities (optional)</label>
            <textarea id="fr-s" className="input" rows={5} value={site} onChange={e => setSite(e.target.value)} maxLength={3000}
                      placeholder="In your own words: the clinic, lab or field site your partner provides, and what is there." /></div>
          <label className="small fr__polish"><input type="checkbox" checked={polish} onChange={e => setPolish(e.target.checked)} /> Smooth the wording with AI (it won’t add new facts)</label>
          <button className="btn" disabled={!picked.length || out.s === 'busy'} onClick={build}>{out.s === 'busy' ? 'Building…' : '3. Build the section'}</button>
          {!picked.length && <p className="muted small">Pick at least one resource first.</p>}

          {out.s === 'err' && <p className="form-error" role="alert">{out.m}</p>}
          {out.s === 'done' && (
            <div className="fr__out">
              <div className="fr__out-bar"><strong>Your draft</strong><span>
                <Copy text={out.text} /> <button className="btn btn--ghost btn--sm" onClick={() => download('facilities-and-resources.txt', out.text)}>Download</button></span></div>
              {out.note && <p className="small muted">{out.note}</p>}
              <pre className="fr__text">{out.text}</pre>
              <p className="small muted">Built from each resource’s public Yale page. Check details with the resource and your grants office before you submit;
                don’t list access you haven’t arranged.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

/** /launchpad/letters (Launchpad step 4) — request a letter of support, plus templates and checklists */
export function Letters({ embedded = false }: { embedded?: boolean }) {
  const [tpl, retry] = useAsync(hub.templates, [])
  const [open, setOpen] = useState<string | null>(null)
  const opp = useLaunchOpp()
  return (
    <div className={embedded ? 'hub hub--embedded' : 'page osf hub'}>
      {!embedded && <><header className="osf-head"><div className="osf-head__inner">
        <p className="eyebrow eyebrow--light"><Link to="/launchpad">Toolkit</Link></p>
        <h1>Letters of support, templates and checklists</h1>
        <p className="lede">Ask for a letter of support, start from a template, and use a checklist so nothing is missed.</p>
      </div>{WAVE}</header>

      <LaunchContext o={opp} /></>}
      <LetterForm key={opp?.id ?? 0} opp={opp} />

      <section id="templates" className="lt">
        <h2 className="home-sec__title">Letter templates</h2>
        {tpl.status === 'loading' && <Loading />}
        {tpl.status === 'error' && <ErrorState message={tpl.error} onRetry={retry} />}
        {tpl.status === 'success' && <>
          <div className="lt__grid">
            {tpl.data.letters.map(l => (
              <article key={l.id} className="card lt__card">
                <h3>{l.title}</h3><p className="small">{l.use}</p>
                <div className="lt__btns"><button className="link-btn" aria-expanded={open === l.id} onClick={() => setOpen(open === l.id ? null : l.id)}>{open === l.id ? 'Hide' : 'Preview'}</button>
                  <Copy text={l.body} /><button className="btn btn--ghost btn--sm" onClick={() => download(`${l.id}.txt`, l.body)}>Download</button></div>
                {open === l.id && <pre className="fr__text">{l.body}</pre>}
              </article>
            ))}
          </div>
          <h2 className="home-sec__title">Checklists</h2>
          <div className="lt__grid">{tpl.data.checklists.map(c => <Checklist key={c.id} c={c} />)}</div>
        </>}
      </section>
    </div>
  )
}

function Checklist({ c }: { c: { id: string; title: string; items: string[]; related: string[] } }) {
  const key = `grapph-check-${c.id}`
  const [done, setDone] = useState<number[]>(() => { try { return JSON.parse(localStorage.getItem(key) ?? '[]') } catch { return [] } })
  const flip = (i: number) => { const n = done.includes(i) ? done.filter(x => x !== i) : [...done, i]; setDone(n); localStorage.setItem(key, JSON.stringify(n)) }
  return (
    <article className="card lt__card">
      <h3>{c.title}</h3>
      <p className="small muted">{done.length} of {c.items.length} done</p>
      <ul className="lt__check">{c.items.map((it, i) => <li key={i}><label><input type="checkbox" checked={done.includes(i)} onChange={() => flip(i)} /> {it}</label></li>)}</ul>
      <p className="small">See the guides: {c.related.map((r, i) => <span key={r}>{i > 0 && ' · '}<Link to={`/hub/${r}`}>{r === 'fund' ? 'Funding' : r === 'comply' ? 'Compliance' : r === 'partner' ? 'Partnerships' : r === 'operate' ? 'Get the work done' : 'Share'}</Link></span>)}</p>
    </article>
  )
}

function LetterForm({ opp }: { opp: OppDetail | null }) {
  const { user, ready } = useAuth()
  const loc = useLocation()
  const [mine, reload] = useAsync<LetterRequest[]>(() => user ? hub.letters() : Promise.resolve([]), [user?.id])
  const [f, setF] = useState({ signer: 'YIGH Director', project_title: opp?.title ?? '', funder: opp?.funder ?? '',
    deadline: '', summary: '', confirm: '' })
  const [st, setSt] = useState<{ s: 'idle' | 'busy' } | { s: 'err'; m: string } | { s: 'ok'; r: LetterRequest }>({ s: 'idle' })
  const minDate = useMemo(() => new Date().toISOString().slice(0, 10), [])
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })

  if (!ready) return null
  if (!user) return (
    <section className="card lt__form"><h2>Request a letter of support</h2>
      <p>Sign in with your Yale email to send a request. Signing in lets YIGH staff know who is asking and lets you see the status of your requests here. The templates and checklists below work without an account.</p>
      <Link className="btn" to={`/signin?next=${encodeURIComponent(loc.pathname + loc.search)}`}>Sign in</Link></section>
  )
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setSt({ s: 'busy' })
    try { const r = await hub.requestLetter({ ...f, opportunity_id: opp?.id ?? null }); setSt({ s: 'ok', r }); reload() } catch (err) { setSt({ s: 'err', m: (err as Error).message }) }
  }
  return (
    <section className="card lt__form">
      <h2>Request a letter of support</h2>
      {opp?.deadline && <p className="small">The funder’s deadline is <strong>{opp.deadline}</strong>. Ask for the letter well before then.</p>}
      <p className="small muted">Your request is saved for YIGH staff to review. Nothing is sent by email yet, so contact the signer as well if the deadline is close.</p>
      <form onSubmit={submit} className="lt__fields">
        <div className="field"><label htmlFor="l-s">Who should sign it?</label><input id="l-s" className="input" required value={f.signer} onChange={set('signer')} /></div>
        <div className="field"><label htmlFor="l-f">Funder and program</label><input id="l-f" className="input" required value={f.funder} onChange={set('funder')} /></div>
        <div className="field"><label htmlFor="l-t">Project title</label><input id="l-t" className="input" required value={f.project_title} onChange={set('project_title')} /></div>
        <div className="field"><label htmlFor="l-d">When do you need it?</label><input id="l-d" type="date" className="input" required min={minDate} value={f.deadline} onChange={set('deadline')} /></div>
        <div className="field lt__wide"><label htmlFor="l-sum">Short project summary</label><textarea id="l-sum" className="input" rows={3} required minLength={20} value={f.summary} onChange={set('summary')} /></div>
        <div className="field lt__wide"><label htmlFor="l-c">What should the letter confirm? (only things already agreed)</label><textarea id="l-c" className="input" rows={2} value={f.confirm} onChange={set('confirm')} /></div>
        <button className="btn" disabled={st.s === 'busy'}>{st.s === 'busy' ? 'Sending…' : 'Send request'}</button>
      </form>
      {st.s === 'err' && <p className="form-error" role="alert">{st.m}</p>}
      {st.s === 'ok' && <p className="form-ok" role="status">Request saved. {st.r.warning}</p>}
      {mine.status === 'success' && mine.data.length > 0 && (
        <div className="lt__mine"><h3>Your requests</h3>
          <ul>{mine.data.map(r => <li key={r.id}><strong>{r.project_title}</strong> · {r.funder} · needed by {r.deadline} · <span className="badge">{r.status}</span></li>)}</ul></div>
      )}
    </section>
  )
}
