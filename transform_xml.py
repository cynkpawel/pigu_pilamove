import html
import os
import re
import sys
from bs4 import BeautifulSoup
import requests

# Konfiguracja plików i adresów
BASELINKER_XML_URL = "https://panel-f.baselinker.com/inventory_export.php?hash=aeddfc8c3f20ca1f0b644bd49df5d18c"
LOCAL_INPUT_FILE = "input_baselinker.xml"  # Nazwa pliku do ewentualnego ręcznego wgrania
OUTPUT_FILE = "pigu.xml"


def clean_inner_html(raw_html):
    """Czyści HTML wewnątrz opisów: usuwa atrybuty 'neue', 'style', 'data-*' i naprawia tagi."""
    if not raw_html:
        return ""

    raw_html = html.unescape(raw_html)
    soup = BeautifulSoup(raw_html, "html.parser")

    # Usuwamy śmieciowe kontenery Angulara / ChatGPT
    for tag in soup.find_all(["message-content", "section"]):
        tag.unwrap()

    # Pętla usuwająca WSZYSTKIE atrybuty z tagów (znika 'neue', 'style', 'class' itp.)
    for tag in soup.find_all(True):
        tag.attrs = {}

    cleaned_str = str(soup)

    # Konwersja <br> na XHTML <br/>
    cleaned_str = re.sub(
        r"<br\s*/?>", "<br/>", cleaned_str, flags=re.IGNORECASE
    )
    cleaned_str = re.sub(
        r"<hr\s*/?>", "<hr/>", cleaned_str, flags=re.IGNORECASE
    )

    # Zabezpieczenie sekcji CDATA przed zamknięciem
    cleaned_str = cleaned_str.replace("]]>", "]]&gt;")

    return cleaned_str.strip()


def transform_xml():
    xml_text = ""

    # 1. Sprawdzamy, czy w repozytorium znajduje się plik wgrany ręcznie
    if os.path.exists(LOCAL_INPUT_FILE):
        print(
            f"Wykryto plik lokalny '{LOCAL_INPUT_FILE}'. Wczytywanie danych z pliku..."
        )
        with open(LOCAL_INPUT_FILE, "r", encoding="utf-8") as f:
            xml_text = f.read()
    else:
        # 2. Jeśli brakuje pliku lokalnego, pobieramy po URL
        print(
            "Brak pliku lokalnego. Pobieranie surowego pliku XML z BaseLinkera po URL..."
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(BASELINKER_XML_URL, headers=headers)

        if response.status_code != 200:
            print(f"Błąd pobierania pliku: Status {response.status_code}")
            sys.exit(1)

        xml_text = response.text

    print("Transformacja opisów i naprawianie struktury CDATA...")

    def replace_description_tag(match):
        tag_name = match.group(1)
        content = match.group(2)

        # Odzieramy z ewentualnych starych tagów CDATA
        content = re.sub(
            r"<!\[CDATA\[(.*?)\]\]>", r"\1", content, flags=re.DOTALL
        )

        # Czyszczenie HTML
        cleaned_content = clean_inner_html(content)

        return f"<{tag_name}><![CDATA[{cleaned_content}]]></{tag_name}>"

    # Szukamy wszystkich tagów typu <long-description>, <long-description-ru>, <long-description-ee> itp.
    pattern = r"<(long-description[a-zA-Z-]*)\b[^>]*>(.*?)</\1>"
    transformed_xml = re.sub(
        pattern, replace_description_tag, xml_text, flags=re.DOTALL
    )

    # Poprawka kodu dla Estonii jeśli w BaseLinkerze wystąpiło 'ee' zamiast 'et'
    transformed_xml = transformed_xml.replace(
        "<title-ee>", "<title-et>"
    ).replace("</title-ee>", "</title-et>")
    transformed_xml = transformed_xml.replace(
        "<long-description-ee>", "<long-description-et>"
    ).replace("</long-description-ee>", "</long-description-et>")

    print(f"Zapisywanie gotowego pliku do {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(transformed_xml)

    print("Sukces! Plik wygenerowany pomyślnie.")


if __name__ == "__main__":
    transform_xml()
