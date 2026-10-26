import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth'

export function SignIn() {
  const { user, signIn, register } = useAuth()
  const [params] = useSearchParams()
  const next = params.get('next')?.startsWith('/') ? params.get('next')! : '/'
  const [mode, setMode] = useState<'in' | 'up'>('in')
  const [name, setName] = useState(''), [email, setEmail] = useState(''), [pw, setPw] = useState('')
  const [err, setErr] = useState<string | null>(null), [busy, setBusy] = useState(false)
  const nav = useNavigate()
  if (user) return <Navigate to={next} replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr(null); setBusy(true)
    try { mode === 'in' ? await signIn(email, pw) : await register(name, email, pw); nav(next, { replace: true }) }
    catch (x) { setErr((x as Error).message) } finally { setBusy(false) }
  }
  return (
    <div className="page signin osf">
      <header className="osf-head">
        <div className="osf-head__inner">
          <p className="eyebrow eyebrow--light">YIGH Nexus</p>
          <h1>{mode === 'in' ? 'Sign in' : 'Create an account'}</h1>
          <p className="lede">Sign in with your Yale email to use the Launchpad and draft research concepts for proposed teams.</p>
        </div>
        <svg className="wave" viewBox="0 0 1440 80" preserveAspectRatio="none" aria-hidden><path d="M0,40 C360,90 1080,-10 1440,40 L1440,80 L0,80 Z" /></svg>
      </header>
      <form className="signin__card" onSubmit={submit} noValidate>
        {mode === 'up' && <div className="field"><label htmlFor="si-name">Name</label>
          <input id="si-name" className="input" value={name} onChange={e => setName(e.target.value)} autoComplete="name" required /></div>}
        <div className="field"><label htmlFor="si-email">Yale email</label>
          <input id="si-email" className="input" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="netid@yale.edu" autoComplete="email" required /></div>
        <div className="field"><label htmlFor="si-pw">Password</label>
          <input id="si-pw" className="input" type="password" value={pw} onChange={e => setPw(e.target.value)}
                 autoComplete={mode === 'in' ? 'current-password' : 'new-password'} required minLength={mode === 'up' ? 10 : undefined} />
          {mode === 'up' && <p className="muted small">At least 10 characters.</p>}</div>
        {err && <p className="signin__err" role="alert">{err}</p>}
        <button className="btn btn--lg" type="submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'in' ? 'Sign in' : 'Create account'}</button>
        <p className="small">{mode === 'in' ? <>New here? <button type="button" className="link-btn" onClick={() => { setMode('up'); setErr(null) }}>Create an account</button></>
          : <>Already have an account? <button type="button" className="link-btn" onClick={() => { setMode('in'); setErr(null) }}>Sign in</button></>}</p>
        <p className="muted small">Accounts are limited to @yale.edu addresses. <Link to="/">Back to home</Link></p>
      </form>
    </div>
  )
}
