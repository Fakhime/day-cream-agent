"""
agent.py - The "brain" of the agent (Google Gemini, free tier).

- fill_unknown(): asks Gemini about ingredients that are not in your table
- summarize():    writes a client-friendly summary of a cream
- chat():         a real agent that decides by itself which tools to call
"""
import json
import os
import re

from google import genai
from google.genai import types

import tools

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "instructions.txt"), encoding="utf-8") as f:
    INSTRUCTIONS = f.read()

GROUPS = ["Humectant", "Emollient", "Occlusive", "Occlusive / silicone", "UV filter (mineral)",
          "UV filter (chemical)", "Antioxidant", "Active", "Soothing agent", "Barrier lipid",
          "Emulsifier", "Thickener", "Preservative", "pH adjuster", "Chelating agent",
          "Fragrance", "Solvent", "Base / solvent", "Texture / absorbent", "Colorant",
          "Plant extract", "Unknown"]


def make_client(api_key: str):
    return genai.Client(api_key=api_key)


def list_models(client) -> list:
    """Return the Gemini models your key can use for text generation."""
    names = []
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or []
        if not actions or "generateContent" in actions:
            names.append(m.name.replace("models/", ""))
    return sorted(n for n in names if "gemini" in n)


def _parse_json(text: str):
    clean = re.sub(r"```(json)?", "", text or "").strip()
    return json.loads(clean)


def fill_unknown(client, model: str, names: list) -> dict:
    """Ask Gemini to profile ingredients that are missing from ingredients.csv."""
    results = {}
    for i in range(0, len(names), 25):  # small batches keep the free tier happy
        batch = names[i:i + 25]
        prompt = f"""You are a cosmetic chemist. For each ingredient below, return a JSON array.
Each object must have these keys:
"input_name" (exactly as given), "inci_name", "group", "function", "features",
"best_for", "be_careful", "concerns", "evidence", "notes".
- group: one of {GROUPS}
- best_for and be_careful: skin types from {tools.SKIN_TYPES} or "All", separated by "; "
- evidence: "Strong", "Good", "Limited", or "N/A" for purely functional ingredients
- Keep each text short (under 20 words). Do not use commas inside skin type lists.
- If you are not sure what an ingredient is, set group to "Unknown" and say so in notes.
Ingredients: {json.dumps(batch)}"""
        resp = client.models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json",
                                               temperature=0.2))
        for item in _parse_json(resp.text):
            key = tools.normalize(item.get("input_name", ""))
            if key:
                results[key] = item
    return results


def summarize(client, model: str, cream_name: str, rows: list, scores: dict,
              language: str = "English") -> str:
    """Write a short summary a beauty adviser can read to a client."""
    compact = [{k: r.get(k, "") for k in ["position", "inci_name", "group", "features",
                                           "best_for", "be_careful", "concerns"]} for r in rows]
    prompt = f"""{INSTRUCTIONS}

Write a client-friendly summary in {language} for the day cream "{cream_name}".
Use these sections with short bullet points:
1. Best for (skin types) and who should be careful
2. Key ingredients by group and what they do
3. Skin concerns it helps with
4. Tips (for example: sunscreen needed? fragrance? heavy or light texture?)
Keep it under 250 words. Base it only on this data.

Skin type scores (higher is better, negative means be careful): {json.dumps(scores)}
Ingredients (in order, highest amount first): {json.dumps(compact)}"""
    resp = client.models.generate_content(
        model=model, contents=prompt,
        config=types.GenerateContentConfig(temperature=0.4))
    return resp.text


def chat(client, model: str, history: list, question: str) -> str:
    """The agent: Gemini reads the question and calls the tools it needs by itself."""
    config = types.GenerateContentConfig(
        system_instruction=INSTRUCTIONS,
        tools=[tools.search_product, tools.lookup_ingredient, tools.analyze_ingredient_list],
        temperature=0.3)
    contents = [types.Content(role=m["role"], parts=[types.Part(text=m["text"])])
                for m in history]
    contents.append(types.Content(role="user", parts=[types.Part(text=question)]))
    resp = client.models.generate_content(model=model, contents=contents, config=config)
    return resp.text or "The agent returned no text. Try asking again."


def friendly_error(e: Exception) -> str:
    msg = str(e)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        return "Free-tier limit reached. Wait a minute and try again, or pick another model."
    if "API key" in msg or "401" in msg or "403" in msg or "PERMISSION" in msg:
        return "Your Gemini API key was rejected. Check it in the sidebar."
    if "404" in msg or "NOT_FOUND" in msg:
        return "This model name is not available. Click 'Check my models' in the sidebar."
    return f"Gemini error: {msg}"
