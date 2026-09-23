"""
fetch_creams.py - Fill in the ingredient lists of your 20 creams automatically
from Open Beauty Facts. Run:  python fetch_creams.py
Creams that are not found stay empty; paste their lists in the app (tab "My 20 creams").
"""
import time
import pandas as pd
import tools

path = f"{tools.DATA_DIR}/creams.csv"
df = pd.read_csv(path, dtype=str).fillna("")
for i, row in df.iterrows():
    if row["ingredients"].strip():
        print(f"✓ already filled: {row['name']}")
        continue
    found = tools.search_product(row["name"])
    if found["found"]:
        df.at[i, "ingredients"] = found["ingredients"]
        print(f"✓ found: {row['name']}  ->  {found['product_name']} ({found['brand']})")
    else:
        print(f"✗ not found: {row['name']}  (paste it in the app)")
    time.sleep(2)  # be polite to the free database
df.to_csv(path, index=False)
print("\nDone. Always check that each list matches your real product.")
