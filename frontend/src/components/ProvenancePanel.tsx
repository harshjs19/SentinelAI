import { Fingerprint, Radio, ShieldCheck } from "lucide-react";

import type { ProducingModel } from "../api/types";
import { humanize } from "../lib/format";
import { lifecycleTone } from "./badgeTone";
import { StatusBadge } from "./StatusBadge";

export function ProvenancePanel({ models }: { models: ProducingModel[] }) {
  return (
    <section className="provenance-panel glass-card" aria-labelledby="provenance-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Captured at execution</p>
          <h2 id="provenance-title">Producing Model</h2>
        </div>
        <Fingerprint aria-hidden="true" />
      </div>
      <div className="provenance-fingerprint" aria-hidden="true"><i /><i /><i /></div>
      <div className="provenance-list">
        {models.map((model) => (
          <article key={model.model_id}>
            <div className="provenance-list__identity">
              <span className="provenance-list__glyph">
                <ShieldCheck aria-hidden="true" />
              </span>
              <div>
                <code>{model.model_id}</code>
                <span>{humanize(model.modality)}</span>
              </div>
              <StatusBadge tone={lifecycleTone(model.status)}>
                {humanize(model.status)}
              </StatusBadge>
            </div>
            <dl className="technical-grid">
              <div>
                <dt>Validated scope</dt>
                <dd>{model.validated_scope}</dd>
              </div>
              <div>
                <dt>Confidence semantics</dt>
                <dd>{humanize(model.confidence_semantics)}</dd>
              </div>
              <div>
                <dt>Runtime default at execution</dt>
                <dd>
                  <Radio size={14} aria-hidden="true" /> {model.runtime_default_at_execution ? "Yes" : "No"}
                </dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
      <p className="provenance-panel__note">
        Historical identity is read from this stored report, never substituted from current defaults.
      </p>
    </section>
  );
}
