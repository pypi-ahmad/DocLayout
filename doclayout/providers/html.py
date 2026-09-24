# Modified for DocLayout; see NOTICE for a summary of changes.

from doclayout.providers.converted import ConvertedPdfProvider
from doclayout.security import embedded_resource


class HTMLProvider(ConvertedPdfProvider):
    conversion_method = "convert_html_to_pdf"

    def convert_html_to_pdf(self, filepath: str):
        from weasyprint import HTML

        font_css = self.get_font_css()
        HTML(
            filename=filepath, encoding="utf-8", url_fetcher=embedded_resource
        ).write_pdf(self.temp_pdf_path, stylesheets=[font_css])
