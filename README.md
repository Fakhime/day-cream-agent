# Day Cream Ingredient Agent

Finds each ingredient's **group, function, features**, and **which skin types** a day cream suits.
Uses free tools only: Google Gemini (free tier), Open Beauty Facts, your own ingredient table, and (optionally) the EU CosIng database.

## Run it on your computer

1. Install Python 3.10 or newer from python.org (Windows: tick "Add Python to PATH").
2. Unzip this folder.
3. Get a free Gemini API key at https://aistudio.google.com ("Get API key").
4. Start the app:
   - Windows: double-click `run_windows.bat`
   - Mac/Linux: open Terminal in this folder and run `./run_mac_linux.sh`
   - Or manually: `pip install -r requirements.txt` then `streamlit run app.py`
5. Your browser opens at http://localhost:8501. Paste the API key in the sidebar.

Optional: rename `.streamlit/secrets.toml.example` to `secrets.toml` and put your key there so you don't have to paste it each time.

## Fill in your 20 creams

- Automatic: `python fetch_creams.py` (searches Open Beauty Facts), or
- In the app: tab "My 20 creams" > Fetch or paste the list > Save.
Always check the list matches the real product (formulas change over time).

## Optional: add the EU CosIng database

Download the ingredient list from the European Commission CosIng website and save it as
`data/cosing.csv` or `data/cosing.xlsx`. The app then shows the official EU function of each ingredient.

## Files

| File | What it does |
|---|---|
| app.py | Web interface (Streamlit) |
| agent.py | Gemini: fills unknown ingredients, writes client summaries, chat agent |
| tools.py | Searches all data sources and scores skin types |
| instructions.txt | The agent's instructions (edit to change its behaviour) |
| data/ingredients.csv | Your curated table (116 starter ingredients, review and extend it) |
| data/creams.csv | Your 20 day creams |

## Publish online for free (Streamlit Community Cloud)

1. Upload this folder to a GitHub repository (secrets.toml is excluded automatically).
2. Go to share.streamlit.io, click "Create app", choose the repo and `app.py`.
3. In the app's Settings > Secrets, add: `GEMINI_API_KEY = "your-key"`.

## Notes

- The starter ingredient table is general cosmetic knowledge; review it before using it with clients.
- Answers marked "AI (not verified)" come from Gemini and should be checked.
- General cosmetic information, not medical advice.
