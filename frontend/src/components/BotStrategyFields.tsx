import { useTranslation } from 'react-i18next'
import type { ReactNode } from 'react'
import type { BotConfig } from '../types'

export type BotFormValues = BotConfig & { name: string }

export const inputClass =
  'w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed'

export function Field({ label, sub, children }: { label: string; sub?: string; children: ReactNode }) {
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

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-4">
      <h2 className="text-xs font-medium text-slate-500 uppercase tracking-wide">{title}</h2>
      {children}
    </div>
  )
}

interface Props {
  form: BotFormValues
  set: <K extends keyof BotFormValues>(key: K, value: BotFormValues[K]) => void
  /** When the bot is running, structural fields (symbol/direction/leverage/entry) are locked. */
  lockStructural?: boolean
  /** Extra field rendered in the "general" section (e.g. account selector on create). */
  accountSlot?: ReactNode
}

export default function BotStrategyFields({ form, set, lockStructural, accountSlot }: Props) {
  const { t } = useTranslation()

  const numField = (
    key: keyof BotFormValues,
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

        {accountSlot}

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
                  disabled={lockStructural}
                  onClick={() => set('direction', dir)}
                  className={`py-2 rounded-md text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
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
            disabled={lockStructural}
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
            disabled={lockStructural}
            onChange={(e) => set('entry_price', Number(e.target.value))}
          />
          <p className="text-xs text-slate-500 mt-1 leading-relaxed">{t('strategy.entryPriceHint')}</p>
        </Field>

        {numField('leverage', t('strategy.leverage'), t('strategy.leverageUnit'), {
          min: 1,
          max: 125,
          disabled: lockStructural,
        })}
        {numField('target_position_pct', t('strategy.targetPosition'), t('strategy.targetPositionSub'), {
          min: 1,
          max: 100,
          step: 0.5,
        })}
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
    </>
  )
}
