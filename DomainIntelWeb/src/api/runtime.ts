function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requireKeys(path: string, value: unknown, keys: string[]) {
  if (!record(value) || keys.some(key => !(key in value))) {
    throw new Error(`API contract mismatch at ${path}: expected ${keys.join(', ')}`)
  }
}

export function validateResponse(path: string, method: string, value: unknown) {
  const route = path.split('?', 1)[0]
  if (method.toUpperCase() !== 'GET') return
  if (route === '/industries' || route === '/jobs') {
    if (!Array.isArray(value)) throw new Error(`API contract mismatch at ${route}: expected array`)
    return
  }
  if (route === '/health') return requireKeys(route, value,
    ['status', 'data_root', 'database', 'active_jobs'])
  if (route === '/background') return requireKeys(route, value,
    ['service', 'last_wakeup', 'next_run_at', 'permissions', 'schedule_errors'])
  if (route === '/setup') return requireKeys(route, value,
    ['runtime_ready', 'data_root', 'taskpack_ready', 'agents', 'api_providers'])
  if (route.endsWith('/overview')) return requireKeys(route, value,
    ['industry', 'stats', 'chain', 'chain_edges', 'entities', 'source_categories'])
  if (route.endsWith('/daily')) return requireKeys(route, value,
    ['items', 'total', 'next_cursor', 'selection_scope'])
  if (route.endsWith('/products')) return requireKeys(route, value,
    ['periodic', 'reports', 'deep_reports', 'impacts'])
  if (route.endsWith('/sources')) return requireKeys(route, value,
    ['industry', 'categories'])
  if (route.endsWith('/source-campaigns')) return requireKeys(route, value,
    ['items', 'total', 'next_offset'])
  if (route.endsWith('/coverage-matrix')) return requireKeys(route, value,
    ['industry', 'cells', 'gap_count'])
  if (route.endsWith('/research')) return requireKeys(route, value,
    ['lab', 'agenda', 'tasks', 'impacts'])
  if (route.endsWith('/history')) return requireKeys(route, value, ['items'])
  if (/^\/jobs\/[^/]+\/output$/.test(route)) return requireKeys(route, value,
    ['run_id', 'output'])
}
