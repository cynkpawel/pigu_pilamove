import html
import os
import re
import sys
from bs4 import BeautifulSoup
import requests

BASELINKER_XML_URL = "https://panel-f.baselinker.com/inventory_export.php?hash=aeddfc8c3f20ca1f0b644bd49df5d18c"
LOCAL_INPUT_FILE = "input_baselinker.xml"
OUTPUT_FILE = "pigu.xml"


def clean_inner_html(raw_html):
    """Czyści HTML z atrybutów i koduje znaki < oraz > na encje &lt; i &gt;

    wymagane przez walidator XSD Pigu.
    """
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

    encoded_str = html.escape(cleaned_str, quote=False)

    return encoded_str.strip()


def remove_empty_containers(xml_str):
    """Usuwa puste sekcje <colours> oraz <properties>, które wywołują błędy walidacji XSD Pigu."""

    # 1. Usuwanie sekcji <colours>, jeśli nie zawierają przynajmniej jednego tagu <colour>
    def colours_filter(match):
        content = match.group(1)
        if "<colour" not in content:
            return ""
        return match.group(0)

    xml_str = re.sub(
        r"<colours>(.*?)</colours>", colours_filter, xml_str, flags=re.DOTALL
    )

    # 2. Usuwanie całkowicie pustych tagów <properties>
    xml_str = re.sub(
        r"<properties>\s*</properties>", "", xml_str, flags=re.IGNORECASE
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

    print("Transformacja opisów pod walidację XSD Pigu...")

    def replace_description_tag(match):
        tag_name = match.group(1)
        content = match.group(2)

        content = re.sub(
            r"<!\[CDATA\[(.*?)\]\]>", r"\1", content, flags=re.DOTALL
        )
        cleaned_content = clean_inner_html(content)

        return f"<{tag_name}><![CDATA[{cleaned_content}]]></{tag_name}>"

    pattern = r"<(long-description[a-zA-Z-]*)\b[^>]*>(.*?)</\1>"
    transformed_xml = re.sub(
        pattern, replace_description_tag, xml_text, flags=re.DOTALL
    )

    # Zapewnienie poprawnych nazewnictw dla Estonii (-ee)
    transformed_xml = transformed_xml.replace(
        "<title-et>", "<title-ee>"
    ).replace("</title-et>", "</title-ee>")
    transformed_xml = transformed_xml.replace(
        "<long-description-et>", "<long-description-ee>"
    ).replace("</long-description-et>", "</long-description-ee>")

    # Czyszczenie pustych kontenerów <colours> i <properties>
    print("Czyszczenie pustych sekcji <colours> i <properties>...")
    transformed_xml = remove_empty_containers(transformed_xml)

    print(f"Zapisywanie gotowego pliku do {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(transformed_xml)

    print("Sukces! Plik wygenerowany pomyślnie.")


if __name__ == "__main__":
    transform_xml()
