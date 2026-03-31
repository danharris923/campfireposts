# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pipeline for generating social media recipe cards from Reddit campfire cooking posts. Two-stage process: scrape recipes, then generate styled cards with AI.

## Pipeline

1. **`scrape_recipes.py`** — Scrapes campfire/outdoor cooking recipes from Reddit (10 subreddits + 20 search terms). Outputs `recipes.json`. Appends to existing data and deduplicates.
2. **`generate_cards.py`** — Picks the best unprocessed recipes (by Reddit score, signal count ≥ 6, body > 120 chars), sends them through an LLM to structure into clean recipes, generates AI food photos, renders styled HTML cards to PNG. Processes in batches of 10.

## Running

```bash
# Scrape recipes from Reddit (rate-limited, takes several minutes)
python scrape_recipes.py

# Generate recipe cards (requires OPENROUTER_API_KEY in .env)
python generate_cards.py
```

## Dependencies

- Python 3.10+ (uses `dict | None` union syntax)
- `requests`, `python-dotenv` — in `requirements.txt`
- `playwright` — HTML-to-PNG rendering (not in requirements.txt; install separately with `pip install playwright && playwright install chromium`)

## Key External Services

- **OpenRouter API** (`OPENROUTER_API_KEY` in `.env`) — routes to:
  - `meta-llama/llama-3.3-70b-instruct` for recipe structuring
  - `openai/gpt-5-image-mini` for food photo generation (returns base64 images)

## Data Flow

- `recipes.json` — Raw scraped Reddit posts (source of truth, ~1MB)
- `generated.json` — Set of recipe IDs already processed (prevents re-processing)
- `cards/` — Output directory containing per-recipe: `.png` (AI-generated card image), `.json` (structured recipe metadata)

## Card Generation Process

`generate_cards.py` has two stages per recipe:
1. **LLM structuring** (`structure_recipe`) — Sends raw Reddit post to Llama 3.3 to extract title, subtitle, ingredients, steps, pro tips, cook method, and category as JSON.
2. **Image generation** (`generate_card_image`) — Sends a detailed prompt to GPT image model describing a 3-layer composition: background ingredients, hero dish, and parchment recipe card. The AI generates the complete card as a single image (no HTML rendering for final output).

Recipe filtering for candidates: `signal_count >= 6`, `body > 120 chars`, not in `generated.json`, sorted by Reddit score descending.

## Card Design

Cards are 1080×1350px (Instagram portrait). The AI-generated image contains: raw ingredients in rustic bowls as background, the hero dish prominently placed, and a torn notebook-style parchment page with the recipe text. "Campfire Kitchen" branding. Cook method maps to specific outdoor cooking settings (camp grill, dutch oven, cast iron, foil packets, etc.).
