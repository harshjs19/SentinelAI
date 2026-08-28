import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { BookOpen, ChevronDown } from "lucide-react";
import { useState } from "react";

import type { MaintenanceCitation } from "../api/types";
import { humanize } from "../lib/format";
import { motionDuration, premiumEase } from "../lib/motion";

export function CitationCard({ citation }: { citation: MaintenanceCitation }) {
  const [open, setOpen] = useState(false);
  const reduced = useReducedMotion();
  return (
    <article className={`citation-card glass-card ${open ? "citation-card--open" : ""}`}>
      <button type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <span className="citation-card__id">[{citation.citation_id}]</span>
        <span>
          <strong>{citation.title}</strong>
          <small>{citation.publisher}</small>
        </span>
        <ChevronDown aria-hidden="true" />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            className="citation-card__details"
            initial={reduced ? false : { opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={reduced ? undefined : { opacity: 0, height: 0 }}
            transition={{ duration: reduced ? 0 : motionDuration.standard, ease: premiumEase }}
          >
            <BookOpen aria-hidden="true" />
            <dl>
              <div>
                <dt>Section</dt>
                <dd>{citation.section}</dd>
              </div>
              <div>
                <dt>Knowledge lane</dt>
                <dd>{humanize(citation.source_lane)}</dd>
              </div>
              <div>
                <dt>Evidence scope</dt>
                <dd>{citation.asset_type}</dd>
              </div>
              <div>
                <dt>Matched intent</dt>
                <dd>{citation.matched_intent}</dd>
              </div>
            </dl>
          </motion.div>
        )}
      </AnimatePresence>
    </article>
  );
}
