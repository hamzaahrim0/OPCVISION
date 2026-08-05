import requests
import pandas as pd
import time

BASE_API = "https://fundshare.asfim.ma/api/counter/"

def get_all_dates():
    all_rows = []
    page = 1
    while True:
        resp = requests.get(BASE_API, params={"page": page, "ordering": "-date"}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_rows.extend(data["results"])
        print(f"Page {page}/{data['page_count']} récupérée ({len(all_rows)} lignes au total)")
        if not data.get("next"):
            break
        page += 1
        time.sleep(0.2)  # politesse envers le serveur
    return pd.DataFrame(all_rows)

df_dates = get_all_dates()
df_dates.to_csv("asfim_dates_index.csv", index=False)
print(df_dates.shape)
df_dates.head()

import os

EXPORT_API = "https://fundshare.asfim.ma/api/performances/export/"
OUT_DIR = "asfim_xlsx"
os.makedirs(OUT_DIR, exist_ok=True)

def download_all(df_dates):
    for _, row in df_dates.iterrows():
        date_str = row["date"]
        periodicite = "hebdomadaire" if row["is_hebdo"] else "quotidienne"
        fname = os.path.join(OUT_DIR, f"{date_str}_{periodicite}.xlsx")

        if os.path.exists(fname):
            continue  # déjà téléchargé, on saute

        try:
            r = requests.get(EXPORT_API, params={"date": date_str}, timeout=30)
            r.raise_for_status()
            with open(fname, "wb") as f:
                f.write(r.content)
        except Exception as e:
            print(f"Erreur pour {date_str} : {e}")

        time.sleep(0.3)  # politesse envers le serveur

download_all(df_dates)
print("Terminé. Fichiers dans :", OUT_DIR)