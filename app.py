"""
app.py - The web interface. Run it with:  streamlit run app.py
"""
import os

import pandas as pd
import streamlit as st

import agent
import tools

st.set_page_config(page_title="Day Cream Ingredient Agent", page_icon="🧴", layout="wide")

EXAMPLE = ("Aqua, Glycerin, Caprylic/Capric Triglyceride, Niacinamide, Cetearyl Alcohol, "
           "Butyrospermum Parkii Butter, Dimethicone, Glyceryl Stearate, PEG-100 Stearate, "
           "Sodium Hyaluronate, Panthenol, Tocopherol, Ceramide NP, Allantoin, Xanthan Gum, "
           "Carbomer, Sodium Hydroxide, Disodium EDTA, Phenoxyethanol, Ethylhexylglycerin, "
           "Parfum, Limonene, Linalool")
SHOW_COLS = ["position", "inci_name", "group", "function", "features", "best_for",
             "be_careful", "concerns", "evidence", "notes", "eu_function", "source"]


def default_key() -> str:
    try:
        return st.secrets.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
    except Exception:
        return os.environ.get("GEMINI_API_KEY", "")


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("Gemini API key", value=default_key(), type="password",
                            help="Free key from aistudio.google.com. Leave empty to use only your own data.")
    model = st.text_input("Gemini model", value=st.session_state.get("model", "gemini-2.5-flash-lite"),
                          help="Any model name from 'Check my models'.")
    st.session_state["model"] = model
    if st.button("Check my models", disabled=not api_key):
        try:
            st.session_state["models"] = agent.list_models(agent.make_client(api_key))
        except Exception as e:
            st.error(agent.friendly_error(e))
    if st.session_state.get("models"):
        st.caption("Models your key can use (copy one into the box above):")
        st.code("\n".join(st.session_state["models"]), language=None)
    language = st.text_input("Language for client summaries", value="English")
    use_ai = st.checkbox("Use AI for ingredients missing from my table", value=True)

    st.divider()
    st.caption(f"Ingredient table: {len(set(r['inci_name'] for r in tools.load_profiles().values()))} ingredients")
    st.caption("EU CosIng file: " + ("loaded ✓" if tools.cosing_available() else
                                      "not added (optional, see README)"))

client = agent.make_client(api_key) if api_key else None


# ------------------------------------------------------------------ analysis
def run_analysis(name: str, ingredient_text: str) -> dict:
    rows = tools.analyze_rows(ingredient_text)
    unknown = [r["as_written"] for r in rows if not r.get("group")]
    note = ""
    if unknown and client and use_ai:
        try:
            with st.spinner(f"Asking Gemini about {len(unknown)} ingredients not in your table..."):
                filled = agent.fill_unknown(client, model, unknown)
            for r in rows:
                info = filled.get(tools.normalize(r["as_written"]))
                if not r.get("group") and info:
                    for f in tools.PROFILE_FIELDS:
                        r[f] = str(info.get(f, ""))
                    r["inci_name"] = info.get("inci_name") or r["inci_name"]
                    r["source"] = (r["source"].replace("Not in database", "") +
                                   " + AI (not verified)").strip(" +")
        except Exception as e:
            note = agent.friendly_error(e)
    scores = tools.skin_type_scores(rows)
    summary = ""
    if client:
        try:
            with st.spinner("Writing the client summary..."):
                summary = agent.summarize(client, model, name, rows, scores, language)
        except Exception as e:
            note = note or agent.friendly_error(e)
    return {"name": name, "rows": rows, "scores": scores, "summary": summary, "note": note}


def show_result(res: dict) -> None:
    rows, scores = res["rows"], res["scores"]
    if not rows:
        st.warning("No ingredients found. Check the list and try again.")
        return
    st.subheader(res["name"])
    if res["note"]:
        st.warning(res["note"])

    known = sum(1 for r in rows if r.get("group"))
    strong = sum(1 for r in rows if r.get("evidence") == "Strong")
    c1, c2, c3 = st.columns(3)
    c1.metric("Ingredients", len(rows))
    c2.metric("Identified", f"{known} of {len(rows)}")
    c3.metric("Strong-evidence ingredients", strong)

    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Which skin type does it suit?**")
        df = pd.DataFrame({"Skin type": list(scores), "Match score": list(scores.values())})
        st.bar_chart(df, x="Skin type", y="Match score", color="#2F6F62")
    with right:
        best = max(scores.values()) if scores else 0
        table = pd.DataFrame([{"Skin type": s, "Result": tools.match_label(v, best)}
                              for s, v in sorted(scores.items(), key=lambda x: -x[1])])
        st.dataframe(table, hide_index=True, width="stretch")
        st.caption("Ingredients near the top of the list count more, because they are used in larger amounts.")

    if res["summary"]:
        st.markdown("**Summary for the client**")
        st.info(res["summary"])
    elif not client:
        st.caption("Add a Gemini API key in the sidebar to get a written client summary.")

    st.markdown("**Ingredients by group**")
    for group, names in sorted(tools.group_summary(rows).items(), key=lambda x: -len(x[1])):
        with st.expander(f"{group} ({len(names)})"):
            sub = [r for r in rows if (r.get("group") or "Not in my table") == group]
            cols = [c for c in SHOW_COLS if any(r.get(c) for r in sub)]
            st.dataframe(pd.DataFrame(sub)[cols], hide_index=True, width="stretch")

    full = pd.DataFrame(rows)
    full = full[[c for c in SHOW_COLS if c in full.columns]]
    st.download_button("Download full table (CSV)", full.to_csv(index=False).encode("utf-8"),
                       file_name=f"{res['name'][:40]}_analysis.csv".replace(" ", "_"),
                       mime="text/csv")


# ------------------------------------------------------------------ page
st.title("Day Cream Ingredient Agent")
st.write("Find each ingredient's group, function and features, and which skin types a day cream suits.")

tab1, tab2, tab3, tab4 = st.tabs(["Analyze a cream", "My 20 creams", "Ask the agent", "Ingredient table"])

with tab1:
    mode = st.radio("How do you want to add the cream?",
                    ["Paste the ingredient list", "Search by product name"], horizontal=True)
    if mode == "Paste the ingredient list":
        if st.button("Fill in an example list"):
            st.session_state["paste"] = EXAMPLE
        name = st.text_input("Cream name", value="My day cream")
        text = st.text_area("Ingredient list (from the packaging or brand website)",
                            key="paste", height=140)
        if st.button("Analyze ingredients", type="primary", disabled=not text.strip()):
            st.session_state["res1"] = run_analysis(name, text)
    else:
        query = st.text_input("Product name", placeholder="for example: Nivea Q10 day cream")
        if st.button("Search and analyze", type="primary", disabled=not query.strip()):
            with st.spinner("Searching your creams and Open Beauty Facts..."):
                found = tools.search_product(query)
            if found["found"]:
                st.success(f"Found in {found['source']}: {found['product_name']} {found['brand']}")
                st.session_state["res1"] = run_analysis(found["product_name"], found["ingredients"])
            else:
                st.error(found["message"])
    if st.session_state.get("res1"):
        show_result(st.session_state["res1"])

with tab2:
    creams = pd.read_csv(os.path.join(tools.DATA_DIR, "creams.csv"), dtype=str).fillna("")
    have = (creams["ingredients"].str.strip() != "").sum()
    st.write(f"{have} of {len(creams)} creams have an ingredient list.")
    pick = st.selectbox("Choose a cream", creams["name"].tolist())
    current = creams.loc[creams["name"] == pick, "ingredients"].iloc[0]

    area_key = f"area_{pick}"
    if area_key not in st.session_state:
        st.session_state[area_key] = current
    b1, b2 = st.columns(2)
    if b1.button("Fetch ingredients from Open Beauty Facts"):
        with st.spinner("Searching Open Beauty Facts..."):
            found = tools.search_product(pick)
        if found["found"]:
            st.session_state[area_key] = found["ingredients"]
            st.success(f"Found: {found['product_name']} ({found['brand']}). Check it matches your product, then save.")
        else:
            st.error(found["message"])
    edited = st.text_area("Ingredient list", key=area_key, height=140)
    if b2.button("Save to my creams list", disabled=not edited.strip()):
        tools.save_cream_ingredients(pick, edited)
        st.success("Saved.")
    if st.button("Analyze this cream", type="primary", disabled=not edited.strip()):
        st.session_state["res2"] = run_analysis(pick, edited)
    if st.session_state.get("res2"):
        show_result(st.session_state["res2"])

with tab3:
    st.write("Ask anything. The agent decides by itself which tools to use: product search, "
             "ingredient lookup, or full analysis.")
    st.caption("Examples: “Is Nivea Q10 day cream good for oily skin?” · "
               "“What group is squalane in and which skin types does it suit?”")
    if not client:
        st.info("Add your Gemini API key in the sidebar to chat with the agent.")
    else:
        history = st.session_state.setdefault("chat", [])
        for m in history:
            with st.chat_message("user" if m["role"] == "user" else "assistant"):
                st.markdown(m["text"])
        question = st.chat_input("Ask about a day cream or an ingredient")
        if question:
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                with st.spinner("Searching the data sources..."):
                    try:
                        answer = agent.chat(client, model, history, question)
                    except Exception as e:
                        answer = agent.friendly_error(e)
                st.markdown(answer)
            history += [{"role": "user", "text": question}, {"role": "model", "text": answer}]
        if history and st.button("Clear chat"):
            st.session_state["chat"] = []
            st.rerun()

with tab4:
    st.write("This is your curated knowledge. Edit `data/ingredients.csv` to add or correct ingredients.")
    table = pd.read_csv(os.path.join(tools.DATA_DIR, "ingredients.csv"), dtype=str).fillna("")
    group = st.selectbox("Filter by group", ["All groups"] + sorted(table["group"].unique()))
    if group != "All groups":
        table = table[table["group"] == group]
    st.dataframe(table, hide_index=True, width="stretch")

st.caption("General cosmetic information, not medical advice. For skin conditions, see a dermatologist.")
