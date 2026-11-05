import { useProviderUsage, useUsage } from '@/lib/queries'
import { fmtTokens } from '@/pages/sessions/util'
import { useIsMobile } from '@/stores/media'
import { fmtDate, fmtRelative } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useLang, useT } from '@/i18n'
import type { ProviderUsage, UsageWindow } from '@/lib/types'
import { ProgressBar, Tooltip } from '@/components/ui'

/** Codex and Cursor under the Claude bars: Codex shows its real plan windows (read from its own files), Cursor has no
 *  quota to read, so both fall back to the tokens Harness measured. Nothing when an agent was never used. */
function ProviderUsageRows({ items, collapsed }: { items: ProviderUsage[]; collapsed?: boolean }) {
  const t = useT()
  const lang = useLang()
  const used = (w: UsageWindow) => Math.min(100, Math.round(w.pct))
  const tone = (w: UsageWindow) => (used(w) >= 90 ? 'error' : used(w) >= 70 ? 'warn' : undefined)
  return (
    <>
      {items.map((p) => {
        const rows = [
          { key: 'five', label: t('usage.fiveHour'), w: p.five_hour },
          { key: 'week', label: t('usage.week'), w: p.seven_day },
        ].filter((r): r is { key: string; label: string; w: UsageWindow } => !!r.w)
        const title = p.plan ? t('usage.providerPlan', { provider: p.label, plan: p.plan }) : t('usage.providerUsage', { provider: p.label })
        const details = (
          <div className="grid gap-1.5 text-xs">
            <span className="font-medium">{title}</span>
            {rows.map((r) => (
              <span key={r.key} className="tabular-nums">
                {r.label} · {t('usage.used', { pct: used(r.w) })}
                {r.w.resets_at && <span className="opacity-70"> · {t('usage.resets', { at: fmtDate(r.w.resets_at, lang, undefined, { dateStyle: undefined, timeStyle: undefined, weekday: 'short', hour: '2-digit', minute: '2-digit' }) })}</span>}
              </span>
            ))}
            <span className="tabular-nums">{t('usage.tokensToday', { n: fmtTokens(p.tokens.today) })} · {t('usage.tokensWeek', { n: fmtTokens(p.tokens.week) })}</span>
            {!rows.length && <span className="max-w-60 opacity-70">{t('usage.noQuota', { provider: p.label })}</span>}
            {rows.length > 0 && p.seen_at && <span className="max-w-60 opacity-70">{t('usage.seen', { when: fmtRelative(p.seen_at, lang) })}</span>}
          </div>
        )
        return (
          <Tooltip key={p.id} content={details} side="right">
            <div className={cn('grid gap-1 px-2.5 py-1.5', collapsed && 'px-1')} aria-label={title}>
              {rows.length ? (
                collapsed ? (
                  rows.map((r) => <ProgressBar key={r.key} value={used(r.w)} tone={tone(r.w)} label={`${p.label} ${r.label}`} className="h-1" />)
                ) : (
                  <>
                    <span className="text-[11px] leading-none font-medium text-muted-foreground">{p.label}</span>
                    {rows.map((r) => (
                      <div key={r.key} className="grid gap-1">
                        <div className="flex justify-between text-[11px] leading-none text-muted-foreground">
                          <span>{r.label}</span>
                          <span className="tabular-nums">{t('usage.used', { pct: used(r.w) })}</span>
                        </div>
                        <ProgressBar value={used(r.w)} tone={tone(r.w)} label={`${p.label} ${r.label}`} className="h-1" />
                      </div>
                    ))}
                  </>
                )
              ) : !collapsed ? (
                <div className="flex justify-between text-[11px] leading-none text-muted-foreground">
                  <span>{p.label}</span>
                  <span className="tabular-nums">{t('usage.tokensWeekShort', { n: fmtTokens(p.tokens.week) })}</span>
                </div>
              ) : null}
            </div>
          </Tooltip>
        )
      })}
    </>
  )
}

/** How much of the Claude plan is used (5-hour window, week), as on claude.ai: two small bars under the health indicator.
 *  Hidden when the server has no plan usage (API key, never read). */
export function UsageIndicator({ collapsed, visible }: { collapsed?: boolean; /** Shown in the touch layout's menu (polls while it is open). */ visible?: boolean }) {
  const t = useT()
  const lang = useLang()
  const desktop = !useIsMobile() || !!visible     // the sidebar is hidden in the touch layout: no polling for a bar nobody sees
  const { data: u } = useUsage(desktop, desktop)
  const { data: pu } = useProviderUsage(desktop, desktop)
  const others = [pu?.codex, pu?.cursor].filter((p): p is ProviderUsage => !!p && (p.available || p.tokens.week > 0))
  if (!u?.available) return others.length ? <div className="grid"><ProviderUsageRows items={others} collapsed={collapsed} /></div> : null
  const rows = [
    { key: 'five', label: t('usage.fiveHour'), w: u.five_hour },
    { key: 'week', label: t('usage.week'), w: u.seven_day },
  ].filter((r): r is { key: string; label: string; w: UsageWindow } => !!r.w)
  const used = (w: UsageWindow) => Math.min(100, Math.round(w.pct))
  const tone = (w: UsageWindow) => (used(w) >= 90 ? 'error' : used(w) >= 70 ? 'warn' : undefined)
  const reset = (w: UsageWindow) =>
    w.resets_at ? t('usage.resets', { at: fmtDate(w.resets_at, lang, undefined, { dateStyle: undefined, timeStyle: undefined, weekday: 'short', hour: '2-digit', minute: '2-digit' }) }) : null
  const noFive = !u.five_hour && u.plan === 'Ultra' // verified Ultra accounts have no 5-hour window
  const title = u.plan ? t('usage.titlePlan', { plan: u.plan }) : t('usage.title')
  const details = (
    <div className="grid gap-1.5 text-xs">
      <span className="font-medium">{title}</span>
      {noFive && <span>{t('usage.noFiveHour')}</span>}
      {rows.map((r) => (
        <span key={r.key} className="tabular-nums">
          {r.label} · {t('usage.used', { pct: used(r.w) })}
          {reset(r.w) && <span className="opacity-70"> · {reset(r.w)}</span>}
        </span>
      ))}
      {u.source === 'turn' && u.seen_at && <span className="max-w-60 opacity-70">{t('usage.seen', { when: fmtRelative(u.seen_at, lang) })}</span>}
    </div>
  )
  return (
    <>
    <Tooltip content={details} side="right">
      <div className={cn('grid gap-1.5 px-2.5 py-1.5', collapsed && 'px-1')} aria-label={title}>
        {rows.map((r) =>
          collapsed ? (
            <ProgressBar key={r.key} value={used(r.w)} tone={tone(r.w)} label={r.label} className="h-1" />
          ) : (
            <div key={r.key} className="grid gap-1">
              <div className="flex justify-between text-[11px] leading-none text-muted-foreground">
                <span>{r.label}</span>
                <span className="tabular-nums">{t('usage.used', { pct: used(r.w) })}</span>
              </div>
              <ProgressBar value={used(r.w)} tone={tone(r.w)} label={r.label} className="h-1" />
            </div>
          ),
        )}
      </div>
    </Tooltip>
    {others.length > 0 && <ProviderUsageRows items={others} collapsed={collapsed} />}
    </>
  )
}
