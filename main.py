#!/usr/bin/env python3
import os
import json
import time
from typing import List, Dict, Any, Optional

import requests
from apify import Actor

# Constants
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o-mini"  # replace with whichever model you prefer / have access to

def load_input() -> Dict[str, Any]:
    input_data = Actor.get_input() or {}
    # fallback support for environment-provided JSON (useful locally)
    env_input = os.getenv("ACTOR_INPUT_JSON")
    if env_input:
        try:
            env_obj = json.loads(env_input)
            input_data.update(env_obj)
        except Exception:
            pass
    return input_data

def openai_generate(product: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    title = product.get("title","")
    features = product.get("features", [])
    keywords = product.get("keywords", [])
    tone = product.get("tone", "professional")
    language = product.get("language", "en")

    prompt = (
        f"Write three variants of an e-commerce product description in {language} for the product titled: \"{title}\".\n\n"
        f"Product features (bullet list):\n" + ("\n".join(f"- {f}" for f in features)) + "\n\n"
        f"Target keywords: {', '.join(keywords)}\n"
        f"Tone: {tone}\n\n"
        "Outputs needed:\n"
        "1) short_title: a catchy short title (max 6 words)\n"
        "2) short_description: 1-2 sentences (max 40 words)\n"
        "3) medium_description: 2-3 short paragraphs (approx 60-120 words)\n"
        "4) long_description: in-depth paragraph (150-250 words)\n"
        "5) bullets: 5 concise feature bullets\n"
        "Return a JSON object only, with keys: short_title, short_description, medium_description, long_description, bullets (array of strings), seo_keywords (array of strings).\n"
        "Make sure all keys are present and follow the specified formats."
    )

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 700
    }

    resp = requests.post(OPENAI_CHAT_URL, headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    # The assistant message
    assistant_text = data["choices"][0]["message"]["content"].strip()

    # Try to parse JSON from assistant_text; sometimes LLMs include surrounding backticks or explanations
    try:
        candidate = assistant_text
        # strip markdown code fences if present
        if candidate.startswith("```"):
            # remove first and last code fence block
            candidate = "\n".join(candidate.split("\n")[1:-1])
        result = json.loads(candidate)
        return result
    except Exception:
        # fallback: return a basic template if parsing fails
        return template_generate(product)

def template_generate(product: Dict[str, Any]) -> Dict[str, Any]:
    title = product.get("title","")
    features = product.get("features", [])
    keywords = product.get("keywords", [])
    tone = product.get("tone", "professional")
    language = product.get("language", "en")

    # short title
    words = title.split()
    short_title = " ".join(words[:6]) if len(words) > 6 else title

    # simple sentence construction
    short_description = f"{short_title} — {features[0] if features else 'High quality product.'}"

    medium_description = f"{short_description} Designed for {', '.join(keywords[:3])}."
    if len(features) > 1:
        medium_description += " Key benefits include " + "; ".join(features[:3]) + "."

    long_description = (
        f"{title} is a thoughtfully-designed product built to deliver {', '.join(keywords[:3])}. "
        f"{' '.join(features[:5]) if features else ''} "
        "Perfect for everyday use and crafted to last."
    )

    # bullets: up to 5
    bullets = []
    for i in range(5):
        if i < len(features):
            bullets.append(features[i])
        else:
            bullets.append("Premium quality and reliable performance.")

    seo_keywords = keywords[:10]

    return {
        "short_title": short_title,
        "short_description": short_description,
        "medium_description": medium_description,
        "long_description": long_description,
        "bullets": bullets,
        "seo_keywords": seo_keywords
    }

def validate_and_normalize_input(input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    products = input_data.get("products", [])
    normalized = []
    for idx, p in enumerate(products):
        if not isinstance(p, dict):
            continue
        product = {
            "id": p.get("id", str(idx)),
            "title": p.get("title", "").strip(),
            "features": p.get("features", []),
            "keywords": p.get("keywords", []),
            "tone": p.get("tone", "professional"),
            "language": p.get("language", "en")
        }
        if not product["title"]:
            Actor.log.warning(f"Skipping product at index {idx} because title is missing.")
            continue
        normalized.append(product)
    return normalized

def main():
    Actor.init()
    try:
        input_data = load_input()
        use_openai = bool(input_data.get("use_openai", False))
        input_key = input_data.get("openai_api_key")
        env_key = os.getenv("OPENAI_API_KEY")
        openai_key = input_key or env_key

        if use_openai and not openai_key:
            Actor.log.warning("use_openai=true but OPENAI_API_KEY not provided. Falling back to template generator.")
            use_openai = False

        products = validate_and_normalize_input(input_data)
        if not products:
            Actor.log.info("No valid products found in input. Exiting.")
            return

        for product in products:
            Actor.log.info(f"Processing product id={product['id']} title={product['title']}")
            try:
                if use_openai:
                    result = openai_generate(product, openai_key)
                else:
                    result = template_generate(product)
            except Exception as e:
                Actor.log.exception(f"Error generating for product {product['id']}: {e}")
                result = template_generate(product)

            # structure output
            output = {
                "product_id": product["id"],
                "title": product["title"],
                "generated": result,
                "meta": {
                    "generator": "openai" if use_openai else "template",
                    "timestamp": int(time.time())
                }
            }
            # push to apify dataset
            Actor.push_data(output)

        Actor.log.info("Finished processing all products.")
    finally:
        Actor.exit()

if __name__ == "__main__":
    main()
