import { useEffect, useState } from 'react'

export type AsyncState<T> =
  | { status: 'loading' }
  | { status: 'error'; error: string }
  | { status: 'success'; data: T }

/** Runs an async loader whenever deps change; ignores results from stale requests. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[]): [AsyncState<T>, () => void] {
  const [state, setState] = useState<AsyncState<T>>({ status: 'loading' })
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    let active = true
    setState({ status: 'loading' })
    loader()
      .then(data => active && setState({ status: 'success', data }))
      .catch((e: Error) => active && setState({ status: 'error', error: e.message }))
    return () => { active = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])
  return [state, () => setNonce(n => n + 1)]
}

export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}
