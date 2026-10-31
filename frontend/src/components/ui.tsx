import { cx } from '../lib/format'
import type { ButtonHTMLAttributes, ReactNode } from 'react'


export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        <h1 className="text-[1.75rem] leading-tight font-semibold tracking-[-0.01em] text-ink">{title}</h1>
        {description && <p className="mt-2 text-[0.95rem] leading-relaxed text-muted">{description}</p>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </header>
  )
}

export function Panel({ title, aside, children, className }: { title?: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx('rounded-[10px] border border-rule bg-paper', className)}>
      {title && (
        <div className="flex items-center justify-between gap-4 border-b border-rule px-5 py-3.5">
          <h2 className="text-[0.95rem] font-semibold text-ink">{title}</h2>
          {aside && <div className="text-sm text-muted">{aside}</div>}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  )
}

type Variant = 'primary' | 'secondary' | 'danger'

export function Button({ variant = 'secondary', className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  const styles: Record<Variant, string> = {
    primary: 'bg-electric text-white hover:bg-[#1749D6] border-electric',
    secondary: 'bg-paper text-ink hover:bg-canvas border-rule',
    danger: 'bg-paper text-fail hover:bg-[#FCEEEF] border-rule',
  }
  return (
    <button
      {...props}
      className={cx(
        'inline-flex h-9 items-center justify-center gap-2 rounded-md border px-3.5 text-sm font-medium',
        'disabled:cursor-not-allowed disabled:opacity-50',
        styles[variant],
        className,
      )}
    />
  )
}

/** A figure with its label. Pass value=null for things that do not exist yet: it says so instead of showing 0. */
export function Figure({ label, value, note }: { label: string; value: number | null; note?: string }) {
  const unavailable = value === null
  return (
    <div className={cx('rounded-[10px] px-5 py-4', unavailable ? 'border border-dashed border-rule bg-transparent' : 'border border-rule bg-paper')}>
      <div className="text-sm text-muted">{label}</div>
      {unavailable ? (
        <div className="mt-2 text-sm text-faint">{note ?? 'Not available yet'}</div>
      ) : (
        <div className="mt-1 text-[2rem] leading-none font-semibold tabular-nums text-ink">{value.toLocaleString('en-GB')}</div>
      )}
      {!unavailable && note && <div className="mt-2 text-xs text-faint">{note}</div>}
    </div>
  )
}

export function Notice({ tone = 'info', children }: { tone?: 'info' | 'error' | 'success'; children: ReactNode }) {
  const styles = {
    info: 'border-rule bg-canvas text-ink',
    error: 'border-[#F1C4C7] bg-[#FCEEEF] text-fail',
    success: 'border-[#BFE3D3] bg-[#EAF6F0] text-pass',
  }
  return <div role={tone === 'error' ? 'alert' : 'status'} className={cx('rounded-md border px-4 py-3 text-sm', styles[tone])}>{children}</div>
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return <p className="py-6 text-sm text-muted" role="status">{label}…</p>
}
