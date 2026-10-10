const API_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export function apiUrl(path: string): string {
  return `${API_URL}${path}`
}

/** Turn a non-2xx response into an ApiError, preferring FastAPI's `detail`. */
export async function toApiError(resp: Response): Promise<ApiError> {
  let detail = resp.statusText || `HTTP ${resp.status}`
  try {
    const body = await resp.json()
    if (typeof body.detail === 'string') detail = body.detail
    else if (Array.isArray(body.detail))
      detail = body.detail.map((d: { msg: string }) => d.msg).join('; ')
  } catch {
    // non-JSON error body; keep statusText
  }
  return new ApiError(resp.status, detail)
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(apiUrl(path), {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!resp.ok) throw await toApiError(resp)
  if (resp.status === 204) return undefined as T
  return resp.json() as Promise<T>
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof TypeError) return 'Cannot reach the backend'
  if (err instanceof Error) return err.message
  return String(err)
}
