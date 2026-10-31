/** The DocumentLab mark: a short run of barcode bars with one bar in the accent colour. */
export function Logo({ className = '' }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <svg width="26" height="20" viewBox="0 0 26 20" aria-hidden="true">
        <rect x="0" y="0" width="2.5" height="20" fill="currentColor" />
        <rect x="4.5" y="0" width="1.2" height="20" fill="currentColor" />
        <rect x="7.8" y="0" width="3.6" height="20" fill="currentColor" />
        <rect x="13.5" y="0" width="1.2" height="20" fill="currentColor" />
        <rect x="16.8" y="0" width="2.4" height="20" fill="currentColor" />
        <rect x="21.4" y="0" width="4.2" height="20" fill="#3B74FF" />
      </svg>
      <span className="text-[1.05rem] font-semibold tracking-[-0.01em]">DocumentLab</span>
    </span>
  )
}
