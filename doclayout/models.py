# Modified for DocLayout; see NOTICE for a summary of changes.
"""API service lifecycle. No local model weights or inference servers."""

from doclayout.services.openai import OpenAIService


def create_model_dict() -> dict:
    return {"extraction_service": OpenAIService()}


def shutdown_models(model_dict: dict) -> None:
    service = model_dict.get("extraction_service")
    if service is not None:
        service.close()
