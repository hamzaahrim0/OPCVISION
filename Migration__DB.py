"""
Construction de la base SQLite asfim.db à partir des fichiers .xlsx
déjà téléchargés dans le dossier asfim_xlsx/.

Usage :
    python build_asfim_db.py
"""

import os
import glob
import sqlite3
import pandas as pd

# ============================================================
#  CONFIGURATION
# ============================================================

XLSX_DIR = "asfim_xlsx"
DB_PATH = "asfim.db"
TABLE = "opcvm_performances"

COLUMN_MAP = {
    "CODE ISIN": "code_isin",
    "Code Maroclear": "code_maroclear",
    "OPCVM": "nom_opcvm",
    "Société de Gestion": "societe_gestion",
    "Nature juridique": "nature_juridique",
    "Classification": "classification",
    "Sensibilité": "sensibilite",
    "Indice Bentchmark": "indice_benchmark",  
    "Périodicité VL": "periodicite_vl",
    "Souscripteurs": "souscripteurs",
    "Affectation des résultats": "affectation_resultats",
    "Commission de souscription": "commission_souscription",
    "Commission de rachat": "commission_rachat",
    "Frais de gestion": "frais_gestion",
    "Dépositaire": "depositaire",
    "Réseau placeur": "reseau_placeur",
    "AN": "actif_net",
    "VL": "vl",
    "YTD": "perf_ytd",
    "1 jour": "perf_1j",
    "1 semaine": "perf_1sem",
    "1 mois": "perf_1m",
    "3 mois": "perf_3m",
    "6 mois": "perf_6m",
    "1 an": "perf_1an",
    "2 ans": "perf_2ans",
    "3 ans": "perf_3ans",
    "5 ans": "perf_5ans",
}

CATEGORICAL_COLS = [
    "nature_juridique", "classification", "periodicite_vl",
    "souscripteurs", "affectation_resultats",
]

DB_COLUMNS = [
    "date", "periodicite",
    "code_isin", "code_maroclear", "nom_opcvm", "societe_gestion",
    "nature_juridique", "classification", "sensibilite", "indice_benchmark",
    "periodicite_vl", "souscripteurs", "affectation_resultats",
    "commission_souscription", "commission_rachat", "frais_gestion",
    "depositaire", "reseau_placeur", "actif_net", "vl",
    "perf_ytd", "perf_1j", "perf_1sem", "perf_1m", "perf_3m",
    "perf_6m", "perf_1an", "perf_2ans", "perf_3ans", "perf_5ans",
]


# ============================================================
#  LECTURE / NORMALISATION D'UN FICHIER
# ============================================================

def find_header_row(filepath, max_scan=5):
    raw = pd.read_excel(filepath, header=None, nrows=max_scan)
    for i in range(len(raw)):
        if str(raw.iloc[i, 0]).strip().upper() == "CODE ISIN":
            return i
    raise ValueError(f"Ligne d'en-tête introuvable dans {filepath}")


def parse_filename(filepath):
    base = os.path.basename(filepath).replace(".xlsx", "")
    date_str, periodicite = base.split("_", 1)
    return date_str, periodicite


def read_asfim_xlsx(filepath):
    header_row = find_header_row(filepath)
    df = pd.read_excel(filepath, header=header_row)

    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns=COLUMN_MAP)
    df = df.dropna(subset=["code_isin"])

    for col in CATEGORICAL_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper()

    date_str, periodicite = parse_filename(filepath)
    df["date"] = date_str
    df["periodicite"] = periodicite

    # Ne garder que les colonnes qu'on connaît, dans un ordre stable
    missing = [c for c in DB_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes dans {filepath} : {missing}")

    return df[DB_COLUMNS]


# ============================================================
#  BOUCLE SUR TOUS LES FICHIERS
# ============================================================

def build_full_history(xlsx_dir=XLSX_DIR):
    all_dfs = []
    errors = []

    files = sorted(glob.glob(os.path.join(xlsx_dir, "*.xlsx")))
    print(f"{len(files)} fichiers trouvés dans {xlsx_dir}/")

    for f in files:
        try:
            all_dfs.append(read_asfim_xlsx(f))
        except Exception as e:
            errors.append((f, str(e)))

    print(f"{len(all_dfs)} fichiers lus avec succès, {len(errors)} erreur(s).")
    for f, e in errors[:20]:
        print("  ERREUR -", f, ":", e)

    if not all_dfs:
        raise RuntimeError("Aucun fichier n'a pu être lu, arrêt.")

    return pd.concat(all_dfs, ignore_index=True)


# ============================================================
#  BASE SQLITE : CRÉATION + INSERTION IDEMPOTENTE
# ============================================================

def init_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            date                    TEXT,
            periodicite             TEXT,
            code_isin               TEXT,
            code_maroclear          TEXT,
            nom_opcvm               TEXT,
            societe_gestion         TEXT,
            nature_juridique        TEXT,
            classification          TEXT,
            sensibilite             TEXT,
            indice_benchmark        TEXT,
            periodicite_vl          TEXT,
            souscripteurs           TEXT,
            affectation_resultats   TEXT,
            commission_souscription REAL,
            commission_rachat       REAL,
            frais_gestion           REAL,
            depositaire             TEXT,
            reseau_placeur          TEXT,
            actif_net               REAL,
            vl                      REAL,
            perf_ytd                REAL,
            perf_1j                 REAL,
            perf_1sem               REAL,
            perf_1m                 REAL,
            perf_3m                 REAL,
            perf_6m                 REAL,
            perf_1an                REAL,
            perf_2ans               REAL,
            perf_3ans               REAL,
            perf_5ans               REAL,
            UNIQUE(date, periodicite, code_isin)
        )
    """)
    conn.commit()
    conn.close()


def insert_dataframe(df, db_path=DB_PATH, table=TABLE):
    """
    Insertion idempotente : passe par une table de staging temporaire,
    puis INSERT OR IGNORE vers la table finale (respecte la contrainte
    UNIQUE sans faire planter tout le lot si des doublons existent).
    """
    conn = sqlite3.connect(db_path)

    df.to_sql("staging_tmp", conn, if_exists="replace", index=False)

    cols = ", ".join(df.columns)
    conn.execute(f"""
        INSERT OR IGNORE INTO {table} ({cols})
        SELECT {cols} FROM staging_tmp
    """)
    conn.execute("DROP TABLE staging_tmp")
    conn.commit()

    n_total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.close()
    return n_total


# ============================================================
#  MAIN
# ============================================================

if __name__ == "__main__":
    init_db()

    df_all = build_full_history()
    print(f"\nDataFrame global : {df_all.shape[0]} lignes, {df_all.shape[1]} colonnes")

    n_total = insert_dataframe(df_all)
    print(f"\nBase peuplée avec succès. Total de lignes dans {TABLE} : {n_total}")