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

    # Oczyszczanie ryzykownych słów (np. fiński autocheck)
    cleaned_str = re.sub(r"helvetica", "sans-serif", cleaned_str, flags=re.IGNORECASE)

    return cleaned_str.strip()


def build_pigu_xml(products_data):
    root = ET.Element("products")

    lang_mapping = {
        'lt': 'lt', 'lit': 'lt',
        'lv': 'lv', 'lav': 'lv',
        'ee': 'ee', 'et': 'ee', 'est': 'ee',
        'fi': 'fi', 'fin': 'fi',
        'en': 'en', 'eng': 'en',
        'ru': 'ru', 'rus': 'ru'
    }

    for prod_id, p in products_data.items():
        text_fields = p.get("text_fields", {})
        title_pl = text_fields.get("name", "")
        desc_pl = clean_html_text(text_fields.get("description", ""))

        raw_translations = p.get("translations", {})
        parsed_translations = {}
        for bl_lang, t_data in raw_translations.items():
            lang_key = bl_lang.lower()
            if lang_key in lang_mapping:
                p_lang = lang_mapping[lang_key]
                t_name = t_data.get("name", "")
                t_desc = clean_html_text(t_data.get("description", ""))
                parsed_translations[p_lang] = {"name": t_name, "desc": t_desc}

        # Wyciągamy tłumaczenie LT jako wiodące (bazowe)
        lt_trans = parsed_translations.get('lt', {})
        base_title = lt_trans.get("name") or title_pl
        base_desc = lt_trans.get("desc") or desc_pl

        variants = p.get("variants", {})
        main_ean = p.get("ean", "")

        if not variants:
            variants_list = [{
                "variant_id": prod_id,
                "sku": p.get("sku", str(prod_id)),
                "ean": main_ean,
                "name": title_pl
            }]
        else:
            variants_list = list(variants.values())

        product_elem = ET.SubElement(root, "product")

        ET.SubElement(product_elem, "category-id").text = str(p.get("category_id", "1"))
        ET.SubElement(product_elem, "category-name").text = "Body"

        # --- GŁÓWNE TYTUŁY (Wymagana ścisła kolejność XSD) ---
        ET.SubElement(product_elem, "title").text = base_title
        for lang in ['ru', 'lv', 'ee', 'fi', 'en']:
            if lang in parsed_translations and parsed_translations[lang]["name"]:
                ET.SubElement(product_elem, f"title-{lang}").text = parsed_translations[lang]["name"]
        ET.SubElement(product_elem, "title-pl").text = title_pl

        # --- GŁÓWNE OPISY ---
        ET.SubElement(product_elem, "long-description").text = base_desc
        for lang in ['ru', 'lv', 'ee', 'fi', 'en']:
            if lang in parsed_translations and parsed_translations[lang]["desc"]:
                ET.SubElement(product_elem, f"long-description-{lang}").text = parsed_translations[lang]["desc"]
        ET.SubElement(product_elem, "long-description-pl").text = desc_pl

        colours_elem = ET.SubElement(product_elem, "colours")
        colour_elem = ET.SubElement(colours_elem, "colour")
        modifications_elem = ET.SubElement(colour_elem, "modifications")

        for v in variants_list:
            modification_elem = ET.SubElement(modifications_elem, "modification")

            # --- TYTUŁY WARIANTÓW (Brak obsługi -pl, używamy tylko dozwolonych) ---
            v_name = v.get("name") or title_pl
            mod_base_title = lt_trans.get("name") or v_name
            
            ET.SubElement(modification_elem, "modification-title").text = mod_base_title
            
            for lang in ['ru', 'lv', 'ee', 'fi']:
                if lang in parsed_translations and parsed_translations[lang]["name"]:
                    ET.SubElement(modification_elem, f"modification-title-{lang}").text = parsed_translations[lang]["name"]

            # Reszta logistyki
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
                ET.SubElement(modification_elem, "package-barcode").text = str(v_ean)

            attr_elem = ET.SubElement(modification_elem, "attributes")
            
            v_sku = v.get("sku") or v.get("ean") or str(v.get("variant_id"))
            ET.SubElement(attr_elem, "supplier-code").text = str(v_sku)
            ET.SubElement(attr_elem, "manufacturer-code").text = str(v_sku)

            if v_ean:
                barcodes_elem = ET.SubElement(attr_elem, "barcodes")
                ET.SubElement(barcodes_elem, "barcode").text = str(v_ean)

    xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")
    soup = BeautifulSoup(xml_str, "xml")

    # CDATA musi obejmować wszystkie możliwe tagi językowe
    cdata_tags = ["package-barcode", "category-name", "supplier-code", "manufacturer-code", "barcode"]
    for ext in ['', '-ru', '-lv', '-ee', '-fi', '-en', '-pl']:
        cdata_tags.extend([f"title{ext}", f"long-description{ext}"])
    for ext in ['', '-ru', '-lv', '-ee', '-fi']:
        cdata_tags.append(f"modification-title{ext}")

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
