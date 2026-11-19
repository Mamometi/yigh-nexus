import { useEffect, useState, type FormEvent } from 'react'
import { useLocation } from 'react-router-dom'
import { hub } from '../hub'

/** "Help Improve GRAPPH": a Feedback button on every page. Saved for YIGH staff; nothing is emailed. */

const KINDS: [string, string][] = [['incorrect', 'Incorrect or outdated information'], ['missing', 'Missing resource or pathway'],
  ['confusing', 'Something is confusing'], ['suggestion', 'Suggestion for improvement'], ['other', 'Other']]

export function Feedback() {
  const loc = useLocation()
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState('suggestion')
  const [msg, setMsg] = useState('')
  const [email, setEmail] = useState('')
  const [state, setState] = useState<{ s: 'idle' | 'sending' | 'sent' | 'error'; err?: string }>({ s: 'idle' })
  const [pageTitle, setPageTitle] = useState('')

  useEffect(() => {
    if (!open) return
    setPageTitle(document.querySelector('main h1')?.textContent?.trim() || 'GRAPPH')
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [open])

  const close = () => { setOpen(false); if (state.s === 'sent') { setMsg(''); setEmail(''); setKind('suggestion'); setState({ s: 'idle' }) } }
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setState({ s: 'sending' })
    try { await hub.feedback({ page: loc.pathname + loc.search, page_title: pageTitle, kind, message: msg, email }); setState({ s: 'sent' }) }
    catch (err) { setState({ s: 'error', err: (err as Error).message }) }
  }

  return (
    <>
      <button className="fb-fab" onClick={() => setOpen(true)} aria-haspopup="dialog">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden><path d="M4 5h16v11H9l-5 4z" /></svg>
        Feedback</button>
      {open && (
        <div className="fb-overlay" onMouseDown={e => e.target === e.currentTarget && close()}>
          <div className="fb" role="dialog" aria-modal="true" aria-labelledby="fb-title">
            <button className="fb__x" onClick={close} aria-label="Close">✕</button>
            <h2 id="fb-title">Help Improve GRAPPH</h2>
            <p className="muted small">Your feedback helps us make GRAPPH more useful for the YIGH community.</p>
            {state.s === 'sent' ? (
              <div className="fb__done"><p><strong>Thank you!</strong> YIGH staff will review your feedback.</p>
                <button className="btn" onClick={close}>Close</button></div>
            ) : (
              <form onSubmit={submit}>
                <p className="fb__page small">You are providing feedback on: <strong>{pageTitle}</strong></p>
                <fieldset><legend>What would you like to tell us?</legend>
                  {KINDS.map(([v, l]) => <label key={v} className="fb__opt"><input type="radio" name="fb-kind" value={v} checked={kind === v} onChange={() => setKind(v)} /> {l}</label>)}
                </fieldset>
                <label className="fb__field">Tell us more
                  <textarea className="input" rows={4} value={msg} onChange={e => setMsg(e.target.value)} maxLength={3000} placeholder="Please share your comments, suggestions or questions…" /></label>
                <label className="fb__field">Your email (optional)
                  <input className="input" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="For follow-up, if needed" /></label>
                {state.s === 'error' && <p className="signin__err" role="alert">{state.err}</p>}
                <div className="fb__btns"><button type="button" className="btn btn--ghost" onClick={close}>Cancel</button>
                  <button className="btn" disabled={state.s === 'sending'}>{state.s === 'sending' ? 'Sending…' : 'Submit Feedback'}</button></div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  )
}
