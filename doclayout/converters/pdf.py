# Modified for DocLayout; see NOTICE for a summary of changes.
import io
import os
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from typing import Annotated, Any, Dict, List, Optional, Tuple, Type, Union, cast

from doclayout.builders.document import DocumentBuilder
from doclayout.builders.structure import StructureBuilder
from doclayout.config.validation import validate_config
from doclayout.converters import BaseConverter
from doclayout.processors import BaseProcessor
from doclayout.processors.blank_page import BlankPageProcessor
from doclayout.processors.block_relabel import BlockRelabelProcessor
from doclayout.processors.blockquote import BlockquoteProcessor
from doclayout.processors.code import CodeProcessor
from doclayout.processors.debug import DebugProcessor
from doclayout.processors.document_toc import DocumentTOCProcessor
from doclayout.processors.footnote import FootnoteProcessor
from doclayout.processors.ignoretext import IgnoreTextProcessor
from doclayout.processors.line_merge import LineMergeProcessor
from doclayout.processors.line_numbers import LineNumbersProcessor
from doclayout.processors.list import ListProcessor
from doclayout.processors.llm.llm_complex import LLMComplexRegionProcessor
from doclayout.processors.llm.llm_equation import LLMEquationProcessor
from doclayout.processors.llm.llm_form import LLMFormProcessor
from doclayout.processors.llm.llm_handwriting import LLMHandwritingProcessor
from doclayout.processors.llm.llm_image_description import LLMImageDescriptionProcessor
from doclayout.processors.llm.llm_mathblock import LLMMathBlockProcessor
from doclayout.processors.llm.llm_page_correction import LLMPageCorrectionProcessor
from doclayout.processors.llm.llm_sectionheader import LLMSectionHeaderProcessor
from doclayout.processors.llm.llm_table import LLMTableProcessor
from doclayout.processors.llm.llm_table_merge import LLMTableMergeProcessor
from doclayout.processors.marginalia import MarginaliaProcessor
from doclayout.processors.page_header import PageHeaderProcessor
from doclayout.processors.reference import ReferenceProcessor
from doclayout.processors.sectionheader import SectionHeaderProcessor
from doclayout.processors.text import TextProcessor
from doclayout.providers.registry import provider_from_filepath
from doclayout.renderers.markdown import MarkdownRenderer
from doclayout.schema import BlockTypes
from doclayout.schema.blocks import Block
from doclayout.schema.document import Document
from doclayout.schema.extraction import sanitize_html
from doclayout.schema.registry import register_block_class
from doclayout.services.openai import OpenAIService
from doclayout.util import strings_to_classes


class PdfConverter(BaseConverter):
    """
    A converter for processing and rendering PDF files into Markdown, JSON, HTML and other formats.
    """

    override_map: Annotated[
        Dict[BlockTypes, Type[Block]],
        "A mapping to override the default block classes for specific block types.",
        "The keys are `BlockTypes` enum values, representing the types of blocks,",
        "and the values are corresponding `Block` class implementations to use",
        "instead of the defaults.",
    ] = defaultdict()
    use_llm: Annotated[
        bool,
        "Enable higher quality processing with LLMs.",
    ] = False
    default_processors: Tuple[type[BaseProcessor], ...] = (
        BlockRelabelProcessor,
        LineMergeProcessor,
        BlockquoteProcessor,
        CodeProcessor,
        DocumentTOCProcessor,
        FootnoteProcessor,
        IgnoreTextProcessor,
        LineNumbersProcessor,
        ListProcessor,
        PageHeaderProcessor,
        MarginaliaProcessor,
        SectionHeaderProcessor,
        LLMTableProcessor,
        LLMTableMergeProcessor,
        LLMFormProcessor,
        TextProcessor,
        LLMComplexRegionProcessor,
        LLMImageDescriptionProcessor,
        LLMEquationProcessor,
        LLMHandwritingProcessor,
        LLMMathBlockProcessor,
        LLMSectionHeaderProcessor,
        LLMPageCorrectionProcessor,
        ReferenceProcessor,
        BlankPageProcessor,
        DebugProcessor,
    )

    def __init__(
        self,
        artifact_dict: Dict[str, Any],
        processor_list: Optional[List[str]] = None,
        renderer: str | None = None,
        llm_service: str | None = None,
        config=None,
    ):
        validate_config(config)
        if llm_service is not None:
            raise ValueError("llm_service was removed; all tasks use gpt-6-sol")
        super().__init__(config)

        if config is None:
            config = {}

        self.config = dict(config)

        for block_type, override_block_type in self.override_map.items():
            register_block_class(block_type, override_block_type)

        if processor_list is not None:
            processor_classes = cast(
                list[type[BaseProcessor]], strings_to_classes(processor_list)
            )
        else:
            processor_classes = list(self.default_processors)

        if renderer:
            renderer_class = strings_to_classes([renderer])[0]
        else:
            renderer_class = MarkdownRenderer

        # Put here so that resolve_dependencies can access it
        self.artifact_dict = dict(artifact_dict)
        self.extraction_service = self.artifact_dict.get("extraction_service")
        if self.extraction_service is None:
            raise ValueError(
                "Pass create_model_dict() artifacts with extraction_service"
            )
        if isinstance(self.extraction_service, OpenAIService):
            self.extraction_service = self.extraction_service.configured(self.config)
        self.llm_service = self.extraction_service if self.use_llm else None
        self.artifact_dict["llm_service"] = self.llm_service

        self.renderer = renderer_class
        self.processor_list = self.initialize_processors(processor_classes)

        self.page_count = None  # Track how many pages were converted

    @contextmanager
    def filepath_to_str(self, file_input: Union[str, io.BytesIO]):
        temp_file = None
        try:
            if isinstance(file_input, str):
                yield file_input
            else:
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".pdf"
                ) as temp_file:
                    if isinstance(file_input, io.BytesIO):
                        file_input.seek(0)
                        temp_file.write(file_input.getvalue())
                    else:
                        raise TypeError(
                            f"Expected str or BytesIO, got {type(file_input)}"
                        )

                yield temp_file.name
        finally:
            if temp_file is not None and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)

    def build_document(self, filepath: str) -> Document:
        if isinstance(self.extraction_service, OpenAIService):
            self.extraction_service.usage.clear()
        provider_cls = provider_from_filepath(filepath)
        provider = provider_cls(filepath, self.config)
        document = DocumentBuilder(self.config)(provider, self.extraction_service)
        self.prepare_document(document)

        for processor in self.processor_list:
            processor(document)

        for page in document.pages:
            for block in page.children:
                if getattr(block, "html", None):
                    block.html = sanitize_html(block.html)
                if getattr(block, "description", None):
                    block.description = sanitize_html(block.description)
        if isinstance(self.extraction_service, OpenAIService):
            document.usage = list(self.extraction_service.usage)
        return document

    def prepare_document(self, document):
        StructureBuilder(self.config)(document)

    def __call__(self, filepath: str | io.BytesIO):
        with self.filepath_to_str(filepath) as temp_path:
            document = self.build_document(temp_path)
            self.page_count = len(document.pages)
            renderer = self.resolve_dependencies(self.renderer)
            rendered = renderer(document)
        return rendered
