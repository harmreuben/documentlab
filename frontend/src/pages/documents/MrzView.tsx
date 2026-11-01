import type { MrzData } from '../../api/documents'
import { STATUS } from '../../components/StatusBadge'
import { cx } from '../../lib/format'

const FIELD_NAMES: Record<string, string> = {
  document_type: 'Type', issuing_state: 'Issuer', name: 'Name', document_number: 'Document number',
  nationality: 'Nationality', birth_date: 'Birth date', sex: 'Sex', expiry_date: 'Expiry',
  optional_data: 'Optional data', check: 'Check digit',
}

/**
 * The machine-readable zone, character by character. Check digits are coloured by their result,
 * and every character DocumentLab corrected is highlighted with what was originally read.
 */
export function MrzView({ mrz }: { mrz: MrzData }) {
  const digitStatus = new Map<string, string>()  // "line:index" (1-based) -> status
  for (const check of mrz.checks) {
    if (check.code.startsWith('mrz.check_digit') && check.positions?.length) {
      const [line, index] = check.positions[check.positions.length - 1]
      digitStatus.set(`${line}:${index}`, check.status)
    }
  }
  const corrected = new Map(mrz.corrections.filter((c) => c.found).map((c) => [`${c.line}:${c.index}`, c]))
  const restored = mrz.corrections.filter((c) => !c.found)

  return (
    <div>
      <div className="overflow-x-auto rounded-md bg-ink px-4 py-4 sm:px-5">
        <div className="inline-block font-mono text-[0.95rem] leading-none text-white sm:text-base" role="img"
          aria-label={`Machine-readable zone, ${mrz.layout}, ${mrz.lines.length} lines`}>
          {mrz.lines.map((line, li) => {
            const segments = mrz.segments.filter((s) => s.line === li + 1)
            return (
              <div key={li} className="mb-3 last:mb-0">
                <div className="flex">
                  {segments.map((seg) => (
                    <span key={seg.start} title={FIELD_NAMES[seg.field] ?? seg.field}
                      className={cx('flex border-b-2 pb-1', seg.field === 'check' ? 'border-transparent' : 'border-ink-line')}
                      style={{ marginRight: 2 }}>
                      {[...line.slice(seg.start, seg.end)].map((ch, i) => {
                        const key = `${li + 1}:${seg.start + i + 1}`
                        const digit = digitStatus.get(key)
                        const fix = corrected.get(key)
                        return (
                          <span key={i} title={fix ? `Read as "${fix.found}", corrected to "${fix.used}". ${fix.reason}` : undefined}
                            className={cx('inline-flex h-7 w-[1ch] items-center justify-center',
                              ch === '<' && !digit && !fix && 'text-[#56637A]',
                              fix && 'rounded-sm bg-[#A86200] text-white')}
                            style={digit ? { outline: `2px solid ${STATUS[digit as keyof typeof STATUS].stroke}`, outlineOffset: -1,
                              borderRadius: 2, background: digit === 'FAIL' ? STATUS.FAIL.stroke : undefined } : undefined}>
                            {ch}
                          </span>
                        )
                      })}
                    </span>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-muted">
        <li className="flex items-center gap-1.5"><span className="inline-block size-3 rounded-sm outline-2 outline-pass" /> Check digit passes</li>
        <li className="flex items-center gap-1.5"><span className="inline-block size-3 rounded-sm bg-fail" /> Check digit fails</li>
        <li className="flex items-center gap-1.5"><span className="inline-block size-3 rounded-sm bg-review" /> Corrected character (hover for details)</li>
        <li>Hover a group to see which field it is.</li>
      </ul>
      {restored.length > 0 && (
        <p className="mt-2 text-xs text-review">{restored.map((r) => `Line ${r.line}: ${r.reason}`).join(' ')}</p>
      )}
    </div>
  )
}
