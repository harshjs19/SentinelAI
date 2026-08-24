from domain.entities.finding import Finding
from domain.entities.prediction import Prediction
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality
from modules.decision.exceptions import (
    UnsupportedPredictionLabelError,
    UnsupportedPredictionModalityError,
)

_TIMESERIES_CONDITIONS = {
    "healthy": ConditionState.NORMAL,
    "bearing_fault": ConditionState.ABNORMAL,
    "coupling_fault": ConditionState.ABNORMAL,
    "bent_shaft": ConditionState.ABNORMAL,
    "eccentric_rotor": ConditionState.ABNORMAL,
    "imbalance": ConditionState.ABNORMAL,
}

_AUDIO_CONDITIONS = {
    "healthy": ConditionState.NORMAL,
    "acoustic_anomaly": ConditionState.ABNORMAL,
}

_VISION_CONDITIONS = {
    "healthy": ConditionState.NORMAL,
    "visual_anomaly": ConditionState.ABNORMAL,
}

_THERMAL_CONDITIONS = {
    "healthy": ConditionState.NORMAL,
    "bearing_fault": ConditionState.ABNORMAL,
    "half_broken_rotor_bar": ConditionState.ABNORMAL,
    "broken_rotor_bar": ConditionState.ABNORMAL,
    "imbalance": ConditionState.ABNORMAL,
    "misalignment": ConditionState.ABNORMAL,
    "gear_wear_25": ConditionState.ABNORMAL,
    "gear_wear_50": ConditionState.ABNORMAL,
    "gear_wear_75": ConditionState.ABNORMAL,
}


def normalize_prediction(prediction: Prediction) -> Finding:
    conditions = {
        Modality.TIMESERIES: _TIMESERIES_CONDITIONS,
        Modality.AUDIO: _AUDIO_CONDITIONS,
        Modality.VISION: _VISION_CONDITIONS,
        Modality.THERMAL: _THERMAL_CONDITIONS,
    }.get(prediction.modality)
    if conditions is None:
        raise UnsupportedPredictionModalityError(
            f"Unsupported prediction modality: {prediction.modality.value}"
        )

    try:
        condition = conditions[prediction.label]
    except KeyError as error:
        raise UnsupportedPredictionLabelError(
            f"Unsupported {prediction.modality.value} prediction label: {prediction.label}"
        ) from error

    return Finding(
        modality=prediction.modality,
        code=prediction.label,
        condition=condition,
        confidence=prediction.confidence,
        confidence_kind=ConfidenceKind.RAW,
    )
