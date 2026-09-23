# Modified for DocLayout; see NOTICE for a summary of changes.
from typing import Optional, Tuple

from pydantic import BaseModel

from doclayout.schema import BlockTypes
from doclayout.schema.document import Document
from doclayout.util import assign_config


class BaseProcessor:
    block_types: Tuple[BlockTypes] | None = None  # What block types this processor is responsible for

    def __init__(self, config: Optional[BaseModel | dict] = None):
        assign_config(self, config)

    def __call__(self, document: Document, *args, **kwargs):
        raise NotImplementedError
