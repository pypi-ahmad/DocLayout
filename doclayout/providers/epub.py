# Modified for DocLayout; see NOTICE for a summary of changes.

from bs4 import BeautifulSoup

from doclayout.providers.converted import ConvertedPdfProvider
from doclayout.security import embedded_resource, image_data_uri

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


class EpubProvider(ConvertedPdfProvider):
    conversion_method = "convert_epub_to_pdf"

    def convert_epub_to_pdf(self, filepath):
        import ebooklib
        from ebooklib import epub
        from weasyprint import CSS, HTML

        ebook = epub.read_epub(filepath)

        html_content = ""
        img_tags = {}

        for item in ebook.get_items():
            if item.get_type() == ebooklib.ITEM_IMAGE:
                img_tags[item.file_name] = image_data_uri(
                    item.get_content(), item.media_type
                )

        for item in ebook.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                html_content += item.get_content().decode("utf-8")

        soup = BeautifulSoup(html_content, "html.parser")
        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                normalized_src = src.replace("../", "")
                if normalized_src in img_tags:
                    img["src"] = img_tags[normalized_src]

        for image in soup.find_all("image"):
            src = image.get("xlink:href")
            if src:
                normalized_src = src.replace("../", "")
                if normalized_src in img_tags:
                    image["xlink:href"] = img_tags[normalized_src]

        html_content = str(soup)

        # we convert the epub to HTML
        HTML(string=html_content, url_fetcher=embedded_resource).write_pdf(
            self.temp_pdf_path,
            stylesheets=[
                CSS(string=css, url_fetcher=embedded_resource),
                self.get_font_css(),
            ],
        )
