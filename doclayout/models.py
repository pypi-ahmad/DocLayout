# Modified for DocLayout; see NOTICE for a summary of changes.
"""API clients and a borrowed process-level lazy layout engine."""

from doclayout.services.openai import OpenAIService


def create_model_dict() -> dict:
    """Create an owned Sol client and borrow the process-cached layout engine.

    Returns:
        dict: Conversion artifacts. The layout engine remains lazy; this call
        does not download weights, prepare a provider, or run inference.
    """
    from doclayout.layout import get_layout_engine

    return {"extraction_service": OpenAIService(), "layout_engine": get_layout_engine()}


def shutdown_models(model_dict: dict) -> None:
    """Close the owned Sol client without closing the shared layout engine.

    Args:
        model_dict: Artifacts returned by create_model_dict. The layout session
            is released separately at process exit.
    """
    service = model_dict.get("extraction_service")
    if service is not None:
        service.close()
