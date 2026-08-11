import html
import os
import re
import sys
from bs4 import BeautifulSoup
import requests

BASELINKER_XML_URL = "https://panel-f.baselinker.com/inventory_export.php?hash=aeddfc8c3f20ca1f0b644bd49df5d18c"
LOCAL_INPUT_FILE = "input_baselinker.xml"
OUTPUT_FILE = "pigu.xml"

# Ścisła kolejność tagów wymagana przez specyfikację Pigu XSD
PIGU_TAG_ORDER = [
    "category-id",
    "category-name",
    "title",
    "title-ru",
    "title-lv",
    "title-ee",
    "title-fi",
    "title-en",
    "title-pl",
    "long-description",
    "long-description-ru",
    "long-description-lv",
    "long-description-ee",
    "long-description-fi",
    "long-description-en",
    "long-description-pl",
    "usage-info",
    "usage-info-lv",
    "usage-info-ee",
    "usage-info-ru",
    "usage-info-fi",
    "usage-info-en",
    "supplier-code",
    "barcodes",
    "price",
    "old-price",
    "vat",
    "stock",
    "delivery-days",
    "guarantee",
    "brand",
    "images",
    "colours",
    "properties",
]


def clean_inner_html(raw_html):
    """Czyści HTML z atrybutów i koduje znaki < oraz > na encje &lt; i &gt;"""
    if not raw_html:
        return ""

    raw_html = html.unescape(raw_html)
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in soup.find_all(["message-content", "section"]):
        tag.unwrap()

    for tag in soup.find_all(True):
        tag.attrs = {}

    cleaned_str = str(soup)
    cleaned_str = re.sub(
        r"<br\s*/?>", "<br/>", cleaned_str, flags=re.IGNORECASE
    )
    cleaned_str = re.sub(
        r"<hr\s*/?>", "<hr/>", cleaned_str, flags=re.IGNORECASE
    )

    return html.escape(cleaned_str, quote=False).strip()


def reorder_product_tags(product_xml_str):
    """Układa tagi wewnątrz <product> w ścisłej kolejności wymaganej przez schemat Pigu XSD."""
    try:
        soup = BeautifulSoup(product_xml_str, "xml")
    except Exception:
        soup = BeautifulSoup(product_xml_str, "html.parser")

    product_tag = soup.find("product")
    if not product_tag:
        return product_xml_str

    children = [child for child in product_tag.children if child.name]

    def get_sort_key(child):
        tag_name = child.name.lower()
        if tag_name in PIGU_TAG_ORDER:
            return PIGU_TAG_ORDER.index(tag_name)
        return 999

    sorted_children = sorted(children, key=get_sort_key)

    product_tag.clear()
    for child in sorted_children:
        product_tag.append(child)

    return str(product_tag)


def remove_empty_containers(xml_str):
    """Usuwa puste sekcje <colours> oraz <properties>."""
    xml_str = re.sub(r"<colours\b[^/>]*/>", "", xml_str, flags=re.IGNORECASE)

    def colours_filter(match):
        content = match.group(1)
        if "<colour" not in content:
            return ""
        return match.group(0)

    xml_str = re.sub(
        r"<colours\b[^>]*>(.*?)</colours>",
        colours_filter,
        xml_str,
        flags=re.IGNORECASE | re.DOTALL,
    )

    xml_str = re.sub(r"<properties\b[^/>]*/>", "", xml_str, flags=re.IGNORECASE)
    xml_str = re.sub(
        r"<properties\b[^>]*>\s*</properties>",
        "",
        xml_str,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return xml_str


def transform_xml():
    xml_text = ""

    if os.path.exists(LOCAL_INPUT_FILE):
        print(f"Wczytywanie z pliku lokalnego '{LOCAL_INPUT_FILE}'...")
        with open(LOCAL_INPUT_FILE, "r", encoding="utf-8") as f:
            xml_text = f.read()
    else:
        print("Pobieranie surowego pliku XML z BaseLinkera po URL...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(BASELINKER_XML_URL, headers=headers)
        if response.status_code != 200:
            print(f"Błąd pobierania pliku: Status {response.status_code}")
            sys.exit(1)
        xml_text = response.text

    print("Poprawianie nazewnictwa tagów (et -> ee)...")
    xml_text = (
        xml_text.replace("<title-et>", "<title-ee>")
        .replace("</title-et>", "</title-ee>")
        .replace("<long-description-et>", "<long-description-ee>")
        .replace("</long-description-et>", "</long-description-ee>")
        .replace("<usage-info-et>", "<usage-info-ee>")
        .replace("</usage-info-et>", "</usage-info-ee>")
    )

    print("Transformacja opisów pod CDATA...")

    def replace_description_tag(match):
        tag_name = match.group(1)
        content = match.group(2)
        content = re.sub(
            r"<!\[CDATA\[(.*?)\]\]>", r"\1", content, flags=re.DOTALL
        )
        cleaned_content = clean_inner_html(content)
        return f"<{tag_name}><![CDATA[{cleaned_content}]]></{tag_name}>"

    pattern = r"<(long-description[a-zA-Z-]*)\b[^>]*>(.*?)</\1>"
    xml_text = re.sub(
        pattern, replace_description_tag, xml_text, flags=re.DOTALL
    )

    print("Sortowanie tagów wewnątrz <product> wg specyfikacji Pigu XSD...")

    def process_product(match):
        return reorder_product_tags(match.group(0))

    xml_text = re.sub(
        r"<product\b[^>]*>(.*?)</product>",
        process_product,
        xml_text,
        flags=re.DOTALL,
    )

    print("Czyszczenie pustych sekcji <colours> i <properties>...")
    xml_text = remove_empty_containers(xml_text)

    print(f"Zapisywanie gotowego pliku do {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml_text)

    print("Sukces! Plik wygenerowany pomyślnie.")


if __name__ == "__main__":
    transform_xml()
