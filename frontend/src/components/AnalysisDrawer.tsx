import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { FileAudio, FileImage, FlaskConical, LoaderCircle, Thermometer, UploadCloud, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../api/client";
import { createIdempotencyKey, createMaintenanceReport } from "../api/reports";
import type {
  CopilotIntent,
  MaintenanceReport,
  MaintenanceSubmission,
  ModelCapability,
  Modality,
  TimeseriesSample,
} from "../api/types";
import { humanize } from "../lib/format";
import { motionDuration, premiumEase } from "../lib/motion";
import { lifecycleTone } from "./badgeTone";
import { PageScene } from "./PageScene";
import { StatusBadge } from "./StatusBadge";

const modalities: { value: Modality; label: string; icon: typeof FileAudio }[] = [
  { value: "timeseries", label: "Time-Series", icon: FlaskConical },
  { value: "audio", label: "Audio", icon: FileAudio },
  { value: "vision", label: "Vision", icon: FileImage },
  { value: "thermal", label: "Thermal", icon: Thermometer },
];

const intents: { value: CopilotIntent; label: string }[] = [
  { value: "summarize_analysis", label: "Summarize analysis" },
  { value: "explain_finding", label: "Explain finding" },
  { value: "explain_confidence", label: "Explain confidence" },
  { value: "inspection_considerations", label: "Inspection considerations" },
  { value: "explain_limitations", label: "Explain limitations" },
];

interface PendingRequest {
  submission: MaintenanceSubmission;
  idempotencyKey: string;
}

function parseSamples(value: string): TimeseriesSample[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error("Enter samples as a valid JSON array.");
  }
  if (!Array.isArray(parsed) || parsed.length < 2) throw new Error("Provide at least two sample rows.");
  const keys: (keyof TimeseriesSample)[] = ["ch1_bias", "ch1_derivedPk", "ch1_direct", "ch1_directRMS", "ch1_velocityPk", "ch1_velocityRMS"];
  return parsed.map((sample, index) => {
    if (typeof sample !== "object" || sample === null || Array.isArray(sample)) throw new Error(`Sample ${index + 1} must be an object.`);
    const record = sample as Record<string, unknown>;
    for (const key of keys) {
      if (typeof record[key] !== "number" || !Number.isFinite(record[key])) throw new Error(`Sample ${index + 1} requires a finite numeric ${key}.`);
    }
    return Object.fromEntries(keys.map((key) => [key, record[key]])) as unknown as TimeseriesSample;
  });
}

export function AnalysisDrawer({
  open,
  machineId,
  machineName,
  capabilities,
  onClose,
  onCreated,
}: {
  open: boolean;
  machineId: string;
  machineName: string;
  capabilities: ModelCapability[];
  onClose: () => void;
  onCreated: (report: MaintenanceReport) => void;
}) {
  const reduced = useReducedMotion();
  const [modality, setModality] = useState<Modality>("timeseries");
  const [intent, setIntent] = useState<CopilotIntent>("summarize_analysis");
  const [question, setQuestion] = useState("");
  const [samplesText, setSamplesText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingRetry, setPendingRetry] = useState<PendingRequest | null>(null);

  const capability = capabilities.find((item) => item.modality === modality && item.runtime_default)
    ?? capabilities.find((item) => item.modality === modality);
  const accepts = useMemo(() => modality === "audio" ? "audio/*,.wav,.mp3,.flac" : "image/*,.png,.jpg,.jpeg,.tiff,.tif", [modality]);

  useEffect(() => {
    if (!file || (modality !== "vision" && modality !== "thermal") || !file.type.startsWith("image/")) {
      setPreviewUrl(null);
      return;
    }
    const nextUrl = URL.createObjectURL(file);
    setPreviewUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [file, modality]);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape" && !submitting) onClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose, open, submitting]);

  const buildSubmission = (): MaintenanceSubmission => {
    if (modality === "timeseries") return { modality, samples: parseSamples(samplesText), intent, question: question.trim() || undefined };
    if (!file) throw new Error(`Select a ${modality} file before submitting.`);
    return { modality, file, intent, question: question.trim() || undefined };
  };

  const send = async (pending: PendingRequest) => {
    setSubmitting(true);
    setError(null);
    try {
      const report = await createMaintenanceReport(machineId, pending.submission, pending.idempotencyKey);
      setPendingRetry(null);
      onCreated(report);
    } catch (reason) {
      if (reason instanceof ApiError && reason.transportUncertain) setPendingRetry(pending);
      else setPendingRetry(null);
      setError(reason instanceof ApiError ? reason.message : "The report could not be created.");
    } finally {
      setSubmitting(false);
    }
  };

  const submitNew = () => {
    try {
      const pending = { submission: buildSubmission(), idempotencyKey: createIdempotencyKey() };
      setPendingRetry(null);
      void send(pending);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The submitted input is invalid.");
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <div className="drawer-layer">
          <motion.button className="drawer-backdrop" type="button" aria-label="Close analysis drawer" onClick={onClose} initial={reduced ? false : { opacity: 0, backdropFilter: "blur(0px)" }} animate={{ opacity: 1, backdropFilter: "blur(8px)" }} exit={{ opacity: 0, backdropFilter: "blur(0px)" }} transition={{ duration: reduced ? 0 : motionDuration.standard, ease: premiumEase }} />
          <motion.aside className="analysis-drawer glass-panel" role="dialog" aria-modal="true" aria-labelledby="analysis-title" initial={reduced ? false : { opacity: 0, x: 32, scale: 0.99 }} animate={{ opacity: 1, x: 0, scale: 1 }} exit={reduced ? undefined : { opacity: 0, x: 24, scale: 0.995 }} transition={{ duration: reduced ? 0 : motionDuration.standard, ease: premiumEase }}>
            <header className="analysis-drawer__header">
              <div><p className="eyebrow">New single-modality request</p><h2 id="analysis-title">Run Analysis</h2><span>{machineName}</span></div>
              <button className="icon-button" type="button" aria-label="Close" onClick={onClose} disabled={submitting}><X /></button>
            </header>

            <div className={`analysis-drawer__scene analysis-drawer__scene--${modality}`}>
              <PageScene
                compact
                variant="analysis"
                kicker="Independent modality chamber"
                title={`${humanize(modality)} analysis module`}
                note="Procedural geometry indicates the selected module only; it does not inspect, measure, or preview the submitted signal."
                items={[
                  { label: capability?.model_id ?? "Capability not declared", meta: capability ? humanize(capability.status) : "no runtime model", tone: capability?.status === "validated_baseline" ? "positive" : capability?.status === "rejected_experiment" ? "danger" : "warning" },
                  { label: humanize(intent), meta: "bounded Copilot intent", tone: "accent" },
                ]}
              />
            </div>

            <div className="analysis-drawer__body">
              <fieldset className="modality-picker"><legend>Choose one intelligence module</legend><div>
                {modalities.map(({ value, label, icon: Icon }) => <button key={value} type="button" className={modality === value ? "is-selected" : ""} onClick={() => { setModality(value); setFile(null); setError(null); setPendingRetry(null); }}><Icon aria-hidden="true" /><span>{label}</span></button>)}
              </div></fieldset>

              {capability && <div className="selected-capability"><div><span>Runtime capability</span><code>{capability.model_id}</code></div><StatusBadge tone={lifecycleTone(capability.status)}>{humanize(capability.status)}</StatusBadge></div>}

              {modality === "timeseries" ? (
                <label className="field"><span>Time-series samples</span><small>Paste at least two raw channel-1 input rows. Feature engineering remains server-owned; no sample values are invented by the dashboard.</small><textarea rows={12} value={samplesText} onChange={(event) => { setSamplesText(event.target.value); setPendingRetry(null); }} spellCheck={false} /></label>
              ) : (
                <label className={`file-drop ${file ? "file-drop--selected" : ""}`}><input type="file" accept={accepts} onChange={(event) => { setFile(event.target.files?.[0] ?? null); setPendingRetry(null); }} /><span className="file-drop__icon"><UploadCloud aria-hidden="true" /></span><span>{file ? file.name : `Select ${modality} source`}</span><small>{file ? `${(file.size / 1024).toFixed(1)} KB / sent directly as multipart data` : "Raw browser File only — never base64 encoded or persisted locally."}</small>{previewUrl && <img src={previewUrl} alt="Selected source preview" />}</label>
              )}

              <label className="field"><span>Copilot intent</span><select value={intent} onChange={(event) => { setIntent(event.target.value as CopilotIntent); setPendingRetry(null); }}>{intents.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}</select></label>
              <label className="field"><span>Optional bounded question</span><textarea rows={3} maxLength={500} placeholder="Ask for an evidence-bounded explanation..." value={question} onChange={(event) => { setQuestion(event.target.value); setPendingRetry(null); }} /><small>{question.length}/500 characters. Operational decisions require qualified human judgment.</small></label>

              {error && <div className="inline-error" role="alert">{error}</div>}
              {submitting && <div className="analysis-progress" role="status"><span className="analysis-progress__core" aria-hidden="true"><LoaderCircle /></span><div><strong>Analyzing machine evidence…</strong><span>No fabricated progress percentage is shown.</span></div></div>}
            </div>

            <footer className="analysis-drawer__footer">
              <button className="button button--secondary" type="button" onClick={onClose} disabled={submitting}>Cancel</button>
              {pendingRetry && !submitting ? <button className="button button--primary" type="button" onClick={() => void send(pendingRetry)}>Retry exact request</button> : <button className="button button--primary" type="button" onClick={submitNew} disabled={submitting}>{submitting ? "Analyzing..." : "Create verified report"}</button>}
            </footer>
          </motion.aside>
        </div>
      )}
    </AnimatePresence>
  );
}
