import os
import re

with open('pipeline/generate_answer.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add CACHE_PATH
if 'CACHE_PATH =' not in content:
    content = content.replace('CONTENT_DIR = PROJECT_ROOT / "content"', 'CONTENT_DIR = PROJECT_ROOT / "content"\nCACHE_PATH = PROJECT_ROOT / "output" / "nl_translations_cache.json"')

# 2. Add force_refresh to synthesize_entity_details
content = content.replace(
    'def synthesize_entity_details(data, provider, model, api_key):',
    'def synthesize_entity_details(data, provider, model, api_key, force_refresh=False, nl_cache=None):'
)

# 3. Inside synthesize_entity_details, use the cache
cache_logic = """
    if nl_cache is None: nl_cache = {}
    if not force_refresh and data["id"] in nl_cache:
        c = nl_cache[data["id"]]
        print(f"  [Synth] Loaded cached translations for {data['id']}")
        return c.get("name_ru", ""), c.get("name_en", ""), c.get("desc_ru", ""), c.get("desc_en", "")
"""
content = content.replace(
    'ru_name, en_name = parse_bilingual_title(data["title"])',
    cache_logic + '\n    ru_name, en_name = parse_bilingual_title(data["title"])'
)

# 4. Remove NL_DESCRIPTIONS fallback
content = content.replace(
    'desc_ru = NL_DESCRIPTIONS.get(data["id"], "").strip()',
    'desc_ru = ""'
)

# 5. Save back to cache
save_logic = """
        synth_desc_en = re.sub(r"\\s*\\[[^\\]]+\\]", "", synth_desc_en).strip()
        
        # Save to cache
        nl_cache[data["id"]] = {
            "id": data["id"],
            "type": data.get("type", "unknown"),
            "name_ru": synth_ru_name,
            "name_en": synth_en_name,
            "desc_ru": synth_desc_ru,
            "desc_en": synth_desc_en
        }
        try:
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                import json
                json.dump(nl_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Warning] Failed to write to translation cache: {e}")
"""
content = content.replace(
    'synth_desc_en = re.sub(r"\\s*\\[[^\\]]+\\]", "", synth_desc_en).strip()',
    save_logic
)

# 6. Add argparse --force-refresh
content = content.replace(
    'parser.add_argument("--no-validate", action=\'store_true\')',
    'parser.add_argument("--no-validate", action=\'store_true\')\n    parser.add_argument("--force-refresh", action=\'store_true\', help=\'Force override of cached NLP translations\')'
)

# 7. In main(), load cache and pass it, and apply enrichment
main_logic = """
    nl_cache = {}
    if CACHE_PATH.exists():
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            import json
            nl_cache = json.load(f)
"""
content = content.replace(
    'args = parser.parse_args()',
    'args = parser.parse_args()\n\n' + main_logic
)

content = content.replace(
    '''synth_ru, synth_en, desc_ru, desc_en = synthesize_entity_details(
            data=data,
            provider=synth_provider,
            model=synth_model,
            api_key=synth_api_key
        )''',
    '''synth_ru, synth_en, desc_ru, desc_en = synthesize_entity_details(
            data=data,
            provider=synth_provider,
            model=synth_model,
            api_key=synth_api_key,
            force_refresh=args.force_refresh,
            nl_cache=nl_cache
        )
        
        # Enrich NLP descriptions with hyperlinks for known entities in the cache
        def enrich_text(text):
            if not text: return text
            # sort by length descending to match longest names first
            sorted_entities = sorted(nl_cache.values(), key=lambda x: len(x.get("name_ru", "")), reverse=True)
            for ent in sorted_entities:
                n_ru = ent.get("name_ru", "").strip()
                eid = ent.get("id", "")
                if len(n_ru) > 3 and eid != data["id"]:
                    # Match the exact word, case-sensitive or insensitive depending on needs
                    # Just simple word match for now
                    import re
                    pattern = r"(?<!\\\\hyperlink\\{)" + re.escape(n_ru) + r"(?![a-zA-Zа-яА-Я])"
                    text = re.sub(pattern, f"\\\\hyperlink{{{eid}}}{{{n_ru}}}", text)
            return text
            
        desc_ru = enrich_text(desc_ru)
'''
)

with open('pipeline/generate_answer.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched generate_answer.py")
