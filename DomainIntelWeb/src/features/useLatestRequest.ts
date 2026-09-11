import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type ClientPath } from '../api'

/** One selected resource: only its latest request may update the view. */
export function useLatestRequest<T>() {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const controller = useRef<AbortController | null>(null)
  const clear = useCallback(() => {
    controller.current?.abort()
    setData(null)
    setError('')
    setLoading(false)
  }, [])
  const load = useCallback(async (path: ClientPath) => {
    clear()
    const request = new AbortController()
    controller.current = request
    setLoading(true)
    try {
      const value = await api<T>(path, { signal: request.signal })
      if (!request.signal.aborted) setData(value)
    } catch (reason) {
      if (!request.signal.aborted) setError(String(reason))
    } finally {
      if (!request.signal.aborted) setLoading(false)
    }
  }, [clear])
  useEffect(() => () => controller.current?.abort(), [])
  return { data, error, loading, load, clear }
}
