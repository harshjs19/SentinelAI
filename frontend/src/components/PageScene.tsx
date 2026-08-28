import type { ReactNode } from "react";

export type PageSceneVariant =
  | "fleet"
  | "machine"
  | "history"
  | "report"
  | "models"
  | "analysis";

export interface PageSceneItem {
  label: string;
  meta?: string;
  tone?: "accent" | "positive" | "warning" | "danger" | "neutral";
}

const scenePaths: Record<PageSceneVariant, { primary: string; secondary: string }> = {
  fleet: {
    primary: "M18 148 C94 48 196 38 304 96 S484 174 582 54",
    secondary: "M4 88 C108 168 210 182 318 112 S496 30 604 126",
  },
  machine: {
    primary: "M24 110 C104 22 222 24 302 110 S500 204 588 96",
    secondary: "M80 182 C162 86 246 66 338 98 S482 144 570 42",
  },
  history: {
    primary: "M42 184 L132 146 L232 116 L340 86 L452 54 L568 28",
    secondary: "M42 204 L132 174 L232 150 L340 126 L452 108 L568 94",
  },
  report: {
    primary: "M18 160 L130 118 L246 144 L360 70 L472 92 L592 32",
    secondary: "M18 78 L130 118 L246 64 L360 70 L472 30 L592 32",
  },
  models: {
    primary: "M20 126 C120 42 210 46 304 110 S478 190 588 72",
    secondary: "M34 58 C132 146 226 170 318 102 S492 32 580 146",
  },
  analysis: {
    primary: "M14 116 C64 116 78 52 128 52 S194 176 250 176 S316 44 376 44 S448 130 594 130",
    secondary: "M14 148 C96 148 122 92 184 92 S280 154 350 154 S450 74 594 74",
  },
};

export function PageScene({
  variant,
  kicker,
  title,
  note,
  items = [],
  footer,
  compact = false,
}: {
  variant: PageSceneVariant;
  kicker: string;
  title: string;
  note: string;
  items?: PageSceneItem[];
  footer?: ReactNode;
  compact?: boolean;
}) {
  const paths = scenePaths[variant];
  const visibleItems = items.slice(0, 5);

  return (
    <aside className={`page-scene page-scene--${variant} ${compact ? "page-scene--compact" : ""}`}>
      <div className="page-scene__geometry" aria-hidden="true">
        <span className="page-scene__plane page-scene__plane--back" />
        <span className="page-scene__plane page-scene__plane--front" />
        <span className="page-scene__axis page-scene__axis--x" />
        <span className="page-scene__axis page-scene__axis--y" />
        <svg viewBox="0 0 610 220" preserveAspectRatio="none">
          <path className="page-scene__path page-scene__path--secondary" d={paths.secondary} />
          <path className="page-scene__path page-scene__path--primary" d={paths.primary} />
        </svg>
        <span className="page-scene__orbit page-scene__orbit--outer" />
        <span className="page-scene__orbit page-scene__orbit--inner" />
        <span className="page-scene__nucleus"><i /><b /></span>
        {Array.from({ length: 6 }, (_, index) => (
          <i className={`page-scene__node page-scene__node--${index + 1}`} key={index} />
        ))}
        <i className="page-scene__signal" />
        <span className="page-scene__coordinate page-scene__coordinate--one">X.04 / Y.19</span>
        <span className="page-scene__coordinate page-scene__coordinate--two">ARCH / {variant.toUpperCase()}</span>
      </div>

      <div className="page-scene__content">
        <span className="page-scene__kicker">{kicker}</span>
        <strong>{title}</strong>
        <p>{note}</p>
        {visibleItems.length > 0 && (
          <ul className="page-scene__ledger">
            {visibleItems.map((item, index) => (
              <li className={`tone-${item.tone ?? "neutral"}`} key={`${item.label}-${index}`}>
                <i aria-hidden="true" />
                <span>{item.label}</span>
                {item.meta && <small>{item.meta}</small>}
              </li>
            ))}
          </ul>
        )}
        {footer && <div className="page-scene__footer">{footer}</div>}
      </div>
    </aside>
  );
}
