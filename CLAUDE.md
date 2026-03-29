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
- `requests`, `python-dotenv` — API calls and env loading
- `playwright` — HTML-to-PNG rendering (needs `playwright install chromium`)

## Key External Services

- **OpenRouter API** (`OPENROUTER_API_KEY` in `.env`) — routes to:
  - `meta-llama/llama-3.3-70b-instruct` for recipe structuring
  - `openai/gpt-5-image-mini` for food photo generation

## Data Flow

- `recipes.json` — Raw scraped Reddit posts (source of truth, ~1MB)
- `generated.json` — Set of recipe IDs already processed (prevents re-processing)
- `cards/` — Output directory containing per-recipe: `.html` (card source), `.png` (rendered card), `.json` (structured recipe metadata)

## Card Design

Cards are 1080×1350px (Instagram portrait). Full-bleed AI food photo with a parchment-textured recipe tag overlay (bottom-right, slight rotation). "Campfire Kitchen" branding badge top-left. Uses Google Fonts (Playfair Display, Lora, Open Sans). Title font size scales dynamically based on title length.
