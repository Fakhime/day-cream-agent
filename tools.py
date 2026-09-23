"""
tools.py - The "hands" of the agent.

Functions here search the data sources:
  1. data/creams.csv        -> your 20 day creams
  2. Open Beauty Facts API  -> free online product database
  3. data/ingredients.csv   -> your curated table (group, features, skin types)
  4. data/cosing.csv/.xlsx  -> EU official ingredient functions (optional download)
"""
import io
import os
import re
from functools import lru_cache

import pandas as pd
import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SKIN_TYPES = ["Dry", "Oily", "Combination", "Normal", "Sensitive", "Acne-prone", "Mature"]
HEADERS = {"User-Agent": "DayCreamIngredientAgent/1.0 (learning project)"}
PROFILE_FIELDS = ["group", "function", "features", "best_for", "be_careful",
                  "concerns", "evidence", "notes"]


# ---------------------------------------------------------------- helpers
def normalize(name: str) -> str:
    """Lower-case an ingredient name and remove stars, dots and extra spaces."""
    n = str(name).lower().strip()
    n = re.sub(r"[\*\u2020\u00b0\u00ae\u2122]+", "", n)
    n = re.sub(r"\s+", " ", n)
    return n.strip(" .;:-")


def split_ingredients(text: str) -> list:
    """Split an ingredient list on commas (ignoring commas inside brackets)."""
    if not text:
        return []
    t = re.sub(r"^\s*(ingredients|ingr[eé]dients|inci)\s*:", "", str(text), flags=re.I)
    t = re.split(r"\bmay contain\b|\[\s*\+/-", t, flags=re.I)[0]  # drop "may contain" colours
    parts, depth, cur = [], 0, ""
    for ch in t:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch in ",;\n" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    seen, out = set(), []
    for p in parts:
        p = p.strip(" .\t\r")
        if p and normalize(p) not in seen:
            seen.add(normalize(p))
            out.append(p)
    return out


def _candidates(name: str) -> list:
    """Different spellings to try, e.g. 'Aqua (Water)' -> aqua (water), aqua, water."""
    full = normalize(name)
    cands = [full]
    outside = normalize(re.sub(r"\(.*?\)", "", full))
    inside = re.findall(r"\((.*?)\)", full)
    cands.append(outside)
    cands += [normalize(i) for i in inside]
    for c in list(cands):
        if "/" in c:
            cands += [normalize(x) for x in c.split("/")]
    return [c for i, c in enumerate(cands) if c and c not in cands[:i]]


# ---------------------------------------------------------------- data loaders
@lru_cache(maxsize=1)
def load_profiles() -> dict:
    """Load your curated table, indexed by INCI name and aliases."""
    df = pd.read_csv(os.path.join(DATA_DIR, "ingredients.csv"), dtype=str).fillna("")
    index = {}
    for rec in df.to_dict("records"):
        keys = [rec["inci_name"]] + [a for a in rec.get("aliases", "").split("|") if a.strip()]
        for k in keys:
            index.setdefault(normalize(k), rec)
    return index


def _find_header(df_raw: pd.DataFrame):
    for i in range(min(40, len(df_raw))):
        row = " ".join(str(x).lower() for x in df_raw.iloc[i].tolist())
        if "inci" in row and "function" in row:
            return i
    return None


@lru_cache(maxsize=1)
def load_cosing() -> dict:
    """Load the EU CosIng file if you downloaded it (data/cosing.csv or data/cosing.xlsx)."""
    csv_path = os.path.join(DATA_DIR, "cosing.csv")
    xlsx_path = os.path.join(DATA_DIR, "cosing.xlsx")
    try:
        if os.path.exists(csv_path):
            with open(csv_path, encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            start = next((i for i, l in enumerate(lines[:40])
                          if "inci" in l.lower() and "function" in l.lower()), 0)
            df = pd.read_csv(io.StringIO("".join(lines[start:])), sep=None, engine="python",
                             dtype=str, on_bad_lines="skip").fillna("")
        elif os.path.exists(xlsx_path):
            raw = pd.read_excel(xlsx_path, header=None, dtype=str).fillna("")
            h = _find_header(raw)
            if h is None:
                return {}
            df = raw.iloc[h + 1:].copy()
            df.columns = raw.iloc[h].tolist()
        else:
            return {}
    except Exception as e:  # a broken file should not stop the app
        print("Could not read CosIng file:", e)
        return {}

    cols = [str(c) for c in df.columns]
    df.columns = cols
    inci_col = next((c for c in cols if "inci" in c.lower()), None)
    func_col = next((c for c in cols if "function" in c.lower()), None)
    restr_col = next((c for c in cols if "restriction" in c.lower()), None)
    if not inci_col or not func_col:
        return {}
    out = {}
    for inci, func, restr in zip(df[inci_col], df[func_col],
                                 df[restr_col] if restr_col else [""] * len(df)):
        if inci:
            out.setdefault(normalize(inci), {"functions": str(func).title(),
                                             "restriction": str(restr)})
    return out


def cosing_available() -> bool:
    return len(load_cosing()) > 0


# ---------------------------------------------------------------- agent tools
def search_product(product_name: str) -> dict:
    """Find a day cream by name and return its ingredient list.
    Looks in the user's own list of creams first, then in the Open Beauty Facts database."""
    wanted = normalize(product_name)
    try:
        creams = pd.read_csv(os.path.join(DATA_DIR, "creams.csv"), dtype=str).fillna("")
        for rec in creams.to_dict("records"):
            if rec["ingredients"].strip() and (wanted in normalize(rec["name"])
                                               or normalize(rec["name"]) in wanted):
                return {"found": True, "product_name": rec["name"], "brand": rec["brand"],
                        "ingredients": rec["ingredients"], "source": "My creams list"}
    except FileNotFoundError:
        pass

    try:
        r = requests.get("https://world.openbeautyfacts.org/cgi/search.pl",
                         params={"search_terms": product_name, "search_simple": 1,
                                 "action": "process", "json": 1, "page_size": 20},
                         headers=HEADERS, timeout=20)
        r.raise_for_status()
        for p in r.json().get("products", []):
            text = p.get("ingredients_text_en") or p.get("ingredients_text") or ""
            if text.strip():
                return {"found": True, "product_name": p.get("product_name", product_name),
                        "brand": p.get("brands", ""), "ingredients": text,
                        "source": "Open Beauty Facts"}
        return {"found": False, "message": "No product with an ingredient list was found. "
                                           "Paste the ingredient list from the packaging or brand website."}
    except Exception as e:
        return {"found": False, "message": f"Open Beauty Facts could not be reached: {e}"}


def lookup_ingredient(ingredient_name: str) -> dict:
    """Look up one cosmetic ingredient: its group, function, features, the skin types it suits,
    who should be careful, skin concerns, evidence level and EU CosIng function."""
    profiles, cosing = load_profiles(), load_cosing()
    result = {"as_written": ingredient_name, "inci_name": ingredient_name, "source": ""}
    sources = []
    for c in _candidates(ingredient_name):
        if c in profiles:
            rec = profiles[c]
            result["inci_name"] = rec["inci_name"]
            result.update({f: rec.get(f, "") for f in PROFILE_FIELDS})
            sources.append("My ingredient table")
            break
    for c in _candidates(result["inci_name"]) + _candidates(ingredient_name):
        if c in cosing:
            result["eu_function"] = cosing[c]["functions"]
            result["eu_restriction"] = cosing[c]["restriction"]
            sources.append("EU CosIng")
            break
    result["found"] = bool(sources)
    result["source"] = " + ".join(sources) if sources else "Not in database"
    return result


def analyze_ingredient_list(ingredient_list: str) -> dict:
    """Analyse a full day cream ingredient list: groups every ingredient and
    scores which skin types the cream suits best."""
    rows = analyze_rows(ingredient_list)
    return {"ingredient_count": len(rows),
            "skin_type_scores": skin_type_scores(rows),
            "groups": group_summary(rows),
            "ingredients": [{k: r.get(k, "") for k in
                             ["position", "inci_name", "group", "features",
                              "best_for", "be_careful", "evidence", "source"]} for r in rows]}


# ---------------------------------------------------------------- analysis
def analyze_rows(ingredient_text: str) -> list:
    rows = []
    for pos, ing in enumerate(split_ingredients(ingredient_text), start=1):
        row = lookup_ingredient(ing)
        row["position"] = pos
        rows.append(row)
    return rows


def _types_in(text: str) -> set:
    t = str(text).lower()
    if "all" in [x.strip() for x in t.split(";")]:
        return set(SKIN_TYPES)
    return {s for s in SKIN_TYPES if s.lower() in t}


def skin_type_scores(rows: list) -> dict:
    """Score each skin type. Ingredients near the top of the list count more,
    because INCI lists go from the highest to the lowest amount."""
    scores = {s: 0.0 for s in SKIN_TYPES}
    for r in rows:
        if not r.get("group") or r.get("group") == "Unknown":
            continue
        pos = r.get("position", 99)
        weight = 3 if pos <= 5 else 2 if pos <= 10 else 1
        good = _types_in(r.get("best_for", ""))
        careful = _types_in(r.get("be_careful", "")) if r.get("be_careful") else set()
        functional = r.get("evidence", "") == "N/A"  # e.g. thickeners, preservatives
        for s in good - careful:
            scores[s] += weight * (0.3 if functional else 1)
        for s in careful:
            scores[s] -= max(weight, 1.5) * 1.5
    return {k: round(v, 1) for k, v in scores.items()}


def match_label(score: float, best: float) -> str:
    if score < 0:
        return "Be careful"
    if best > 0 and score >= 0.75 * best:
        return "Great match"
    if best > 0 and score >= 0.45 * best:
        return "Good match"
    return "Okay"


def group_summary(rows: list) -> dict:
    groups = {}
    for r in rows:
        g = r.get("group") or "Not in my table"
        groups.setdefault(g, []).append(r["inci_name"])
    return groups


def save_cream_ingredients(name: str, ingredients: str) -> None:
    path = os.path.join(DATA_DIR, "creams.csv")
    df = pd.read_csv(path, dtype=str).fillna("")
    df.loc[df["name"] == name, "ingredients"] = ingredients
    df.to_csv(path, index=False)
