# Modified for DocLayout; see NOTICE for a summary of changes.
"""API client and process-shared lazy local layout lifecycle."""

from doclayout.services.layout import (
    LayoutConfigurationError,
    LayoutPreparation,
    LayoutService,
)
from doclayout.services.openai import OpenAIService
from doclayout.settings import settings


def create_layout_service() -> LayoutService:
    device = settings.DOCLAYOUT_LAYOUT_DEVICE
    if device not in ("auto", "cpu", "cuda"):
        raise LayoutConfigurationError("Layout device must be auto, cpu, or cuda.")
    return LayoutService(device, settings.DOCLAYOUT_LAYOUT_CACHE_DIR)


def create_model_dict() -> dict:
    layout = create_layout_service()
    return {"extraction_service": OpenAIService(), "layout_service": layout}


def prepare_layout_model(model_dict: dict) -> LayoutPreparation:
    return model_dict["layout_service"].prepare()


def shutdown_models(model_dict: dict) -> None:
    service = model_dict.get("extraction_service")
    if service is not None:
        service.close()
