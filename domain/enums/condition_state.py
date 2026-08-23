from enum import StrEnum


class ConditionState(StrEnum):
    NORMAL = "normal"
    ABNORMAL = "abnormal"
    INDETERMINATE = "indeterminate"
