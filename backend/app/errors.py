from fastapi import HTTPException, status


def model_unavailable_error(model_name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"{model_name} model is not available",
    )
