"""Reject retired model and OCR controls at every configuration boundary."""

DEFAULT_MODEL = "gpt-6.1-sol"
MODEL_CHOICES = ("gpt-6-luna", "gpt-6.1-sol")


def validate_model(model):
    """Reject unsupported stage models before any provider request."""
    if model not in MODEL_CHOICES:
        raise ValueError("Model must be gpt-6-luna or gpt-6.1-sol.")
    return model


def conversion_models(config=None):
    """Resolve page reading and enabled refinement models from conversion settings."""
    if config is None:
        config = {}
    elif not isinstance(config, dict):
        config = config.model_dump()
    page = validate_model(
        config.get("PdfConverter_page_model", config.get("page_model", DEFAULT_MODEL))
    )
    refinement = validate_model(
        config.get(
            "PdfConverter_refinement_model",
            config.get("refinement_model", DEFAULT_MODEL),
        )
    )
    enabled = config.get("PdfConverter_use_llm", config.get("use_llm", False))
    return page, refinement if enabled else None


REMOVED = {
    "mode",
    "force_ocr",
    "disable_ocr",
    "strip_existing_ocr",
    "keep_chars",
    "pdftext_workers",
    "cache_pdftext_pages",
    "disable_multiprocessing",
    "device",
    "dtype",
    "attention_implementation",
    "inference_manager",
    "inference_backend",
    "recognition_model",
    "layout_model",
    "fast_layout_model",
    "ocr_error_model",
    "llm_service",
    "openai_model",
    "openai_api_key",
    "openai_base_url",
    "openai_image_format",
    "total_torch_threads",
    "retry_wait_time",
    "force_layout_block",
    "ocr_full_page",
    "use_pdftext_reading_order",
    "expand_block_types",
    "max_expand_frac",
    "ocr_error_batch_size",
    "layout_coverage_min_lines",
    "layout_coverage_threshold",
    "provider_line_provider_line_min_overlap_pct",
    "overlap_line_fraction_threshold",
    "excluded_for_coverage",
    "block_ocr_promote_fraction",
    "min_ocr_block_area_fraction",
    "empty_block_contained_threshold",
    "min_garbled_text_chars",
    "block_garbled_check_min_page_score",
    "block_ocr_skip_types",
    "skip_ocr_blocks",
    "default_token_budget",
    "min_recon_score",
    "ocr_table_token_floor",
    "ocr_invalid_chars",
    "ocr_space_threshold",
    "ocr_newline_threshold",
    "ocr_alphanum_threshold",
    "image_threshold",
    "disable_links",
}


def validate_config(config):
    """Reject removed configuration keys in a mapping or Pydantic config.

    Raises:
        ValueError: If a removed key or provider prefix is present.
    """
    if config is None:
        return
    values = config if isinstance(config, dict) else config.model_dump()
    conversion_models(values)
    invalid = sorted(
        key
        for key in values
        if (
            key.split("_", 1)[-1] in REMOVED
            or key in REMOVED
            or key.lower().startswith(
                (
                    "surya",
                    "torch",
                    "gemini",
                    "google",
                    "claude",
                    "anthropic",
                    "ollama",
                    "vertex",
                    "azure",
                    "openrouter",
                )
            )
        )
    )
    if invalid:
        raise ValueError(
            "Removed configuration: "
            + ", ".join(invalid)
            + ". Supported models are gpt-6-luna and gpt-6.1-sol. Use OPENAI_API_KEY/OPENAI_BASE_URL "
            "in the environment; use_llm enables optional extra refinement."
        )
