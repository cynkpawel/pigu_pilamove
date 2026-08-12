import html
import os
import re
import sys
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import requests

BASELINKER_XML_URL = "https://panel-f.baselinker.com/inventory_export.php?hash=aeddfc8c3f20ca1f0b644bd49df5d18c"
LOCAL_INPUT_FILE = "input_baselinker.xml"
OUTPUT_FILE = "pigu.xml"

# Ścisła, oficjalna sekwencja tagów Pigu XSD (supplier-code MUSI być na pierwszym miejscu)
PIGU_OFFICIAL_ORDER = [
    "supplier-code",
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


def clean_html_content(raw_html):
    """Czyści HTML z atrybutów (neue, style, class) i koduje znaki < oraz > na encje &lt; i &gt;"""
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

    print("Korekta kodów językowych (et -> ee)...")
    xml_text = (
        xml_text.replace("<title-et>", "<title-ee>")
        .replace("</title-et>", "</title-ee>")
        .replace("<long-description-et>", "<long-description-ee>")
        .replace("</long-description-et>", "</long-description-ee>")
        .replace("<usage-info-et>", "<usage-info-ee>")
        .replace("</usage-info-et>", "</usage-info-ee>")
    )

    print("Parsowanie drzewa XML...")
    try:
        root = ET.fromstring(xml_text)
    except Exception as e:
        print(f"Błąd parsowania XML: {e}")
        sys.exit(1)

    for product in root.findall("product"):
        # 1. Czyszczenie opisów HTML
        for child in list(product):
            if child.tag.startswith("long-description") and child.text:
                text_content = re.sub(
                    r"<!\[CDATA\[(.*?)\]\]>",
                    r"\1",
                    child.text,
                    flags=re.DOTALL,
                )
                child.text = clean_html_content(text_content)

        # 2. Usuwanie pustych kontenerów <colours> i <properties>
        colours = product.find("colours")
        if colours is not None and len(colours.findall("colour")) == 0:
            product.remove(colours)

        properties = product.find("properties")
        if properties is not None and len(properties.findall("property")) == 0:
            if not properties.text or not properties.text.strip():
                product.remove(properties)

        # 3. Usuwanie całkowicie pustych opcjonalnych pól (np. puste <title-pl/> lub <usage-info/>)
        for child in list(product):
            if len(child) == 0 and (not child.text or not child.text.strip()):
                if child.tag not in ["barcodes", "images"]:
                    product.remove(child)

        # 4. Ścisłe sortowanie tagów wg PIGU_OFFICIAL_ORDER
        children = list(product)
        for child in children:
            product.remove(child)

        valid_children = []
        for child in children:
            tag_name = child.tag.lower()
            if tag_name in PIGU_OFFICIAL_ORDER:
                valid_children.append(
                    (PIGU_OFFICIAL_ORDER.index(tag_name), child)
                )

        valid_children.sort(key=lambda x: x[0])
        for _, child in valid_children:
            product.append(child)

    print("Generowanie wyjściowego ciągu XML...")
    xml_out = ET.tostring(root, encoding="utf-8").decode("utf-8")

    # 5. Otaczanie tytułów, opisów i kategorii blokami CDATA
    def wrap_cdata(match):
        tag_name = match.group(1)
        content = match.group(2)
        content = re.sub(
            r"<!\[CDATA\[(.*?)\]\]>", r"\1", content, flags=re.DOTALL
        )
        return f"<{tag_name}><![CDATA[{content}]]></{tag_name}>"

    cdata_pattern = r"<(title[a-zA-Z-]*|long-description[a-zA-Z-]*|category-name)\b[^>]*>(.*?)</\1>"
    xml_out = re.sub(cdata_pattern, wrap_cdata, xml_out, flags=re.DOTALL)

    print(f"Zapisywanie gotowego pliku do {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml_out)

    print("Sukces! Plik wygenerowany pomyślnie.")


if __name__ == "__main__":
    transform_xml()
