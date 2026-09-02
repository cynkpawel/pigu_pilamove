import html
import os
import sys
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup, CData
import requests

# Konfiguracja
BASELINKER_TOKEN = os.environ.get("BASELINKER_TOKEN")
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
        print(f"Błąd API BaseLinkera: {data.get('error_message')}")
        sys.exit(1)

    return data


def clean_html_text(raw_html):
    """Czyszczenie kodu HTML opisu ze śmieciowych atrybutów i zbędnych tagów."""
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
    import re
    cleaned_str = re.sub(r"<br\s*/?>", "<br/>", cleaned_str, flags=re.IGNORECASE)
    cleaned_str = re.sub(r"<hr\s*/?>", "<hr/>", cleaned_str, flags=re.IGNORECASE)

    return cleaned_str.strip()


def build_pigu_xml(products_data):
    """Buduje strukturę XML wymaganą przez Pigu."""
    root = ET.Element("products")

    for prod_id, p in products_data.items():
        # Pobieranie zdjęć
        main_images = p.get("images", {})
        main_image_urls = (
            list(main_images.values()) if isinstance(main_images, dict) else []
        )

        # Pobieranie opisów
        text_fields = p.get("text_fields", {})
        title_pl = text_fields.get("name", "")
        desc_pl = clean_html_text(text_fields.get("description", ""))

        # Sprawdzanie wariantów dla poprawnego EAN-u
        variants = p.get("variants", {})
        if not variants:
            variants_list = [{
                "variant_id": prod_id,
                "ean": p.get("ean", ""),
                "images": main_image_urls,
            }]
        else:
            variants_list = list(variants.values())

        ean_val = p.get("ean") or (variants_list[0].get("ean") if variants_list else "")

        # --- BUDOWANIE ELEMENTU PRODUCT ---
        product_elem = ET.SubElement(root, "product")

        # 1. supplier-code (BEZWZGLĘDNIE NA PIERWSZYM MIEJSCU)
        # Zastępujemy błędne nazwy z SKU konkretnym kodem EAN lub numerycznym ID
        supplier_code = ET.SubElement(product_elem, "supplier-code")
        supplier_code.text = str(ean_val) if ean_val else str(prod_id)

        # 2. category-id
        cat_id = ET.SubElement(product_elem, "category-id")
        cat_id.text = str(p.get("category_id", "1"))

        # 3. category-name
        cat_name = ET.SubElement(product_elem, "category-name")
        cat_name.text = "Body"

        # 4. title
        title_elem = ET.SubElement(product_elem, "title")
        title_elem.text = title_pl

        # 5. long-description
        desc_elem = ET.SubElement(product_elem, "long-description")
        desc_elem.text = desc_pl

        # 6. barcodes
        barcodes_elem = ET.SubElement(product_elem, "barcodes")
        if ean_val:
            barcode_item = ET.SubElement(barcodes_elem, "barcode")
            barcode_item.text = str(ean_val)

        # 7. price & stock
        price_elem = ET.SubElement(product_elem, "price")
        price_elem.text = str(p.get("prices", {}).get("1", 0))

        stock_elem = ET.SubElement(product_elem, "stock")
        stock_elem.text = str(p.get("stock", {}).get("1", 0))

        # 8. images
        images_elem = ET.SubElement(product_elem, "images")
        prod_images = list(main_image_urls)

        if not prod_images and variants_list:
            for v in variants_list:
                v_imgs = v.get("images", {})
                if isinstance(v_imgs, dict):
                    prod_images.extend(list(v_imgs.values()))

        for img_url in prod_images[:10]:
            if img_url:
                if not img_url.startswith("http"):
                    img_url = "https://" + img_url
                img_tag = ET.SubElement(images_elem, "image")
                img_tag.text = img_url

    # --- PAKOWANIE W CDATA I GENEROWANIE CZYSTEGO KODU ---
    xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")
    soup = BeautifulSoup(xml_str, "xml")

    cdata_tags = ["supplier-code", "barcode", "category-name", "title", "long-description"]
    for tag_name in cdata_tags:
        for tag in soup.find_all(tag_name):
            val = tag.get_text().strip()
            if val:
                tag.string = CData(val)

    import re
    xml_body = str(soup)
    xml_body = re.sub(r"<\?xml.*?\?>", "", xml_body, flags=re.DOTALL)
    xml_body = xml_body.lstrip()

    xml_final = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + xml_body
    return xml_final


def main():
    print("Pobieranie listy magazynów...")
    inv_res = call_baselinker_api("getInventories")
    inventories = inv_res.get("inventories", [])

    if not inventories:
        print("Nie znaleziono żądnego magazynu w BaseLinkerze!")
        sys.exit(1)

    target_inv_id = inventories[0]["inventory_id"]
    print(f"Wybrano magazyn: {inventories[0]['name']} (ID: {target_inv_id})")

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

    print("Pobieranie szczegółowych danych o produktach...")
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
