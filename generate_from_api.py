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
    """Czyszczenie kodu HTML opisu ze śmieciowych atrybutów i tagów."""
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
    root = ET.Element("products")

    for prod_id, p in products_data.items():
        main_images = p.get("images", {})
        main_image_urls = list(main_images.values()) if isinstance(main_images, dict) else []

        text_fields = p.get("text_fields", {})
        title_pl = text_fields.get("name", "")
        desc_pl = clean_html_text(text_fields.get("description", ""))

        variants = p.get("variants", {})
        main_price = p.get("prices", {}).get("1", 0)
        main_stock = p.get("stock", {}).get("1", 0)
        main_ean = p.get("ean", "")

        if not variants:
            variants_list = [{
                "variant_id": prod_id,
                "sku": p.get("sku", str(prod_id)),
                "ean": main_ean,
                "price_brutto": main_price,
                "quantity": main_stock,
                "images": main_image_urls,
            }]
        else:
            variants_list = list(variants.values())

        # Budowanie tagu <product>
        product_elem = ET.SubElement(root, "product")

        cat_id = ET.SubElement(product_elem, "category-id")
        cat_id.text = str(p.get("category_id", "1"))

        cat_name = ET.SubElement(product_elem, "category-name")
        cat_name.text = "Body"

        title_elem = ET.SubElement(product_elem, "title")
        title_elem.text = title_pl

        desc_elem = ET.SubElement(product_elem, "long-description")
        desc_elem.text = desc_pl

        # --- OBOWIĄZKOWY BLOK WARIANTÓW (COLOURS -> MODIFICATIONS) ---
        colours_elem = ET.SubElement(product_elem, "colours")
        colour_elem = ET.SubElement(colours_elem, "colour")
        modifications_elem = ET.SubElement(colour_elem, "modifications")

        for v in variants_list:
            modification_elem = ET.SubElement(modifications_elem, "modification")

            # supplier-code (teraz w prawidłowym miejscu!)
            sup_code = ET.SubElement(modification_elem, "supplier-code")
            v_sku = v.get("sku") or v.get("ean") or str(v.get("variant_id"))
            sup_code.text = str(v_sku)

            # barcodes
            v_ean = v.get("ean") or main_ean
            if v_ean:
                barcodes_elem = ET.SubElement(modification_elem, "barcodes")
                barcode_item = ET.SubElement(barcodes_elem, "barcode")
                barcode_item.text = str(v_ean)

            # price & stock
            price_elem = ET.SubElement(modification_elem, "price")
            price_elem.text = str(v.get("price_brutto", main_price))

            stock_elem = ET.SubElement(modification_elem, "stock")
            stock_elem.text = str(v.get("quantity", main_stock))

            # images
            images_elem = ET.SubElement(modification_elem, "images")
            v_images = list(main_image_urls)
            if v.get("images"):
                v_imgs = v.get("images")
                if isinstance(v_imgs, dict):
                    v_images = list(v_imgs.values())
                elif isinstance(v_imgs, list):
                    v_images = v_imgs

            for img_url in v_images[:10]:
                if img_url:
                    if not img_url.startswith("http"):
                        img_url = "https://" + img_url
                    img_tag = ET.SubElement(images_elem, "image")
                    img_tag.text = img_url

    # --- CDATA i GENEROWANIE XML ---
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
    target_inv_id = inv_res["inventories"][0]["inventory_id"]
    print(f"Wybrano magazyn: (ID: {target_inv_id})")

    prod_list_res = call_baselinker_api(
        "getInventoryProductsList", {"inventory_id": target_inv_id}
    )
    product_ids = [int(pid) for pid in prod_list_res.get("products", {}).keys()]

    if not product_ids:
        print("Brak produktów w magazynie.")
        sys.exit(0)

    print("Pobieranie danych produktów...")
    products_data_res = call_baselinker_api(
        "getInventoryProductsData",
        {"inventory_id": target_inv_id, "products": product_ids[:500]},
    )
    full_products = products_data_res.get("products", {})

    print("Generowanie Pigu XML...")
    pigu_xml_output = build_pigu_xml(full_products)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(pigu_xml_output)
    print(f"Sukces! Plik gotowy.")


if __name__ == "__main__":
    main()
