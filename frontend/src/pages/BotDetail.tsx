import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, AlertTriangle, ArrowLeft, CircleDot, Play, Square, Trash2 } from 'lucide-react'
import { api } from '../api'
import StatCard from '../components/StatCard'
import Badge from '../components/Badge'

export default function BotDetail() {
  const { t } = useTranslation()
  const { id } = useParams()
  const botId = Number(id)
  const nav = useNavigate()
  const qc = useQueryClient()

  const { data: bot } = useQuery({ queryKey: ['bot', botId], queryFn: () => api.getBot(botId) })
  const { data: position } = useQuery({ queryKey: ['botPosition', botId], queryFn: () => api.botPosition(botId) })
  const { data: orders = [] } = useQuery({ queryKey: ['botOrders', botId], queryFn: () => api.botOrders(botId) })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['bot', botId] })
    qc.invalidateQueries({ queryKey: ['botOrders', botId] })
    qc.invalidateQueries({ queryKey: ['botPosition', botId] })
  }
  const start = useMutation({ mutationFn: () => api.startBot(botId), onSuccess: refresh })
  const stop = useMutation({ mutationFn: () => api.stopBot(botId), onSuccess: refresh })
  const del = useMutation({ mutationFn: () => api.deleteBot(botId), onSuccess: () => nav('/bots') })

  if (!bot) return null
  const running = bot.runtime.running

  const config: [string, string][] = [
    [t('strategy.direction'), bot.direction === 'LONG' ? t('strategy.directionLong') : t('strategy.directionShort')],
    [t('strategy.entryPrice'), bot.entry_price > 0 ? `$${bot.entry_price.toLocaleString()}` : t('common.none')],
    [t('strategy.leverage'), `${bot.leverage}×`],
    [t('strategy.targetPosition'), `${bot.target_position_pct}%`],
    [t('strategy.dcaStep'), `${bot.dca_step_pct}%`],
    [t('strategy.dcaAdd'), `${bot.dca_add_pct}%`],
    [t('strategy.maxDcaOrders'), `${bot.max_dca_orders}`],
    [t('strategy.closePerLevel'), `${bot.take_profit_close_pct}%`],
    [t('bots.account'), bot.account_name],
  ]

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Link to="/bots" className="text-slate-500 hover:text-slate-100">
            <ArrowLeft size={18} />
          </Link>
          {running ? (
            <Activity size={16} className="text-emerald-400" />
          ) : (
            <CircleDot size={16} className="text-slate-500" />
          )}
          <h1 className="text-lg font-semibold text-slate-100">{bot.name}</h1>
          <span className="text-sm text-slate-500">{bot.symbol}</span>
          <Badge
            label={bot.direction === 'LONG' ? t('side.long') : t('side.short')}
            variant={bot.direction === 'LONG' ? 'green' : 'red'}
          />
        </div>
        <div className="flex items-center gap-2">
          {running ? (
            <button
              onClick={() => stop.mutate()}
              disabled={stop.isPending}
              className="flex items-center gap-1.5 bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded-md"
            >
              <Square size={13} /> {t('bots.stop')}
            </button>
          ) : (
            <button
              onClick={() => start.mutate()}
              disabled={start.isPending}
              className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded-md"
            >
              <Play size={13} /> {t('bots.start')}
            </button>
          )}
          <button
            onClick={() => confirm(t('bots.deleteConfirm')) && del.mutate()}
            className="text-slate-500 hover:text-red-400 px-2"
            title={t('bots.delete')}
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      {bot.runtime.last_error && (
        <div className="flex items-center gap-2 text-sm text-red-400 bg-red-900/20 rounded-md px-3 py-2">
          <AlertTriangle size={15} /> {bot.runtime.last_error}
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        <StatCard label={t('bots.realized')} value={`$${bot.pnl.realized.toFixed(2)}`} positive={bot.pnl.realized > 0} negative={bot.pnl.realized < 0} />
        <StatCard label={t('bots.unrealized')} value={`$${bot.pnl.unrealized.toFixed(2)}`} positive={bot.pnl.unrealized > 0} negative={bot.pnl.unrealized < 0} />
        <StatCard label={t('bots.total')} value={`$${bot.pnl.total.toFixed(2)}`} positive={bot.pnl.total > 0} negative={bot.pnl.total < 0} />
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
          <h2 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-3">{t('botDetail.config')}</h2>
          <dl className="space-y-2 text-sm">
            {config.map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <dt className="text-slate-500">{k}</dt>
                <dd className="text-slate-200">{v}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
          <h2 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-3">{t('botDetail.position')}</h2>
          {position ? (
            <dl className="space-y-2 text-sm">
              <Row k={t('table.size')} v={`${position.size}`} />
              <Row k={t('table.entry')} v={`$${position.entry_price.toLocaleString()}`} />
              <Row k={t('table.mark')} v={`$${position.mark_price.toLocaleString()}`} />
              <Row k={t('table.liqPrice')} v={`$${position.liquidation_price.toLocaleString()}`} red />
              <Row k={t('table.pnl')} v={`${position.unrealized_pnl >= 0 ? '+' : ''}$${position.unrealized_pnl.toFixed(2)}`} />
            </dl>
          ) : (
            <p className="text-sm text-slate-500">{t('botDetail.noPosition')}</p>
          )}
        </div>
      </div>

      <div>
        <h2 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-3">
          {t('botDetail.orders')} ({orders.length})
        </h2>
        <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
          {orders.length === 0 ? (
            <p className="p-6 text-center text-sm text-slate-500">{t('common.none')}</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-slate-500 text-xs uppercase">
                  <th className="px-4 py-2.5 text-left">{t('table.side')}</th>
                  <th className="px-4 py-2.5 text-right">{t('table.qty')}</th>
                  <th className="px-4 py-2.5 text-right">{t('table.price')}</th>
                  <th className="px-4 py-2.5 text-center">{t('table.reduceOnly')}</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.order_id} className="border-b border-slate-800/50">
                    <td className="px-4 py-2.5">
                      <Badge label={o.side === 'BUY' ? t('side.buy') : t('side.sell')} variant={o.side === 'BUY' ? 'green' : 'red'} />
                    </td>
                    <td className="px-4 py-2.5 text-right text-slate-300">{o.quantity}</td>
                    <td className="px-4 py-2.5 text-right text-slate-300">${o.price.toLocaleString()}</td>
                    <td className="px-4 py-2.5 text-center text-slate-400">{o.reduce_only ? t('common.yes') : t('common.none')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

function Row({ k, v, red }: { k: string; v: string; red?: boolean }) {
  return (
    <div className="flex justify-between">
      <dt className="text-slate-500">{k}</dt>
      <dd className={red ? 'text-red-400' : 'text-slate-200'}>{v}</dd>
    </div>
  )
}
