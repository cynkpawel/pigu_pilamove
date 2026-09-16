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
        main_ean = p.get("ean", "")

        if not variants:
            variants_list = [{
                "variant_id": prod_id,
                "ean": main_ean,
                "name": title_pl
            }]
        else:
            variants_list = list(variants.values())

        product_elem = ET.SubElement(root, "product")

        cat_id = ET.SubElement(product_elem, "category-id")
        cat_id.text = str(p.get("category_id", "1"))

        cat_name = ET.SubElement(product_elem, "category-name")
        cat_name.text = "Body"

        title_elem = ET.SubElement(product_elem, "title")
        title_elem.text = title_pl

        desc_elem = ET.SubElement(product_elem, "long-description")
        desc_elem.text = desc_pl

        # --- GŁÓWNE ZDJĘCIA PRODUKTU (W TAGU MEDIA) ---
        media_elem = ET.SubElement(product_elem, "media")
        
        prod_images = list(main_image_urls)
        if not prod_images and variants:
            for v in variants_list:
                v_imgs = v.get("images", {})
                if isinstance(v_imgs, dict):
                    prod_images.extend(list(v_imgs.values()))
                elif isinstance(v_imgs, list):
                    prod_images.extend(v_imgs)

        for img_url in prod_images[:10]:
            if img_url:
                if not img_url.startswith("http"):
                    img_url = "https://" + img_url
                img_tag = ET.SubElement(media_elem, "image")
                img_tag.text = img_url

        # --- ZAGNIEŻDŻONE WARIANTY ---
        colours_elem = ET.SubElement(product_elem, "colours")
        colour_elem = ET.SubElement(colours_elem, "colour")
        modifications_elem = ET.SubElement(colour_elem, "modifications")

        for v in variants_list:
            modification_elem = ET.SubElement(modifications_elem, "modification")

            mod_title = ET.SubElement(modification_elem, "modification-title")
            v_name = v.get("name") or title_pl
            mod_title.text = v_name

            weight_val = v.get("weight") or p.get("weight") or 0.1
            length_val = v.get("length") or p.get("length") or 10
            height_val = v.get("height") or p.get("height") or 10
            width_val = v.get("width") or p.get("width") or 10

            ET.SubElement(modification_elem, "weight").text = str(weight_val)
            ET.SubElement(modification_elem, "length").text = str(length_val)
            ET.SubElement(modification_elem, "height").text = str(height_val)
            ET.SubElement(modification_elem, "width").text = str(width_val)

            v_ean = v.get("ean") or main_ean
            if v_ean:
                pkg_barcode = ET.SubElement(modification_elem, "package-barcode")
                pkg_barcode.text = str(v_ean)

            # --- ZDJĘCIA WARIANTU (W TAGU MEDIA) ---
            mod_media_elem = ET.SubElement(modification_elem, "media")
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
                    img_tag = ET.SubElement(mod_media_elem, "image")
                    img_tag.text = img_url

    xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")
    soup = BeautifulSoup(xml_str, "xml")

    # CDATA
    cdata_tags = ["package-barcode", "category-name", "title", "long-description", "modification-title"]
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
