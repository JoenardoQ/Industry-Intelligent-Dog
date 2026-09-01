import type { ApiPath } from '../generated/openapi'
import { validateResponse } from './runtime'

type ExpandParameters<Path extends string> =
  Path extends `${infer Prefix}{${string}}${infer Suffix}`
    ? `${Prefix}${string}${ExpandParameters<Suffix>}`
    : Path

type StripApiPrefix<Path extends string> =
  Path extends `/api${infer Client}` ? ExpandParameters<Client> : never

type Queryable<Path extends string> = Path | `${Path}?${string}`

export type ClientPath = ApiPath extends infer Path extends string
  ? Queryable<StripApiPrefix<Path>>
  : never

export type SessionRequestInit = RequestInit & { signal?: AbortSignal }

async function sessionRequest<TPath extends ClientPath>(
  path: TPath,
  init?: SessionRequestInit,
): Promise<Response> {
  const capability = sessionStorage.getItem('intdog.session') || ''
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(capability ? { 'X-IntDog-Session': capability } : {}),
      ...(init?.headers || {}),
    },
  })
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const payload: unknown = await response.json()
      if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
        detail = String((payload as { detail: unknown }).detail || detail)
      }
    } catch { /* preserve HTTP status when the error body is not JSON */ }
    throw new Error(detail)
  }
  return response
}

export async function api<
  TResult = unknown,
  TPath extends ClientPath = ClientPath,
>(path: TPath, init?: SessionRequestInit): Promise<TResult> {
  const response = await sessionRequest(path, init)
  const value: unknown = response.status === 204 ? null : await response.json()
  validateResponse(path, init?.method || 'GET', value)
  return value as TResult
}

export async function apiText<TPath extends ClientPath>(
  path: TPath,
  init?: SessionRequestInit,
): Promise<string> {
  return (await sessionRequest(path, init)).text()
}

export function artifactUrl(path: string) {
  return `/api/artifact?path=${encodeURIComponent(path)}`
}
