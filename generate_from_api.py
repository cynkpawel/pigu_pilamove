import html
import os
import re
import sys
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup, CData
import requests

# Konfiguracja
BASELINKER_TOKEN = os.environ.get("BASELINKER_TOKEN")
INVENTORY_ID = (
    83361  # Domyślne ID magazynu w BaseLinkerze (zostanie pobrane auto)
)
OUTPUT_FILE = "pigu.xml"
API_URL = "https://api.baselinker.com/connector.php"


def call_baselinker_api(method, parameters=None):
    """Pomocnicza funkcja do zapytań do API BaseLinkera."""
    if not BASELINKER_TOKEN:
        print("CRITICAL ERROR: Brak BASELINKER_TOKEN w zmiennych środowiskowych!")
        sys.exit(1)

    payload = {
        "token": BASELINKER_TOKEN,
        "method": method,
        "parameters": str(parameters or {}).replace("'", '"'),
    }

    response = requests.post(API_URL, data=payload)
    if response.status_code != 200:
        print(f"Błąd połączenia z API BaseLinker: {response.status_code}")
        sys.exit(1)

    data = response.json()
    if data.get("status") == "ERROR":
        print(
            f"Błąd API BaseLinkera: {data.get('error_message')} (Kod: {data.get('error_code')})"
        )
        sys.exit(1)

    return data


def clean_html_text(raw_html):
    """Czyszczenie kodu HTML opisu ze śmieciowych atrybutów."""
    if not raw_html:
        return ""

    clean_str = html.unescape(raw_html)
    clean_str = html.unescape(clean_str)
    soup = BeautifulSoup(clean_str, "html.parser")

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

    return cleaned_str.strip()


def build_pigu_xml(products_data):
    """Buduje pełną strukturę XML wymaganą przez Pigu na podstawie danych JSON z API."""
    root = ET.Element("products")

    for prod_id, p in products_data.items():
        # Pobieramy główne zdjęcia produktu
        main_images = p.get("images", {})
        main_image_urls = (
            list(main_images.values()) if isinstance(main_images, dict) else []
        )

        # Pobieramy teksty / opisy
        text_fields = p.get("text_fields", {})
        title_pl = text_fields.get("name", "")
        desc_pl = clean_html_text(text_fields.get("description", ""))

        # Sprawdzamy, czy produkt ma warianty
        variants = p.get("variants", {})

        # Jeśli produkt nie ma wariantów, traktujemy go jako pojedynczy wariant
        if not variants:
            variants_list = [{
                "variant_id": prod_id,
                "sku": p.get("sku", str(prod_id)),
                "ean": p.get("ean", ""),
                "price_brutto": p.get("prices", {}).get("1", 0),
                "quantity": p.get("stock", {}).get("1", 0),
                "images": main_image_urls,
            }]
        else:
            variants_list = list(variants.values())

        # Budowanie struktury <product>
        product_elem = ET.SubElement(root, "product")

        # 1. <supplier-code>
        supplier_code = ET.SubElement(product_elem, "supplier-code")
        supplier_code.text = str(p.get("sku") or prod_id)

        # 2. Kategorie
        cat_id = ET.SubElement(product_elem, "category-id")
        cat_id.text = str(p.get("category_id", "1"))

        cat_name = ET.SubElement(product_elem, "category-name")
        cat_name.text = "Body"

        # 3. Tytuły i Opisy
        title_elem = ET.SubElement(product_elem, "title")
        title_elem.text = title_pl

        desc_elem = ET.SubElement(product_elem, "long-description")
        desc_elem.text = desc_pl

        # 4. Kody Kreskowe (EAN)
        barcodes_elem = ET.SubElement(product_elem, "barcodes")
        ean_val = p.get("ean") or (
            variants_list[0].get("ean") if variants_list else ""
        )
        if ean_val:
            barcode_item = ET.SubElement(barcodes_elem, "barcode")
            barcode_item.text = str(ean_val)

        # 5. Cena i Stan
        price_val = p.get("prices", {}).get("1", 0)
        price_elem = ET.SubElement(product_elem, "price")
        price_elem.text = str(price_val)

        stock_elem = ET.SubElement(product_elem, "stock")
        stock_elem.text = str(p.get("stock", {}).get("1", 0))

        # 6. Zdjęcia (Z DZIEDZICZENIEM Z PRODUKTU GŁÓWNEGO!)
        images_elem = ET.SubElement(product_elem, "images")
        prod_images = main_image_urls

        # Jeśli brak bezpośrednich zdjęć, szukamy w wariantach
        if not prod_images and variants_list:
            for v in variants_list:
                v_imgs = v.get("images", {})
                if isinstance(v_imgs, dict):
                    prod_images.extend(list(v_imgs.values()))

        # Dopisujemy zdjęcia do XML (HTTPS)
        for img_url in prod_images[:10]:  # Limit 10 zdjęć
            if img_url:
                if not img_url.startswith("http"):
                    img_url = "https://" + img_url
                img_tag = ET.SubElement(images_elem, "image")
                img_tag.text = img_url

    # Generowanie ciągu znaków XML
    xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")

    # Pakowanie w CDATA dla wymaganych pól
    soup = BeautifulSoup(xml_str, "xml")

    cdata_tags = ["supplier-code", "barcode", "category-name", "title"]
    for tag_name in cdata_tags:
        for tag in soup.find_all(tag_name):
            val = tag.get_text().strip()
            if val:
                tag.string = CData(val)

    for tag in soup.find_all("long-description"):
        val = tag.get_text().strip()
        if val:
            tag.string = CData(val)

    xml_final = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + str(soup)
    )
    return xml_final


def main():
    print("Pobieranie listy magazynów...")
    inv_res = call_baselinker_api("getInventories")
    inventories = inv_res.get("inventories", [])

    if not inventories:
        print("Nie znaleziono żądnego magazynu w BaseLinkerze!")
        sys.exit(1)

    target_inv_id = inventories[0]["inventory_id"]
    print(
        f"Wybrano magazyn: {inventories[0]['name']} (ID: {target_inv_id})..."
    )

    print("Pobieranie listy ID produktów z API...")
    prod_list_res = call_baselinker_api(
        "getInventoryProductsList", {"inventory_id": target_inv_id}
    )
    products_dict = prod_list_res.get("products", {})

    product_ids = [int(pid) for pid in products_dict.keys()]
    print(f"Znaleziono {len(product_ids)} produktów w API.")

    if not product_ids:
        print("Brak produktów w magazynie.")
        sys.exit(0)

    print("Pobieranie szczegółowych danych o produktach, wariantach i zdjęciach...")
    # API pozwala pobrać max 1000 ID w jednym zapytaniu
    products_data_res = call_baselinker_api(
        "getInventoryProductsData",
        {"inventory_id": target_inv_id, "products": product_ids[:500]},
    )

    full_products = products_data_res.get("products", {})

    print("Generowanie wyjściowego pliku Pigu XML...")
    pigu_xml_output = build_pigu_xml(full_products)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(pigu_xml_output)

    print(f"Sukces! Wygenerowano plik {OUTPUT_FILE} na podstawie API.")


if __name__ == "__main__":
    main()
