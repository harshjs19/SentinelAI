export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="brand-lockup" aria-label="SentinelAI">
      <span className="brand-mark__field">
        <svg className="brand-mark" viewBox="0 0 48 48" aria-hidden="true">
          <path d="M24 4 40 10v12c0 10.4-6.6 18.1-16 22C14.6 40.1 8 32.4 8 22V10L24 4Z" />
          <path d="M16 25h5l3-8 4 14 3-6h3" />
          <circle cx="24" cy="11" r="2" />
        </svg>
        <i aria-hidden="true" />
      </span>
      {!compact && (
        <div>
          <strong>SentinelAI</strong>
          <span>Evidence / Intelligence</span>
        </div>
      )}
    </div>
  );
}
