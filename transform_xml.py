import html
import os
import re
import sys
from bs4 import BeautifulSoup, CData
import requests

BASELINKER_XML_URL = "https://panel-f.baselinker.com/inventory_export.php?hash=aeddfc8c3f20ca1f0b644bd49df5d18c"
LOCAL_INPUT_FILE = "input_baselinker.xml"
OUTPUT_FILE = "pigu.xml"


def clean_html_content(raw_html):
    """Czyści HTML ze zbędnych atrybutów oraz przestarzałych tagów <font> i <section>."""
    if not raw_html:
        return ""

    clean_str = html.unescape(raw_html)
    clean_str = html.unescape(clean_str)

    soup = BeautifulSoup(clean_str, "html.parser")

    for tag in soup.find_all(["message-content", "section", "font"]):
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

    return cleaned_str.strip()


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
    soup = BeautifulSoup(xml_text, "xml")

    # 1. Czyszczenie opisów i pakowanie w CDATA
    for tag in soup.find_all(re.compile(r"^long-description")):
        raw_val = tag.get_text()
        cleaned_html = clean_html_content(raw_val)
        tag.string = CData(cleaned_html)

    # 2. CDATA dla pozostałych pól tekstowych i kodów
    cdata_target_tags = [
        "supplier-code",
        "barcode",
        "category-name",
        "brand",
        "title",
        "title-ru",
        "title-lv",
        "title-ee",
        "title-fi",
        "title-en",
        "title-pl",
    ]
    for tag_name in cdata_target_tags:
        for tag in soup.find_all(tag_name):
            raw_val = tag.get_text().strip()
            if raw_val:
                clean_val = html.unescape(raw_val)
                tag.string = CData(clean_val)

    # 3. Usuwanie pustych kontenerów <colours> i <properties>
    for colours in soup.find_all("colours"):
        if not colours.find_all("colour"):
            colours.decompose()

    for properties in soup.find_all("properties"):
        if not properties.find_all("property") and not properties.get_text(
            strip=True
        ):
            properties.decompose()

    print("Gwarantowanie pojedynczej deklaracji XML...")
    xml_body = str(soup)

    # Bezwarunkowe usunięcie KAŻDEJ deklaracji <?xml ...?> z całości tekstu
    xml_body = re.sub(r"<\?xml.*?\?>", "", xml_body, flags=re.DOTALL).strip()

    # Dodanie jednej, czystej deklaracji na samym początku
    final_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        + xml_body
    )

    print(f"Zapisywanie gotowego pliku do {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(final_xml)

    print("Sukces! Wygenerowano prawidłowy plik XML.")


if __name__ == "__main__":
    transform_xml()
