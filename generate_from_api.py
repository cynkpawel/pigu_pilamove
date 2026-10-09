import html
import os
import sys
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup, CData
import requests

BASELINKER_TOKEN = os.environ.get("BASELINKER_TOKEN")
OUTPUT_FILE = "pigu.xml"
API_URL = "https://api.baselinker.com/connector.php"

def call_baselinker_api(method, parameters=None):
    if not BASELINKER_TOKEN:
        sys.exit(1)
    payload = {
        "token": BASELINKER_TOKEN,
        "method": method,
        "parameters": str(parameters or {}).replace("'", '"'),
    }
    response = requests.post(API_URL, data=payload)
    return response.json()

def fix_caps(text):
    if not text: return text
    if text.isupper(): return text.capitalize()
    return text

def clean_html_text(raw_html):
    if not raw_html: return ""
    clean_str = html.unescape(html.unescape(raw_html))
    soup = BeautifulSoup(clean_str, "html.parser")
    for tag in soup.find_all(["message-content", "section", "font"]): tag.unwrap()
    for tag in soup.find_all(True): tag.attrs = {}
    cleaned_str = str(soup)
    import re
    cleaned_str = re.sub(r"<br\s*/?>", "<br/>", cleaned_str, flags=re.IGNORECASE)
    cleaned_str = re.sub(r"<hr\s*/?>", "<hr/>", cleaned_str, flags=re.IGNORECASE)
    cleaned_str = re.sub(r"helvetica", "sans-serif", cleaned_str, flags=re.IGNORECASE)
    return cleaned_str.strip()

def to_meters(cm_val):
    try:
        return f"{float(cm_val) / 100.0:.2f}"
    except:
        return "0.10"

def assign_category(title):
    """
    Automatycznie przydziela ID i nazwę kategorii z wytycznych Pilamove 
    na podstawie słów kluczowych w polskim tytule produktu.
    """
    t = title.lower()
    
    # Odzież damska
    if any(x in t for x in ['body', 'kombinezon', 'spódniczka', 'sukienka', 'top', 'spodenki', 'kolarki', 'dzwony', 'legginsy', 'komplet']):
        return "1001", "Drabužiai moterims"
        
    # Akcesoria damskie
    elif any(x in t for x in ['torba', 'nerka']):
        return "1002", "Aksesuarai moterims"
        
    # Skrzynia do reformera
    elif 'skrzynia' in t:
        return "1003", "Laisvalaikis"
        
    # Sprzęt fitness / Urządzenia
    elif any(x in t for x in ['stepper', 'trenażer', 'motylek', 'dysk', 'mata', 'reformer', 'deska']):
        return "1004", "Treniruokliai"
        
    # Kategoria domyślna dla sportu
    else:
        return "1005", "Sporto prekės"

def build_pigu_xml(products_data):
    root = ET.Element("products")
    bl_to_pigu = {
        'lt': 'lt', 'lv': 'lv', 'et': 'ee', 'ee': 'ee',
        'fi': 'fi', 'en': 'en', 'ru': 'ru'
    }

    for prod_id, p in products_data.items():
        text_fields = p.get("text_fields", {})
        title_pl = fix_caps(text_fields.get("name", ""))
        desc_pl = clean_html_text(text_fields.get("description", ""))

        parsed_translations = {}
        for key, value in text_fields.items():
            if "|" in key:
                field_type, lang_code = key.split("|", 1)
                lang_code = lang_code.lower()
                if lang_code in bl_to_pigu:
                    pigu_lang = bl_to_pigu[lang_code]
                    if pigu_lang not in parsed_translations:
                        parsed_translations[pigu_lang] = {"name": "", "desc": ""}
                    if field_type == "name":
                        parsed_translations[pigu_lang]["name"] = fix_caps(value)
                    elif field_type == "description":
                        parsed_translations[pigu_lang]["desc"] = clean_html_text(value)

        lt_title = parsed_translations.get('lt', {}).get("name") or title_pl
        lt_desc = parsed_translations.get('lt', {}).get("desc") or desc_pl
        en_title = parsed_translations.get('en', {}).get("name") or title_pl
        en_desc = parsed_translations.get('en', {}).get("desc") or desc_pl

        variants = p.get("variants", {})
        main_ean = p.get("ean", "")
        if not variants:
            variants_list = [{"variant_id": prod_id, "sku": p.get("sku", str(prod_id)), "ean": main_ean, "name": title_pl}]
        else:
            variants_list = list(variants.values())

        product_elem = ET.SubElement(root, "product")

        # AUTOMATYCZNE PRZYPISANIE KATEGORII Z PDF
        cat_id_val, cat_name_val = assign_category(title_pl)
        ET.SubElement(product_elem, "category-id").text = cat_id_val
        ET.SubElement(product_elem, "category-name").text = cat_name_val

        ET.SubElement(product_elem, "title").text = lt_title
        for lang in ['ru', 'lv', 'ee', 'fi', 'en']:
            lang_title = parsed_translations.get(lang, {}).get("name") or (en_title if lang in ['lv', 'ee'] else "")
            if lang_title: ET.SubElement(product_elem, f"title-{lang}").text = lang_title
            
        ET.SubElement(product_elem, "long-description").text = lt_desc
        for lang in ['ru', 'lv', 'ee', 'fi', 'en']:
            lang_desc = parsed_translations.get(lang, {}).get("desc") or (en_desc if lang in ['lv', 'ee'] else "")
            if lang_desc: ET.SubElement(product_elem, f"long-description-{lang}").text = lang_desc

        colours_elem = ET.SubElement(product_elem, "colours")
        colour_elem = ET.SubElement(colours_elem, "colour")

        main_images = p.get("images", {})
        main_image_urls = list(main_images.values()) if isinstance(main_images, dict) else []
        if main_image_urls:
            images_elem = ET.SubElement(colour_elem, "images")
            for img_url in main_image_urls[:10]:
                if not img_url.startswith("http"): img_url = "https://" + img_url
                img_tag = ET.SubElement(images_elem, "image")
                url_tag = ET.SubElement(img_tag, "url")
                url_tag.text = img_url

        modifications_elem = ET.SubElement(colour_elem, "modifications")

        for v in variants_list:
            modification_elem = ET.SubElement(modifications_elem, "modification")

            mod_lt_title = parsed_translations.get('lt', {}).get("name") or fix_caps(v.get("name")) or title_pl
            ET.SubElement(modification_elem, "modification-title").text = mod_lt_title
            
            for lang in ['ru', 'lv', 'ee', 'fi']:
                lang_mod_title = parsed_translations.get(lang, {}).get("name") or (en_title if lang in ['lv', 'ee'] else "")
                if lang_mod_title: ET.SubElement(modification_elem, f"modification-title-{lang}").text = lang_mod_title

            weight_val = v.get("weight") or p.get("weight") or 0.1
            ET.SubElement(modification_elem, "weight").text = str(weight_val)
            ET.SubElement(modification_elem, "length").text = to_meters(v.get("length") or p.get("length") or 10)
            ET.SubElement(modification_elem, "height").text = to_meters(v.get("height") or p.get("height") or 10)
            ET.SubElement(modification_elem, "width").text = to_meters(v.get("width") or p.get("width") or 10)

            v_ean = v.get("ean") or main_ean
            if v_ean: ET.SubElement(modification_elem, "package-barcode").text = str(v_ean)

            attr_elem = ET.SubElement(modification_elem, "attributes")
            if v_ean:
                barcodes_elem = ET.SubElement(attr_elem, "barcodes")
                ET.SubElement(barcodes_elem, "barcode").text = str(v_ean)
                
            v_sku = v.get("sku") or v.get("ean") or str(v.get("variant_id"))
            ET.SubElement(attr_elem, "supplier-code").text = str(v_sku)
            ET.SubElement(attr_elem, "manufacturer-code").text = str(v_sku)

    xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")
    soup = BeautifulSoup(xml_str, "xml")

    cdata_tags = ["package-barcode", "category-name", "supplier-code", "manufacturer-code", "barcode", "url"]
    for ext in ['', '-ru', '-lv', '-ee', '-fi', '-en']:
        cdata_tags.extend([f"title{ext}", f"long-description{ext}"])
    for ext in ['', '-ru', '-lv', '-ee', '-fi']:
        cdata_tags.append(f"modification-title{ext}")

    for tag_name in cdata_tags:
        for tag in soup.find_all(tag_name):
            val = tag.get_text().strip()
            if val: tag.string = CData(val)

    import re
    xml_body = str(soup)
    xml_body = re.sub(r"<\?xml.*?\?>", "", xml_body, flags=re.DOTALL)
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + xml_body.lstrip()

def main():
    inv_res = call_baselinker_api("getInventories")
    target_inv_id = inv_res["inventories"][0]["inventory_id"]
    
    prod_list_res = call_baselinker_api("getInventoryProductsList", {"inventory_id": target_inv_id})
    product_ids = [int(pid) for pid in prod_list_res.get("products", {}).keys()]
    if not product_ids: return

    products_data_res = call_baselinker_api(
        "getInventoryProductsData",
        {"inventory_id": target_inv_id, "products": product_ids[:500]},
    )
    
    pigu_xml_output = build_pigu_xml(products_data_res.get("products", {}))
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(pigu_xml_output)

if __name__ == "__main__":
    main()
