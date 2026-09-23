"""Validated page extraction and safe document HTML."""

from importlib.resources import files
from typing import Literal

import bleach
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, field_validator, model_validator


def sanitize_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "iframe", "object", "embed"]):
        tag.decompose()
    return bleach.clean(
        str(soup),
        tags={
            "p",
            "br",
            "div",
            "span",
            "b",
            "strong",
            "i",
            "em",
            "u",
            "del",
            "s",
            "sub",
            "sup",
            "a",
            "code",
            "pre",
            "blockquote",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "ul",
            "ol",
            "li",
            "table",
            "thead",
            "tbody",
            "tfoot",
            "tr",
            "td",
            "th",
            "caption",
            "math",
        },
        attributes={
            "a": ["href"],
            "td": ["colspan", "rowspan"],
            "th": ["colspan", "rowspan"],
            "math": ["display"],
            "ol": ["start"],
        },
        protocols={"http", "https", "mailto"},
        strip=True,
    )


class ExtractedBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_type: Literal[
        "Text",
        "SectionHeader",
        "PageHeader",
        "PageFooter",
        "Caption",
        "Footnote",
        "Code",
        "Bibliography",
        "Picture",
        "Figure",
        "Diagram",
        "Table",
        "Form",
        "Equation",
        "ListGroup",
        "TableOfContents",
        "ChemicalBlock",
    ]
    bbox: list[float]
    html: str

    @field_validator("bbox")
    @classmethod
    def valid_bbox(cls, value):
        if (
            len(value) != 4
            or any(not 0 <= n <= 1000 for n in value)
            or value[0] >= value[2]
            or value[1] >= value[3]
        ):
            raise ValueError("bbox must be a nonempty rectangle normalized to 0–1000")
        return value

    @model_validator(mode="after")
    def valid_content(self):
        self.html = sanitize_html(self.html)
        if self.block_type not in {"Picture", "Figure", "Diagram"}:
            if not BeautifulSoup(self.html, "html.parser").get_text(strip=True):
                raise ValueError("Text blocks must contain visible content")
        return self


class ExtractedPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blank: bool
    blocks: list[ExtractedBlock]

    @model_validator(mode="after")
    def valid_blank(self):
        if self.blank == bool(self.blocks):
            raise ValueError(
                "A blank page must have no blocks; a nonblank page needs blocks"
            )
        return self


PAGE_PROMPT = (
    files("doclayout").joinpath("prompts").joinpath("extraction.md").read_text(encoding="utf-8")
)
