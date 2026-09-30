import os
import sys
import requests
import json

# Konfiguracja
BASELINKER_TOKEN = os.environ.get("BASELINKER_TOKEN")
API_URL = "https://api.baselinker.com/connector.php"

def call_baselinker_api(method, parameters=None):
    if not BASELINKER_TOKEN:
        print("CRITICAL ERROR: Brak BASELINKER_TOKEN!")
        sys.exit(1)
    
    payload = {
        "token": BASELINKER_TOKEN,
        "method": method,
        "parameters": json.dumps(parameters or {})
    }
    response = requests.post(API_URL, data=payload)
    return response.json()

def main():
    print("Pobieranie listy magazynów...")
    inv_res = call_baselinker_api("getInventories")
    
    if "inventories" not in inv_res or not inv_res["inventories"]:
        print("Brak magazynów.")
        return
        
    target_inv = inv_res["inventories"][0]
    target_inv_id = target_inv["inventory_id"]
    print(f"Wybrano magazyn: {target_inv_id}")
    print(f"Dane magazynu (języki itp.): {json.dumps(target_inv, indent=2, ensure_ascii=False)}")

    print("\nPobieranie listy produktów...")
    prod_list_res = call_baselinker_api(
        "getInventoryProductsList", {"inventory_id": target_inv_id}
    )
    product_ids = list(prod_list_res.get("products", {}).keys())

    if not product_ids:
        print("Brak produktów.")
        return

    first_product_id = int(product_ids[0])
    print(f"\nPobieranie szczegółów dla produktu ID: {first_product_id}")
    
    products_data_res = call_baselinker_api(
        "getInventoryProductsData",
        {"inventory_id": target_inv_id, "products": [first_product_id]}
    )
    
    product_data = products_data_res.get("products", {}).get(str(first_product_id), {})
    
    print("\n===========================================")
    print("SUROWA STRUKTURA JSON PRODUKTU Z BASELINKERA:")
    print("===========================================")
    print(json.dumps(product_data, indent=2, ensure_ascii=False))
    print("===========================================\n")
    print("Koniec diagnostyki.")

if __name__ == "__main__":
    main()
