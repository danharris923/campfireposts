#!/usr/bin/env python3
"""
Generate campfire recipe cards from scraped recipes.
1. LLM structures raw Reddit posts into clean recipes
2. Image gen creates a mouth-watering hero food photo
3. Renders styled HTML card with photo -> PNG
"""

import json
import os
import re
import time
import base64
import random
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TEXT_MODEL = "meta-llama/llama-3.3-70b-instruct"
IMAGE_MODEL = "openai/gpt-5-image-mini"

RECIPES_FILE = Path(__file__).parent / "recipes.json"
CARDS_DIR = Path(__file__).parent / "cards"
TRACKER_FILE = Path(__file__).parent / "generated.json"

BATCH_SIZE = 10


def load_recipes() -> list:
    with open(RECIPES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_tracker() -> set:
    if TRACKER_FILE.exists():
        with open(TRACKER_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_tracker(ids: set):
    with open(TRACKER_FILE, "w") as f:
        json.dump(list(ids), f)


def call_llm(prompt: str, model: str = None) -> str | None:
    """Call OpenRouter text LLM."""
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model or TEXT_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 2000,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        else:
            print(f"  LLM error {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  LLM request failed: {e}")
        return None


def generate_card_image(recipe: dict) -> bytes | None:
    """Generate the complete recipe card as one AI image via OpenRouter.
    GPT renders food styling + parchment recipe card together."""

    title = recipe["title"]
    subtitle = recipe.get("subtitle", "Made right over the campfire!")
    ingredients = recipe.get("ingredients", [])
    cook_method = recipe.get("cook_method", "campfire")

    method_settings = {
        "campfire": "cooked on a portable propane camp grill",
        "dutch_oven": "in a cast iron dutch oven on a camp stove or propane burner",
        "cast_iron": "in a cast iron skillet on a camp grill grate",
        "foil_packet": "in foil packets on a camp grill or portable propane grill",
        "grill": "on a portable camping grill or propane camp grill",
        "camp_stove": "on a portable camp stove outdoors",
    }
    setting = method_settings.get(cook_method, "cooked over a campfire")

    # Format ingredients as a bullet list for the prompt
    ing_list = "\n".join(f"• {ing}" for ing in ingredients)

    # Build condensed steps summary for the parchment
    steps = recipe.get("steps", [])
    steps_list = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))

    prompt = f"""Generate a beautiful food photography recipe card image in portrait orientation (3:4 aspect ratio).

COMPOSITION — three layers, all in ONE image:
1. BACKGROUND: The raw ingredients for this recipe ({', '.join(ingredients[:6])}) arranged in small rustic bowls and plates on a natural outdoor surface — a weathered picnic table, tree stump, or campsite prep area. These should be clearly visible behind and around the other elements.
2. FEATURED DISH: A large, appetizing, freshly-cooked serving of {title} {setting}, placed prominently in the lower-right area. It should look steaming hot, delicious, mouth-watering. This is the hero of the image.
3. RECIPE CARD: An aged, torn notebook-style parchment page on the LEFT side of the image (covering roughly the left 40%). It has spiral binding holes along its left edge. The parchment has this text written on it in a handwritten/serif style:

Title (large, bold, uppercase): {title}
Subtitle (italic, smaller): "{subtitle}"
Header (underlined): INGREDIENTS
{ing_list}

Header (underlined): HOW TO MAKE
{steps_list}

STYLE: Professional food photography with NEUTRAL, natural daylight color balance. NO yellow/amber/orange color cast — the lighting should look like a bright overcast day or clean natural light, NOT smoky firelight. Colors should be true-to-life: whites look white, greens look green, food has its real colors. Shallow depth of field on the background ingredients, the featured dish is sharp and vibrant. The parchment recipe card looks weathered and aged with slight coffee stains. The recipe card should NOT cover or block the featured dish — it sits to the left while the dish is to the right.

REALISM: The scene must look authentic and believable. Use realistic camp cooking equipment — portable propane grills, camp stoves, grill grates on stands. NO open flames on wooden tables or surfaces. Match the setting to the recipe. Variety is good.

No watermarks. No logos."""

    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": IMAGE_MODEL,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=180,
        )

        if resp.status_code != 200:
            print(f"  Image gen error {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()
        msg = data["choices"][0]["message"]
        images = msg.get("images", [])
        if not images:
            print(f"  No image returned")
            return None

        img_url = images[0]["image_url"]["url"]
        b64 = img_url.split(",")[1]
        return base64.b64decode(b64)

    except Exception as e:
        print(f"  Image gen failed: {e}")
        return None


def structure_recipe(raw_title: str, raw_body: str) -> dict | None:
    """Use LLM to extract structured recipe from a raw Reddit post."""
    prompt = f"""You are a recipe extractor. Given this Reddit post about outdoor/campfire cooking, extract a clean structured recipe.

TITLE: {raw_title}

POST BODY:
{raw_body[:3000]}

Return ONLY valid JSON (no markdown fences, no extra text) with this exact structure:
{{
  "title": "RECIPE TITLE IN ALL CAPS",
  "subtitle": "A short catchy tagline, 6-10 words",
  "ingredients": ["ingredient 1", "ingredient 2", ...],
  "steps": ["Step 1 text", "Step 2 text", ...],
  "pro_tips": ["tip 1", "tip 2", "tip 3"],
  "cook_method": "campfire|dutch_oven|cast_iron|foil_packet|grill|camp_stove",
  "category": "breakfast|lunch|dinner|dessert|snack|side|drink"
}}

Rules:
- Title should be catchy and food-focused, ALL CAPS
- Subtitle should feel warm and inviting like "Hearty, smoky & made right over the fire!"
- Keep ingredients concise with measurements
- Steps should be numbered actions, concise
- Include 2-3 pro tips for campfire/outdoor cooking
- If the post doesn't contain enough info for a real recipe, return exactly: {{"skip": true}}
- cook_method should reflect how this is cooked outdoors
- Make it feel like a campfire cooking recipe even if the original is vague"""

    result = call_llm(prompt)
    if not result:
        return None

    result = result.strip()
    result = re.sub(r'^```json\s*', '', result)
    result = re.sub(r'\s*```$', '', result)

    try:
        data = json.loads(result)
        if data.get("skip"):
            return None
        if not all(k in data for k in ["title", "ingredients", "steps"]):
            return None
        if len(data["ingredients"]) < 2 or len(data["steps"]) < 2:
            return None
        return data
    except json.JSONDecodeError:
        print(f"  Failed to parse LLM JSON")
        return None


FONT_IMPORT = "@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Lora:ital,wght@0,400;0,600;0,700;1,400;1,600&family=Open+Sans:wght@400;600;700&display=swap');"

BRAND_SVG = """<svg class="brand-icon" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
      <path d="M50 5 C50 5,25 35,25 55 C25 72,35 85,50 90 C65 85,75 72,75 55 C75 35,50 5,50 5Z" fill="#c44e1a" opacity="0.9"/>
      <path d="M50 25 C50 25,35 48,35 60 C35 72,41 78,50 82 C59 78,65 72,65 60 C65 48,50 25,50 25Z" fill="#e8871e" opacity="0.85"/>
      <path d="M50 42 C50 42,42 55,42 63 C42 70,45 74,50 76 C55 74,58 70,58 63 C58 55,50 42,50 42Z" fill="#f5c842" opacity="0.9"/>
    </svg>"""

# Campfire line-art SVG used as a decorative illustration on the parchment
CAMPFIRE_ILLUSTRATION = """<svg class="illustration" viewBox="0 0 120 100" xmlns="http://www.w3.org/2000/svg">
  <g opacity="0.35" fill="none" stroke="#6b4226" stroke-width="1.2" stroke-linecap="round">
    <!-- logs -->
    <line x1="20" y1="88" x2="100" y2="88"/>
    <line x1="30" y1="82" x2="90" y2="82"/>
    <line x1="25" y1="92" x2="95" y2="85"/>
    <line x1="25" y1="85" x2="95" y2="92"/>
    <!-- flames -->
    <path d="M60 78 Q55 55 60 35 Q65 55 60 78" fill="rgba(107,66,38,0.15)"/>
    <path d="M50 80 Q45 60 55 42 Q58 60 50 80" fill="rgba(107,66,38,0.1)"/>
    <path d="M70 80 Q75 60 65 42 Q62 60 70 80" fill="rgba(107,66,38,0.1)"/>
    <!-- sparks -->
    <circle cx="52" cy="30" r="1" fill="#6b4226" opacity="0.3"/>
    <circle cx="68" cy="25" r="0.8" fill="#6b4226" opacity="0.25"/>
    <circle cx="58" cy="20" r="1.2" fill="#6b4226" opacity="0.2"/>
  </g>
</svg>"""


def build_card_html(recipe: dict, food_image_path: str) -> str:
    """Build HTML card: notebook-page parchment on left with spiral binding,
    food photo filling the background. Shows ingredients, how to make, pro tips."""

    with open(food_image_path, "rb") as img_f:
        img_b64 = base64.b64encode(img_f.read()).decode("ascii")
    image_uri = f"data:image/png;base64,{img_b64}"

    title = recipe["title"]
    subtitle = recipe.get("subtitle", "Made right over the campfire!")
    ingredients = recipe.get("ingredients", [])
    steps = recipe.get("steps", [])
    pro_tips = recipe.get("pro_tips", [])[:3]

    title_len = len(title)
    if title_len <= 18:
        title_size = 48
    elif title_len <= 28:
        title_size = 42
    elif title_len <= 40:
        title_size = 36
    else:
        title_size = 30

    ing_html = "\n".join(f'<li>{ing}</li>' for ing in ingredients)
    steps_html = "\n".join(
        f'<li><span class="sn">{i}.</span> {s}</li>'
        for i, s in enumerate(steps, 1)
    )
    tips_html = "\n".join(f'<li>{t}</li>' for t in pro_tips)

    # Spiral binding holes — 10 evenly spaced down the left edge
    holes_html = "\n".join(
        f'<div class="hole" style="top:{65 + i * 122}px;"></div>'
        for i in range(10)
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  {FONT_IMPORT}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; height:1350px; overflow:hidden; }}
  .card {{ width:1080px; height:1350px; position:relative; overflow:hidden; }}

  /* ===== FOOD PHOTO BACKGROUND ===== */
  .food-bg {{ position:absolute; top:0; left:0; right:0; bottom:0; z-index:1; }}
  .food-bg img {{ width:100%; height:100%; object-fit:cover; }}

  /* ===== NOTEBOOK PARCHMENT PAGE (left side) ===== */
  .notebook {{
    position:absolute; top:0; left:0; bottom:0; width:560px; z-index:5;
    background:
      /* Age stains */
      radial-gradient(ellipse at 75% 20%, rgba(160,120,60,0.15) 0%, transparent 45%),
      radial-gradient(ellipse at 30% 80%, rgba(140,100,50,0.12) 0%, transparent 40%),
      radial-gradient(ellipse at 50% 50%, rgba(170,130,70,0.06) 0%, transparent 60%),
      /* Burnt/worn edge on right */
      linear-gradient(to right,
        transparent 85%, rgba(100,60,20,0.12) 95%, rgba(80,40,10,0.2) 100%),
      /* Parchment base */
      linear-gradient(175deg,
        #f5e6be 0%, #f0deb2 15%, #ebdaab 30%, #f2e1b5 50%,
        #e9d5a2 70%, #f0dcae 85%, #e6d09a 100%);
    box-shadow:
      6px 0 25px rgba(0,0,0,0.4),
      2px 0 8px rgba(0,0,0,0.25),
      inset -10px 0 20px rgba(100,60,20,0.06);
    padding: 40px 30px 30px 55px;
  }}

  /* Torn/rough right edge */
  .notebook::after {{
    content: '';
    position: absolute;
    top: 0; right: -6px; bottom: 0; width: 12px;
    background: linear-gradient(to right,
      rgba(229,208,154,0.6) 0%,
      rgba(229,208,154,0.3) 40%,
      transparent 100%);
    filter: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'><filter id='r'><feTurbulence baseFrequency='0.08' numOctaves='4'/><feDisplacementMap in='SourceGraphic' scale='6'/></filter></svg>#r");
  }}

  /* Spiral binding holes */
  .hole {{
    position: absolute;
    left: 18px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: radial-gradient(circle,
      rgba(40,25,10,0.6) 0%, rgba(40,25,10,0.3) 40%,
      rgba(80,50,20,0.15) 70%, transparent 100%);
    box-shadow: inset 0 1px 3px rgba(0,0,0,0.4), 0 1px 1px rgba(255,240,200,0.3);
    z-index: 10;
  }}

  /* ===== TYPOGRAPHY ===== */
  .title {{
    font-family: 'Playfair Display', Georgia, serif;
    font-weight: 900;
    font-size: {title_size}px;
    line-height: 1.08;
    color: #2a1508;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 6px;
  }}

  .subtitle {{
    font-family: 'Lora', Georgia, serif;
    font-style: italic;
    font-size: 16px;
    color: #7a4a28;
    margin-bottom: 16px;
  }}

  .section-head {{
    font-family: 'Playfair Display', Georgia, serif;
    font-weight: 700;
    font-size: 21px;
    color: #8b4513;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 6px;
    padding-bottom: 4px;
    border-bottom: 2px solid rgba(139,69,19,0.35);
    display: inline-block;
  }}

  /* ===== INGREDIENTS ===== */
  .ingredients {{ list-style:none; padding:0; margin-bottom:14px; }}
  .ingredients li {{
    font-family: 'Lora', Georgia, serif;
    font-size: 16px;
    line-height: 1.55;
    color: #2e1a0e;
    padding-left: 20px;
    position: relative;
  }}
  .ingredients li::before {{
    content: '\\2022';
    position: absolute;
    left: 3px;
    color: #2e1a0e;
    font-size: 18px;
  }}

  /* ===== STEPS ===== */
  .steps {{ list-style:none; padding:0; margin-bottom:14px; }}
  .steps li {{
    font-family: 'Lora', Georgia, serif;
    font-size: 15px;
    line-height: 1.5;
    color: #2e1a0e;
    margin-bottom: 2px;
  }}
  .sn {{ font-family:'Open Sans',sans-serif; font-weight:700; color:#8b4513; }}

  /* ===== PRO TIPS ===== */
  .tips {{ border-top:1px solid rgba(139,69,19,0.25); padding-top:10px; margin-top:6px; }}
  .tips ul {{ list-style:none; padding:0; }}
  .tips li {{
    font-family: 'Lora', Georgia, serif;
    font-size: 14px;
    line-height: 1.45;
    color: #5a3a1a;
    padding-left: 18px;
    position: relative;
  }}
  .tips li::before {{
    content: '\\2713';
    position: absolute;
    left: 0;
    color: #8b4513;
    font-weight: 700;
  }}
  .tips-head {{
    font-family: 'Playfair Display', Georgia, serif;
    font-weight: 700;
    font-size: 18px;
    color: #8b4513;
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 1px;
  }}

  /* ===== DECORATIVE ILLUSTRATION ===== */
  .illustration {{
    position: absolute;
    bottom: 30px;
    right: 20px;
    width: 90px;
    height: 75px;
    opacity: 0.5;
  }}

  /* ===== BRANDING (bottom-right over photo) ===== */
  .branding {{
    position:absolute; bottom:28px; right:28px; z-index:10;
    display:flex; align-items:center; gap:10px;
    background:rgba(0,0,0,0.5); backdrop-filter:blur(8px);
    padding:10px 20px 10px 14px; border-radius:6px;
  }}
  .brand-icon {{ width:36px; height:36px; flex-shrink:0; }}
  .brand-text {{ display:flex; flex-direction:column; }}
  .brand-name {{ font-family:'Playfair Display',Georgia,serif; font-weight:900;
    font-size:17px; color:#f4e8c1; text-transform:uppercase; letter-spacing:3px; line-height:1.1; }}
  .brand-sub {{ font-family:'Open Sans',sans-serif; font-weight:700;
    font-size:9px; color:#d4b87a; text-transform:uppercase; letter-spacing:4px; }}
</style></head>
<body>
<div class="card">

  <!-- Full-bleed food photo -->
  <div class="food-bg">
    <img src="{image_uri}" alt="{title}">
  </div>

  <!-- Notebook parchment page -->
  <div class="notebook">
    {holes_html}
    <div class="title">{title}</div>
    <div class="subtitle">"{subtitle}"</div>

    <div class="section-head">Ingredients</div>
    <ul class="ingredients">{ing_html}</ul>

    <div class="section-head">How to Make</div>
    <ol class="steps">{steps_html}</ol>

    {f'<div class="tips"><div class="tips-head">Pro Tips</div><ul>{tips_html}</ul></div>' if pro_tips else ""}

    {CAMPFIRE_ILLUSTRATION}
  </div>

  <!-- Branding badge -->
  <div class="branding">
    {BRAND_SVG}
    <div class="brand-text">
      <span class="brand-name">Campfire</span>
      <span class="brand-sub">Kitchen</span>
    </div>
  </div>

</div>
</body></html>"""

    return html


def render_card(html: str, output_path: Path):
    """Render HTML to PNG using Playwright."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1350})
        page.set_content(html, wait_until="networkidle")
        page.wait_for_timeout(2000)
        page.screenshot(path=str(output_path), type="png")
        browser.close()


def process_recipe(raw: dict, generated: set) -> bool:
    """Process a single recipe: structure with LLM -> generate complete card image."""
    safe_title = raw["title"][:50].encode("ascii", "replace").decode("ascii")
    print(f"  {safe_title}")
    print(f"  Score: {raw['score']} | {raw['source']}")

    # Step 1: Structure with LLM
    print(f"  [1/2] Structuring recipe...")
    structured = structure_recipe(raw["title"], raw.get("body", ""))
    if not structured:
        print(f"  SKIP (not a real recipe)")
        return False

    recipe_title = structured["title"]
    cook_method = structured.get("cook_method", "campfire")
    print(f"  => {recipe_title} ({cook_method})")

    slug = re.sub(r'[^a-z0-9]+', '_', recipe_title.lower()).strip('_')[:60]

    # Step 2: Generate complete card image (food + parchment + text in one)
    print(f"  [2/2] Generating card image...")
    img_bytes = generate_card_image(structured)
    if not img_bytes:
        print(f"  SKIP (image gen failed)")
        return False

    card_path = CARDS_DIR / f"{slug}.png"
    with open(card_path, "wb") as f:
        f.write(img_bytes)
    print(f"  Card saved ({len(img_bytes)//1024}KB)")

    # Save metadata
    meta_path = CARDS_DIR / f"{slug}.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        structured["source_id"] = raw["id"]
        structured["source_url"] = raw.get("source_url", "")
        structured["source_score"] = raw["score"]
        json.dump(structured, f, indent=2, ensure_ascii=False)

    print(f"  DONE -> {card_path.name}")
    return True


def main():
    print("=" * 60)
    print("  CAMPFIRE RECIPE CARD GENERATOR")
    print("  (with AI food photography)")
    print("=" * 60)

    if not OPENROUTER_API_KEY:
        print("ERROR: Set OPENROUTER_API_KEY in .env")
        return

    CARDS_DIR.mkdir(exist_ok=True)

    recipes = load_recipes()
    generated = load_tracker()

    print(f"Total recipes: {len(recipes)}")
    print(f"Already processed: {len(generated)}")

    # Candidates: enough body text + recipe signals
    candidates = [
        r for r in recipes
        if r["id"] not in generated
        and len(r.get("body", "")) > 120
        and r.get("signal_count", 0) >= 6
    ]
    candidates.sort(key=lambda r: r["score"], reverse=True)

    batch = candidates[:BATCH_SIZE]
    print(f"Candidates: {len(candidates)}")
    print(f"Processing batch of {len(batch)}\n")

    success_count = 0

    for i, raw in enumerate(batch, 1):
        print(f"\n[{i}/{len(batch)}]")

        ok = process_recipe(raw, generated)
        if ok:
            success_count += 1

        generated.add(raw["id"])
        save_tracker(generated)
        time.sleep(1)

    print(f"\n{'=' * 60}")
    print(f"  Generated {success_count}/{len(batch)} cards")
    print(f"  Total processed: {len(generated)}")
    print(f"  Cards in: {CARDS_DIR}/")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
