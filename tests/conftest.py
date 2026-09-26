"""Offline fixtures. Live API calls require --run-integration."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image, ImageDraw

from doclayout.builders.document import DocumentBuilder
from doclayout.converters.pdf import PdfConverter
from doclayout.providers.pdf import PdfProvider


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration", action="store_true", help="Run billable GPT-6 Sol tests"
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-integration"):
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(
                    pytest.mark.skip(
                        reason="Requires explicit --run-integration (billable)"
                    )
                )


@pytest.fixture(autouse=True)
def prevent_unrequested_api(request, monkeypatch):
    if "integration" not in request.keywords:

        def blocked(*args, **kwargs):
            raise AssertionError("Unexpected real OpenAI request in offline tests")

        monkeypatch.setattr(
            "openai.resources.responses.responses.Responses.parse", blocked
        )
        monkeypatch.setattr(
            "openai.resources.responses.responses.Responses.create", blocked
        )
        from doclayout.schema.layout import LayoutAnalysis

        class OfflineLayout:
            status = "Not loaded"
            actual_device = None

            def prepare(self):
                self.actual_device = "cpu"
                self.status = "Ready: offline test fixture"

            def analyze(self, image):
                return LayoutAnalysis(
                    image_size=image.size,
                    provider="test",
                    model_id="test",
                    model_revision="fixture",
                    actual_device="cpu",
                    elapsed_ms=0,
                    candidate_count=0,
                    filtered_count=0,
                    regions=[],
                )

            def retry_failed(self):
                pass

        engine = OfflineLayout()
        monkeypatch.setattr("doclayout.layout.get_layout_engine", lambda: engine)
        monkeypatch.setattr("doclayout.ui.batch.get_layout_engine", lambda: engine)


@pytest.fixture
def config(request):
    mark = request.node.get_closest_marker("config")
    return dict(mark.args[0]) if mark else {}


@pytest.fixture
def page_result():
    def block(kind, html, bbox):
        return {"block_type": kind, "html": html, "bbox": bbox}

    return {
        "blank": False,
        "blocks": [
            block(
                "SectionHeader",
                "<h1>Subspace Adversarial Training</h1>",
                [50, 20, 900, 80],
            ),
            block(
                "Text", "<p>Hello, World! First column text.</p>", [50, 100, 450, 180]
            ),
            block(
                "Equation",
                '<math display="block">x^2 + y^2</math>',
                [50, 190, 450, 240],
            ),
            block(
                "Table",
                "<table><tr><th>Name</th><th>Value</th></tr><tr><td>A</td><td>42</td></tr></table>",
                [50, 260, 900, 420],
            ),
            block("Figure", "", [50, 450, 450, 550]),
            block(
                "ListGroup",
                "<ul><li>First</li><li>Second</li></ul>",
                [50, 650, 450, 750],
            ),
            block("PageFooter", "<p>Page one</p>", [100, 930, 800, 990]),
        ],
    }


@pytest.fixture
def extraction_service(page_result):
    def extract(prompt, image, block, schema, **kwargs):
        block.update_metadata(llm_request_count=1, llm_tokens_used=123)
        return page_result

    return Mock(side_effect=extract)


@pytest.fixture
def model_dict(extraction_service):
    return {"extraction_service": extraction_service}


@pytest.fixture
def temp_doc(tmp_path):
    path = tmp_path / "document.pdf"
    first = Image.new("RGB", (512, 512), "white")
    ImageDraw.Draw(first).text((20, 20), "Hello, World!", fill="black")
    first.save(path, save_all=True, append_images=[first])
    return SimpleNamespace(name=str(path))


@pytest.fixture
def temp_image(tmp_path):
    path = tmp_path / "image.png"
    Image.new("RGB", (512, 512), "white").save(path)
    return SimpleNamespace(name=str(path))


@pytest.fixture
def doc_provider(config, temp_doc):
    return PdfProvider(temp_doc.name, config)


@pytest.fixture
def pdf_document(config, doc_provider, extraction_service):
    return DocumentBuilder(config)(doc_provider, extraction_service)


@pytest.fixture
def pdf_converter(config, model_dict):
    return PdfConverter(model_dict, config=config)
