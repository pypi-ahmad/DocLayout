# Modified for DocLayout; see NOTICE for a summary of changes.
from enum import Enum, auto


class BlockTypes(str, Enum):
    Line = auto()
    Span = auto()
    Char = auto()
    FigureGroup = auto()
    TableGroup = auto()
    ListGroup = auto()
    PictureGroup = auto()
    Page = auto()
    Caption = auto()
    Code = auto()
    Figure = auto()
    Footnote = auto()
    Form = auto()
    Equation = auto()
    Handwriting = auto()
    TextInlineMath = auto()
    ListItem = auto()
    PageFooter = auto()
    PageHeader = auto()
    Picture = auto()
    SectionHeader = auto()
    Table = auto()
    Text = auto()
    TableOfContents = auto()
    Document = auto()
    ComplexRegion = auto()
    TableCell = auto()
    Reference = auto()
    Bibliography = auto()
    ChemicalBlock = auto()
    Diagram = auto()

    def __str__(self):
        return self.name
