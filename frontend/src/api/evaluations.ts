export interface ModelEvaluationSummary {
  model_id: string;
  evaluation_reference: string;
  source_digest_sha256: string;
  metric_label: string;
  metric_value: number;
  known_limitation: string;
}

interface ModelEvaluationIndex {
  schema_version: string;
  models: ModelEvaluationSummary[];
}

let indexPromise: Promise<ModelEvaluationIndex> | null = null;

function validateIndex(value: unknown): ModelEvaluationIndex {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Evaluation index must be an object");
  }
  const index = value as Record<string, unknown>;
  if (index.schema_version !== "1" || !Array.isArray(index.models) || index.models.length === 0) {
    throw new Error("Evaluation index schema is invalid");
  }
  const ids = new Set<string>();
  index.models.forEach((value, position) => {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      throw new Error(`Evaluation record ${position} is invalid`);
    }
    const item = value as Record<string, unknown>;
    for (const field of [
      "model_id",
      "evaluation_reference",
      "source_digest_sha256",
      "metric_label",
      "known_limitation",
    ]) {
      if (typeof item[field] !== "string" || item[field].trim().length === 0) {
        throw new Error(`Evaluation record ${position}.${field} is invalid`);
      }
    }
    if (
      typeof item.metric_value !== "number" ||
      !Number.isFinite(item.metric_value) ||
      item.metric_value < 0 ||
      item.metric_value > 1
    ) {
      throw new Error(`Evaluation record ${position}.metric_value is invalid`);
    }
    ids.add(item.model_id as string);
  });
  if (ids.size !== index.models.length) throw new Error("Evaluation model IDs must be unique");
  return value as ModelEvaluationIndex;
}

export function listModelEvaluationSummaries(signal?: AbortSignal): Promise<ModelEvaluationSummary[]> {
  if (!indexPromise) {
    indexPromise = fetch(`${import.meta.env.BASE_URL}model-evaluations.json`, {
      headers: { Accept: "application/json" },
      signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("Evaluation index request failed");
        return validateIndex(await response.json());
      })
      .catch(() => {
        indexPromise = null;
        throw new ApiError("Verified model evaluation summaries could not be loaded.");
      });
  }
  return indexPromise.then((index) => index.models);
}
import { ApiError } from "./client";
