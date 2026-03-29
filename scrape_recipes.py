#!/usr/bin/env python3
"""
Scrape campfire/outdoor cooking recipes from Reddit and recipe sites.
Outputs a big JSON collection: recipes.json
"""

import requests
import json
import time
import re
import hashlib
from datetime import datetime
from pathlib import Path

HEADERS = {
    "User-Agent": "CampfireRecipeCollector/1.0 (recipe research bot)"
}

# Reddit subs to hit
SUBREDDITS = [
    "campfirecooking",
    "CampfireCooking",
    "camping",
    "castiron",
    "dutchoven",
    "trailmeals",
    "bushcraft",
    "Outdoors",
    "overlanding",
    "BackpackingFood",
]

# Search terms for subs that aren't recipe-specific
SEARCH_TERMS = [
    "campfire recipe",
    "campfire cooking",
    "fire roasted",
    "dutch oven recipe",
    "cast iron camping",
    "foil packet",
    "camp stove recipe",
    "outdoor cooking",
    "grilled over fire",
    "campfire dessert",
    "campfire breakfast",
    "s'mores",
    "campfire chili",
    "campfire nachos",
    "hobo dinner",
    "campfire pizza",
    "campfire stew",
    "skillet camping",
    "bannock",
    "damper bread",
]

OUTPUT_FILE = Path(__file__).parent / "recipes.json"


def make_id(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


def fetch_reddit_json(url: str) -> dict:
    """Fetch a Reddit .json endpoint with rate limiting."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 429:
            print(f"  Rate limited, waiting 10s...")
            time.sleep(10)
            resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"  HTTP {resp.status_code} for {url}")
            return None
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None


def extract_recipe_from_post(post_data: dict) -> dict | None:
    """Try to extract a recipe from a Reddit post."""
    data = post_data.get("data", {})

    title = data.get("title", "").strip()
    selftext = data.get("selftext", "").strip()
    url = data.get("url", "")
    permalink = data.get("permalink", "")
    score = data.get("score", 0)
    num_comments = data.get("num_comments", 0)
    subreddit = data.get("subreddit", "")
    created = data.get("created_utc", 0)

    # Skip low effort / image-only posts with no text
    if not selftext and not title:
        return None

    # Skip very low score posts
    if score < 3:
        return None

    # Build the recipe entry
    full_text = f"{title}\n\n{selftext}"

    # Try to detect if this actually contains a recipe
    recipe_signals = [
        "ingredient", "recipe", "cook", "bake", "grill", "roast",
        "tbsp", "tsp", "cup", "oz", "lb", "degrees",
        "minutes", "hours", "heat", "stir", "mix", "add",
        "foil", "skillet", "dutch oven", "cast iron", "campfire",
        "serve", "season", "salt", "pepper", "butter", "oil",
    ]

    signal_count = sum(1 for s in recipe_signals if s.lower() in full_text.lower())

    # If it's from a cooking-specific sub, lower the bar
    cooking_subs = ["campfirecooking", "CampfireCooking", "dutchoven", "castiron", "trailmeals", "BackpackingFood"]
    is_cooking_sub = subreddit in cooking_subs

    min_signals = 2 if is_cooking_sub else 4

    if signal_count < min_signals and len(selftext) < 100:
        return None

    # Get image if available
    image = None
    if data.get("post_hint") == "image":
        image = url
    elif data.get("preview", {}).get("images"):
        try:
            image = data["preview"]["images"][0]["source"]["url"].replace("&amp;", "&")
        except (KeyError, IndexError):
            pass
    elif data.get("thumbnail", "").startswith("http"):
        image = data["thumbnail"]

    recipe = {
        "id": make_id(permalink or title),
        "title": title,
        "body": selftext,
        "source": f"reddit/r/{subreddit}",
        "source_url": f"https://reddit.com{permalink}" if permalink else url,
        "score": score,
        "num_comments": num_comments,
        "image_url": image,
        "created_utc": int(created),
        "scraped_at": datetime.now().isoformat(),
        "signal_count": signal_count,
    }

    return recipe


def scrape_subreddit(subreddit: str, limit: int = 100) -> list:
    """Scrape top/hot posts from a subreddit."""
    recipes = []

    for sort in ["top", "hot"]:
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}&t=all"
        print(f"  Fetching r/{subreddit}/{sort}...")

        data = fetch_reddit_json(url)
        if not data:
            continue

        children = data.get("data", {}).get("children", [])
        print(f"    Got {len(children)} posts")

        for post in children:
            recipe = extract_recipe_from_post(post)
            if recipe:
                recipes.append(recipe)

        time.sleep(2)  # Be nice to Reddit

        # Also grab page 2 via "after" token
        after = data.get("data", {}).get("after")
        if after:
            url2 = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}&t=all&after={after}"
            print(f"    Fetching page 2...")
            data2 = fetch_reddit_json(url2)
            if data2:
                children2 = data2.get("data", {}).get("children", [])
                print(f"    Got {len(children2)} more posts")
                for post in children2:
                    recipe = extract_recipe_from_post(post)
                    if recipe:
                        recipes.append(recipe)
            time.sleep(2)

    return recipes


def search_reddit(query: str, limit: int = 50) -> list:
    """Search Reddit globally for recipe posts."""
    recipes = []

    url = f"https://www.reddit.com/search.json?q={requests.utils.quote(query)}&limit={limit}&sort=top&t=all"
    print(f"  Searching: '{query}'...")

    data = fetch_reddit_json(url)
    if not data:
        return recipes

    children = data.get("data", {}).get("children", [])
    print(f"    Got {len(children)} results")

    for post in children:
        recipe = extract_recipe_from_post(post)
        if recipe:
            recipes.append(recipe)

    return recipes


def deduplicate(recipes: list) -> list:
    """Remove duplicate recipes by ID and similar titles."""
    seen_ids = set()
    seen_titles = set()
    unique = []

    for r in recipes:
        if r["id"] in seen_ids:
            continue

        # Normalize title for dedup
        norm_title = re.sub(r'[^a-z0-9]', '', r["title"].lower())
        if norm_title in seen_titles and len(norm_title) > 10:
            continue

        seen_ids.add(r["id"])
        seen_titles.add(norm_title)
        unique.append(r)

    return unique


def main():
    print("=" * 60)
    print("  CAMPFIRE RECIPE SCRAPER")
    print("=" * 60)

    all_recipes = []

    # Load existing if present (so we can append)
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
        print(f"\nLoaded {len(existing)} existing recipes")
        all_recipes.extend(existing)

    # 1. Scrape subreddits
    print(f"\n--- SCRAPING {len(SUBREDDITS)} SUBREDDITS ---\n")
    for sub in SUBREDDITS:
        print(f"\n[r/{sub}]")
        recipes = scrape_subreddit(sub)
        print(f"  => {len(recipes)} recipes extracted")
        all_recipes.extend(recipes)

    # 2. Search Reddit for specific terms
    print(f"\n--- SEARCHING {len(SEARCH_TERMS)} TERMS ---\n")
    for term in SEARCH_TERMS:
        recipes = search_reddit(term)
        print(f"  => {len(recipes)} recipes")
        all_recipes.extend(recipes)
        time.sleep(2)

    # 3. Deduplicate
    print(f"\n--- DEDUPLICATING ---")
    print(f"  Before: {len(all_recipes)}")
    all_recipes = deduplicate(all_recipes)
    print(f"  After:  {len(all_recipes)}")

    # 4. Sort by score
    all_recipes.sort(key=lambda r: r["score"], reverse=True)

    # 5. Save
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_recipes, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"  DONE! Saved {len(all_recipes)} recipes to {OUTPUT_FILE.name}")
    print(f"  Top 10 by score:")
    for i, r in enumerate(all_recipes[:10], 1):
        safe_title = r['title'][:60].encode('ascii', 'replace').decode('ascii')
        print(f"    {i}. [{r['score']:>5} pts] {safe_title}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
