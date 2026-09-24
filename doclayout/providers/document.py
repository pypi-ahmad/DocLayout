# Modified for DocLayout; see NOTICE for a summary of changes.
import base64
import re
from io import BytesIO

from PIL import Image

from doclayout.logger import get_logger
from doclayout.providers.converted import ConvertedPdfProvider
from doclayout.security import DocumentLimitError, embedded_resource, check_pixels

logger = get_logger()

css = """
@page {
    size: A4;
    margin: 2cm;
}

img {
    max-width: 100%;
    max-height: 25cm;
    object-fit: contain;
    margin: 12pt auto;
}

div, p {
    max-width: 100%;
    word-break: break-word;
    font-size: 10pt;
}

table {
    width: 100%;
    border-collapse: collapse;
    break-inside: auto;
    font-size: 10pt;
}

tr {
    break-inside: avoid;
    page-break-inside: avoid;
}

td {
    border: 0.75pt solid #000;
    padding: 6pt;
}
"""


class DocumentProvider(ConvertedPdfProvider):
    conversion_method = "convert_docx_to_pdf"

    def convert_docx_to_pdf(self, filepath: str):
        import mammoth
        from weasyprint import CSS, HTML

        with open(filepath, "rb") as docx_file:
            # we convert the docx to HTML
            result = mammoth.convert_to_html(docx_file)
            html = result.value

            # We convert the HTML into a PDF
            HTML(
                string=self._preprocess_base64_images(html),
                url_fetcher=embedded_resource,
            ).write_pdf(
                self.temp_pdf_path,
                stylesheets=[
                    CSS(string=css, url_fetcher=embedded_resource),
                    self.get_font_css(),
                ],
            )

    @staticmethod
    def _preprocess_base64_images(html_content):
        pattern = r'data:([^;]+);base64,([^"\'>\s]+)'

        def convert_image(match):
            try:
                img_data = embedded_resource(match.group(0))["string"]

                with BytesIO(img_data) as bio:
                    with Image.open(bio) as img:
                        check_pixels(*img.size, source=True)
                        output = BytesIO()
                        img.save(output, format=img.format)
                        new_base64 = base64.b64encode(output.getvalue()).decode()
                        return f"data:{match.group(1)};base64,{new_base64}"

            except DocumentLimitError:
                raise
            except (OSError, ValueError) as e:
                logger.error(f"Failed to process image: {e}")
                return ""  # we ditch broken images as that breaks the PDF creation down the line

        return re.sub(pattern, convert_image, html_content)
