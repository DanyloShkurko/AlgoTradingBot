import type {
  Account,
  AccountCreate,
  AuthResponse,
  Bot,
  BotCreate,
  BotConfig,
  ConnectionTest,
  Order,
  Position,
  User,
} from '../types'

const BASE = '/api'

export function getToken(): string | null {
  return localStorage.getItem('token')
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem('token', token)
  else localStorage.removeItem('token')
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = getToken()
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })

  if (res.status === 401) {
    setToken(null)
    if (!location.pathname.startsWith('/login') && !location.pathname.startsWith('/register')) {
      location.href = '/login'
    }
    throw new Error('Unauthorized')
  }

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const j = await res.json()
      if (j?.detail) detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }

  if (res.status === 204) return undefined as T
  return res.json()
}

export const api = {
  register: (email: string, password: string) =>
    req<AuthResponse>('POST', '/auth/register', { email, password }),
  login: (email: string, password: string) =>
    req<AuthResponse>('POST', '/auth/login', { email, password }),
  me: () => req<User>('GET', '/auth/me'),

  listAccounts: () => req<Account[]>('GET', '/accounts'),
  createAccount: (body: AccountCreate) => req<Account>('POST', '/accounts', body),
  deleteAccount: (id: number) => req<void>('DELETE', `/accounts/${id}`),
  testAccount: (id: number) => req<ConnectionTest>('POST', `/accounts/${id}/test`),

  listBots: () => req<Bot[]>('GET', '/bots'),
  createBot: (body: BotCreate) => req<Bot>('POST', '/bots', body),
  getBot: (id: number) => req<Bot>('GET', `/bots/${id}`),
  updateBot: (id: number, body: BotConfig & { name: string }) =>
    req<Bot>('PUT', `/bots/${id}`, body),
  deleteBot: (id: number) => req<void>('DELETE', `/bots/${id}`),
  startBot: (id: number) => req<Bot>('POST', `/bots/${id}/start`),
  stopBot: (id: number) => req<Bot>('POST', `/bots/${id}/stop`),
  botOrders: (id: number) => req<Order[]>('GET', `/bots/${id}/orders`),
  botPosition: (id: number) => req<Position | null>('GET', `/bots/${id}/position`),
}
