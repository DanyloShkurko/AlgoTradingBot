import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { api } from '../api'
import type { BotCreate } from '../types'

const inputClass =
  'w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500'

const defaults: Omit<BotCreate, 'account_id'> = {
  name: '',
  symbol: 'BTCUSDT',
  direction: 'LONG',
  entry_price: 0,
  leverage: 10,
  target_position_pct: 15,
  dca_step_pct: 2,
  dca_add_pct: 20,
  take_profit_pct: 20,
  take_profit_close_pct: 33,
  tp_width_pct: 100,
  max_dca_orders: 8,
}

function Field({ label, sub, children }: { label: string; sub?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-300 mb-1">
        {label}
        {sub && <span className="ml-1.5 text-xs text-slate-500">{sub}</span>}
      </label>
      {children}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-4">
      <h2 className="text-xs font-medium text-slate-500 uppercase tracking-wide">{title}</h2>
      {children}
    </div>
  )
}

export default function CreateBot() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const { data: accounts = [] } = useQuery({ queryKey: ['accounts'], queryFn: api.listAccounts })
  const [form, setForm] = useState<Omit<BotCreate, 'account_id'>>(defaults)
  const [accountId, setAccountId] = useState<number | null>(null)

  const effectiveAccount = accountId ?? accounts[0]?.id ?? null

  const create = useMutation({
    mutationFn: () => api.createBot({ ...form, account_id: effectiveAccount! }),
    onSuccess: () => nav('/bots'),
  })

  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const numField = (
    key: keyof typeof form,
    label: string,
    sub?: string,
    extra?: Partial<React.InputHTMLAttributes<HTMLInputElement>>,
  ) => (
    <Field label={label} sub={sub}>
      <input
        type="number"
        className={inputClass}
        value={form[key] as number}
        onChange={(e) => set(key, Number(e.target.value) as never)}
        {...extra}
      />
    </Field>
  )

  return (
    <div className="max-w-xl space-y-6">
      <div className="flex items-center gap-2">
        <Link to="/bots" className="text-slate-500 hover:text-slate-100">
          <ArrowLeft size={18} />
        </Link>
        <h1 className="text-lg font-semibold text-slate-100">{t('createBot.title')}</h1>
      </div>

      {accounts.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-6 text-center text-sm text-slate-400">
          {t('createBot.noAccounts')}{' '}
          <Link to="/accounts" className="text-emerald-400 hover:text-emerald-300">
            {t('nav.accounts')}
          </Link>
        </div>
      ) : (
        <>
          <Section title={t('createBot.general')}>
            <Field label={t('createBot.name')}>
              <input
                className={inputClass}
                value={form.name}
                placeholder={t('createBot.namePlaceholder')}
                onChange={(e) => set('name', e.target.value)}
              />
            </Field>
            <Field label={t('createBot.account')}>
              <select
                className={inputClass}
                value={effectiveAccount ?? ''}
                onChange={(e) => setAccountId(Number(e.target.value))}
              >
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} {a.testnet ? '(testnet)' : ''}
                  </option>
                ))}
              </select>
            </Field>
            <Field
              label={t('strategy.direction')}
              sub={form.direction === 'LONG' ? t('strategy.directionLongSub') : t('strategy.directionShortSub')}
            >
              <div className="grid grid-cols-2 gap-2">
                {(['LONG', 'SHORT'] as const).map((dir) => {
                  const active = form.direction === dir
                  const cls = dir === 'LONG' ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'
                  return (
                    <button
                      key={dir}
                      type="button"
                      onClick={() => set('direction', dir)}
                      className={`py-2 rounded-md text-sm font-medium transition-colors ${
                        active ? cls : 'bg-slate-800 text-slate-400 hover:text-slate-100'
                      }`}
                    >
                      {dir === 'LONG' ? t('strategy.directionLong') : t('strategy.directionShort')}
                    </button>
                  )
                })}
              </div>
            </Field>
            <Field label={t('strategy.symbol')}>
              <input
                className={inputClass}
                value={form.symbol}
                onChange={(e) => set('symbol', e.target.value.toUpperCase())}
              />
            </Field>
            <Field label={t('strategy.entryPrice')} sub={t('strategy.entryPriceSub')}>
              <input
                type="number"
                className={inputClass}
                value={form.entry_price}
                min={0}
                step="any"
                onChange={(e) => set('entry_price', Number(e.target.value))}
              />
              <p className="text-xs text-slate-500 mt-1 leading-relaxed">{t('strategy.entryPriceHint')}</p>
            </Field>
            {numField('leverage', t('strategy.leverage'), t('strategy.leverageUnit'), { min: 1, max: 125 })}
            {numField('target_position_pct', t('strategy.targetPosition'), t('strategy.targetPositionSub'), { min: 1, max: 100, step: 0.5 })}
          </Section>

          <Section title={t('createBot.advanced')}>
            {numField('dca_step_pct', t('strategy.dcaStep'), t('strategy.dcaStepSub'), { min: 0.1, max: 50, step: 0.1 })}
            {numField('dca_add_pct', t('strategy.dcaAdd'), t('strategy.dcaAddSub'), { min: 1, max: 200, step: 1 })}
            {numField('max_dca_orders', t('strategy.maxDcaOrders'), undefined, { min: 1, max: 30 })}
            <p className="text-xs text-slate-500 leading-relaxed">{t('strategy.tpExplain')}</p>
            {numField('take_profit_close_pct', t('strategy.closePerLevel'), t('strategy.closePerLevelSub'), { min: 5, max: 100, step: 1 })}
            {numField('tp_width_pct', t('strategy.tpWidth'), t('strategy.tpWidthSub'), { min: 10, max: 500, step: 5 })}
            {numField('take_profit_pct', t('strategy.tpTrigger'), t('strategy.tpTriggerSub'), { min: 1, max: 100, step: 1 })}
          </Section>

          {create.isError && <div className="text-sm text-red-400">{(create.error as Error).message}</div>}

          <button
            onClick={() => create.mutate()}
            disabled={create.isPending || !effectiveAccount}
            className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white font-medium py-2 rounded-md transition-colors text-sm"
          >
            {create.isPending ? t('common.creating') : t('createBot.submit')}
          </button>
        </>
      )}
    </div>
  )
}
