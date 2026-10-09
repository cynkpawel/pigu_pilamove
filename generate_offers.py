import os
import sys
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup, CData
import requests

BASELINKER_TOKEN = os.environ.get("BASELINKER_TOKEN")
OUTPUT_FILE = "pigu_offers.xml"
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

def build_offers_xml(products_data, default_price_group, default_warehouse):
    root = ET.Element("products")

    for prod_id, p in products_data.items():
        variants = p.get("variants", {})
        main_ean = p.get("ean", "")
        
        if not variants:
            variants_list = [{
                "variant_id": prod_id,
                "sku": p.get("sku", str(prod_id)),
                "ean": main_ean,
                "prices": p.get("prices", {}),
                "stock": p.get("stock", {})
            }]
        else:
            variants_list = list(variants.values())

        for v in variants_list:
            v_ean = v.get("ean") or main_ean
            if not v_ean:
                continue # Pigu wymaga EAN do powiązania ofert

            product_elem = ET.SubElement(root, "product")
            
            # SKU (musi odpowiadać supplier-code)
            v_sku = v.get("sku") or v.get("ean") or str(v.get("variant_id"))
            ET.SubElement(product_elem, "sku").text = str(v_sku)
            
            # EAN
            ET.SubElement(product_elem, "ean").text = str(v_ean)
            
            # Ceny (pobieramy z domyślnej grupy cenowej BaseLinkera)
            v_prices = v.get("prices", {})
            price = v_prices.get(str(default_price_group)) or v_prices.get(list(v_prices.keys())[0] if v_prices else "0") or "0"
            
            # Pigu wymaga obu pól. Jeśli nie ma promocji, wstawiamy to samo.
            ET.SubElement(product_elem, "price-before-discount").text = str(price)
            ET.SubElement(product_elem, "price-after-discount").text = str(price)
            
            # Stany magazynowe
            v_stock = v.get("stock", {})
            stock = v_stock.get(default_warehouse) or sum(v_stock.values()) if v_stock else 0
            ET.SubElement(product_elem, "stock").text = str(stock)
            
            # Czas wysyłki w godzinach roboczych (domyślnie 24h)
            ET.SubElement(product_elem, "collectionhours").text = "24"

    xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")
    soup = BeautifulSoup(xml_str, "xml")

    # Dodanie CDATA
    for tag_name in ["sku", "ean"]:
        for tag in soup.find_all(tag_name):
            val = tag.get_text().strip()
            if val: tag.string = CData(val)

    import re
    xml_body = str(soup)
    xml_body = re.sub(r"<\?xml.*?\?>", "", xml_body, flags=re.DOTALL)
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + xml_body.lstrip()

def main():
    inv_res = call_baselinker_api("getInventories")
    target_inv = inv_res["inventories"][0]
    target_inv_id = target_inv["inventory_id"]
    default_price_group = target_inv.get("default_price_group", 0)
    default_warehouse = target_inv.get("default_warehouse", "")

    prod_list_res = call_baselinker_api("getInventoryProductsList", {"inventory_id": target_inv_id})
    product_ids = [int(pid) for pid in prod_list_res.get("products", {}).keys()]
    if not product_ids: return

    products_data_res = call_baselinker_api(
        "getInventoryProductsData",
        {"inventory_id": target_inv_id, "products": product_ids[:500]},
    )
    
    offers_xml_output = build_offers_xml(products_data_res.get("products", {}), default_price_group, default_warehouse)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(offers_xml_output)

if __name__ == "__main__":
    main()
