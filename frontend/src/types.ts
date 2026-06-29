export interface User {
  id: number
  email: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

export interface Account {
  id: number
  name: string
  api_key_masked: string
  testnet: boolean
  created_at: string
}

export interface AccountCreate {
  name: string
  api_key: string
  api_secret: string
  testnet: boolean
}

export interface ConnectionTest {
  ok: boolean
  can_trade: boolean | null
  total_wallet_balance: number | null
  error: string | null
}

export interface BotRuntime {
  running: boolean
  last_tick_at: string | null
  last_error: string | null
  desired_orders: number
  open_orders: number
  notes: string[]
}

export interface BotPnl {
  realized: number
  unrealized: number
  total: number
  since: string | null
}

export interface BotConfig {
  symbol: string
  direction: 'LONG' | 'SHORT'
  entry_price: number
  leverage: number
  target_position_pct: number
  dca_step_pct: number
  dca_add_pct: number
  take_profit_pct: number
  take_profit_close_pct: number
  tp_width_pct: number
  max_dca_orders: number
}

export interface Bot extends BotConfig {
  id: number
  name: string
  account_id: number
  account_name: string
  enabled: boolean
  created_at: string
  started_at: string | null
  runtime: BotRuntime
  pnl: BotPnl
}

export interface BotCreate extends BotConfig {
  name: string
  account_id: number
}

export interface Position {
  symbol: string
  side: 'LONG' | 'SHORT'
  size: number
  entry_price: number
  mark_price: number
  leverage: number
  unrealized_pnl: number
  pnl_pct: number
  liquidation_price: number
  margin: number
}

export interface Order {
  order_id: string
  symbol: string
  side: 'BUY' | 'SELL'
  type: string
  quantity: number
  price: number
  status: string
  reduce_only: boolean
}
