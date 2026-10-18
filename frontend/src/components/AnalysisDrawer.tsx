import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { FileAudio, FileImage, FlaskConical, LoaderCircle, Thermometer, UploadCloud, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";

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
import { useMaintenanceSubmission } from "./maintenanceSubmissionContext";
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

async function validateUpload(file: File, modality: "audio" | "vision" | "thermal"): Promise<void> {
  if (file.size === 0) throw new Error("The selected file is empty. Choose a non-empty source file.");
  const header = await new Promise<Uint8Array>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
    reader.onerror = () => reject(new Error("The selected file could not be read. Choose it again."));
    reader.readAsArrayBuffer(file.slice(0, 12));
  });
  if (modality === "audio") {
    const container = String.fromCharCode(...header.slice(0, 4));
    const wav = header.length >= 12
      && (container === "RIFF" || container === "RIFX")
      && String.fromCharCode(...header.slice(8, 12)) === "WAVE";
    if (!wav) throw new Error("Select a valid WAV audio file. MP3 and FLAC are not supported.");
    return;
  }
  const png = [137, 80, 78, 71, 13, 10, 26, 10].every((byte, index) => header[index] === byte);
  const jpeg = header[0] === 255 && header[1] === 216;
  if (!png && !jpeg) throw new Error("Select a valid PNG or JPEG image. TIFF is not supported.");
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
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { operation, submit, retry, acknowledgeSuccess } = useMaintenanceSubmission();
  const currentOperation = operation?.machineId === machineId ? operation : null;
  const submitting = preparing || currentOperation?.status === "submitting";
  const locked = preparing || operation !== null;
  const dialogRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  const onCreatedRef = useRef(onCreated);
  const mountedRef = useRef(false);
  const openRef = useRef(open);
  const preparingRef = useRef(false);
  const submittingRef = useRef(submitting);
  onCloseRef.current = onClose;
  onCreatedRef.current = onCreated;
  openRef.current = open;
  submittingRef.current = submitting;

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const capability = capabilities.find((item) => item.modality === modality && item.runtime_default)
    ?? capabilities.find((item) => item.modality === modality);
  const accepts = useMemo(() => modality === "audio" ? ".wav,audio/wav,audio/x-wav" : ".png,.jpg,.jpeg,image/png,image/jpeg", [modality]);

  useEffect(() => {
    if (!file || (modality !== "vision" && modality !== "thermal") || !/\.(png|jpe?g)$/i.test(file.name)) {
      setPreviewUrl(null);
      return;
    }
    const nextUrl = URL.createObjectURL(file);
    setPreviewUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [file, modality]);

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const appRoot = document.getElementById("root");
    const wasInert = appRoot?.inert ?? false;
    if (appRoot) appRoot.inert = true;
    closeButtonRef.current?.focus();

    const focusable = () => Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ) ?? []).filter((element) => element.getClientRects().length > 0);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !submittingRef.current) {
        event.preventDefault();
        onCloseRef.current();
      }
      if (event.key !== "Tab") return;
      const elements = focusable();
      const first = elements[0];
      const last = elements.at(-1);
      if (!first || !last) {
        event.preventDefault();
        dialogRef.current?.focus();
      } else if (!dialogRef.current?.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    const onFocusIn = (event: FocusEvent) => {
      if (!dialogRef.current?.contains(event.target as Node)) {
        closeButtonRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("focusin", onFocusIn);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("focusin", onFocusIn);
      if (appRoot) appRoot.inert = wasInert;
      if (previousFocus?.isConnected) previousFocus.focus();
      else document.querySelector<HTMLElement>('.nav-link[aria-current="page"]')?.focus();
    };
  }, [open]);

  const buildSubmission = async (): Promise<MaintenanceSubmission> => {
    if (modality === "timeseries") return { modality, samples: parseSamples(samplesText), intent, question: question.trim() || undefined };
    if (!file) throw new Error(`Select a ${modality} file before submitting.`);
    await validateUpload(file, modality);
    return { modality, file, intent, question: question.trim() || undefined };
  };

  const handleResult = (result: Awaited<ReturnType<typeof submit>>) => {
    if (!mountedRef.current || !openRef.current) return;
    if (result.kind === "success") {
      acknowledgeSuccess(machineId);
      onCreatedRef.current(result.report);
    }
    else if (result.kind === "rejected") setError(result.message);
    else if (result.kind === "busy") setError("Resolve the existing report request before starting another.");
  };

  const submitNew = async () => {
    if (preparingRef.current || operation) return;
    preparingRef.current = true;
    setPreparing(true);
    setError(null);
    try {
      const submission = await buildSubmission();
      if (!mountedRef.current || !openRef.current) return;
      handleResult(await submit(machineId, submission));
    } catch (reason) {
      if (mountedRef.current) setError(reason instanceof Error ? reason.message : "The submitted input is invalid.");
    } finally {
      preparingRef.current = false;
      if (mountedRef.current) setPreparing(false);
    }
  };

  const retryPending = async () => {
    if (submittingRef.current) return;
    setError(null);
    const result = await retry(machineId);
    if (result.kind !== "busy") handleResult(result);
  };

  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="drawer-layer">
          <motion.button className="drawer-backdrop" type="button" tabIndex={-1} aria-hidden="true" onClick={onClose} disabled={submitting} initial={reduced ? false : { opacity: 0, backdropFilter: "blur(0px)" }} animate={{ opacity: 1, backdropFilter: "blur(8px)" }} exit={{ opacity: 0, backdropFilter: "blur(0px)" }} transition={{ duration: reduced ? 0 : motionDuration.standard, ease: premiumEase }} />
          <motion.aside ref={dialogRef} tabIndex={-1} className="analysis-drawer glass-panel" role="dialog" aria-modal="true" aria-labelledby="analysis-title" initial={reduced ? false : { opacity: 0, x: 32, scale: 0.99 }} animate={{ opacity: 1, x: 0, scale: 1 }} exit={reduced ? undefined : { opacity: 0, x: 24, scale: 0.995 }} transition={{ duration: reduced ? 0 : motionDuration.standard, ease: premiumEase }}>
            <header className="analysis-drawer__header">
              <div><p className="eyebrow">New single-modality request</p><h2 id="analysis-title">Run Analysis</h2><span>{machineName}</span></div>
              <button ref={closeButtonRef} className="icon-button" type="button" aria-label="Close" onClick={onClose} disabled={submitting}><X /></button>
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
                {modalities.map(({ value, label, icon: Icon }) => <button key={value} type="button" disabled={locked} className={modality === value ? "is-selected" : ""} onClick={() => { setModality(value); setFile(null); setError(null); }}><Icon aria-hidden="true" /><span>{label}</span></button>)}
              </div></fieldset>

              {capability && <div className="selected-capability"><div><span>Runtime capability</span><code>{capability.model_id}</code></div><StatusBadge tone={lifecycleTone(capability.status)}>{humanize(capability.status)}</StatusBadge></div>}

              {modality === "timeseries" ? (
                <label className="field"><span>Time-series samples</span><small>Paste at least two raw channel-1 input rows. Feature engineering remains server-owned; no sample values are invented by the dashboard.</small><textarea rows={12} value={samplesText} disabled={locked} onChange={(event) => setSamplesText(event.target.value)} spellCheck={false} /></label>
              ) : (
                <label className={`file-drop ${file ? "file-drop--selected" : ""}`}><input key={modality} type="file" accept={accepts} disabled={locked} onChange={(event) => { setFile(event.target.files?.[0] ?? null); setError(null); }} /><span className="file-drop__icon"><UploadCloud aria-hidden="true" /></span><span>{file ? file.name : `Select ${modality} source`}</span><small>{modality === "audio" ? "WAV audio file only; no live audio acquisition." : "PNG or JPEG image only; no live sensor acquisition."}</small>{file && <small>{(file.size / 1024).toFixed(1)} KB / sent directly as multipart data</small>}{previewUrl && <img src={previewUrl} alt="Selected source preview" />}</label>
              )}

              <label className="field"><span>Copilot intent</span><select value={intent} disabled={locked} onChange={(event) => setIntent(event.target.value as CopilotIntent)}>{intents.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}</select></label>
              <label className="field"><span>Optional bounded question</span><textarea rows={3} maxLength={500} placeholder="Ask for an evidence-bounded explanation..." value={question} disabled={locked} onChange={(event) => setQuestion(event.target.value)} /><small>{question.length}/500 characters. Operational decisions require qualified human judgment.</small></label>

              {error && <div className="inline-error" role="alert">{error}</div>}
              {currentOperation?.status === "uncertain" && <div className="inline-error" role="alert">The report outcome could not be confirmed. Retry the exact request safely; inputs remain locked until resolved.</div>}
              {operation && operation.machineId !== machineId && <div className="inline-error" role="alert">A report request for another machine is {operation.status === "succeeded" ? "complete" : "still unresolved"}. Return to its machine before starting another analysis.</div>}
              {currentOperation?.status === "succeeded" && <div className="analysis-progress" role="status">The report was created while this view was inactive. Open the stored report or acknowledge it before starting another analysis.</div>}
              {submitting && <div className="analysis-progress" role="status"><span className="analysis-progress__core" aria-hidden="true"><LoaderCircle /></span><div><strong>Analyzing machine evidence…</strong><span>No fabricated progress percentage is shown.</span></div></div>}
            </div>

            <footer className="analysis-drawer__footer">
              <button className="button button--secondary" type="button" onClick={onClose} disabled={submitting}>Cancel</button>
              {operation && operation.machineId !== machineId
                ? <Link className="button button--primary" to={`/machines/${encodeURIComponent(operation.machineId)}`}>Return to originating machine</Link>
                : currentOperation?.status === "uncertain"
                  ? <button className="button button--primary" type="button" onClick={() => void retryPending()}>Retry exact request</button>
                  : currentOperation?.status === "succeeded" && currentOperation.report
                    ? <><button className="button button--secondary" type="button" onClick={() => acknowledgeSuccess(machineId)}>Start another analysis</button><button className="button button--primary" type="button" onClick={() => { acknowledgeSuccess(machineId); onCreatedRef.current(currentOperation.report!); }}>Open created report</button></>
                    : <button className="button button--primary" type="button" onClick={submitNew} disabled={locked}>{submitting ? "Analyzing..." : "Create verified report"}</button>}
            </footer>
          </motion.aside>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
