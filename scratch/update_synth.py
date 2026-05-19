import re

with open(r'f:\Universe\Projects\Учебник по матанализу\pipeline\canonical_synthesizer.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the start and end of synthesize_cluster
match = re.search(r'def synthesize_cluster\(cluster_id, formulations, sources,(.*?)(?=def main\(\):)', content, flags=re.DOTALL)
if not match:
    print("Function not found!")
    exit(1)

old_func = match.group(0)

new_func = '''def synthesize_cluster(cluster_id, formulations, sources, page_refs, has_proof=False, model="qwen3:8b"):
    import time
    print(f"\\n{'='*60}", flush=True)
    print(f"[synthesizer] Cluster: {cluster_id}", flush=True)
    print(f"[synthesizer] Sources: {', '.join(sources)} ({len(formulations)} formulations)", flush=True)

    entity_type = detect_entity_type_from_text(formulations, has_proof=has_proof)
    print(f"[synthesizer] Detected entity type: {entity_type}", flush=True)

    max_attempts = 7
    print(f"[synthesizer] Starting LLM Synthesis Loop (max {max_attempts} attempts)...", flush=True)

    current_attempt = 1
    semantic_error_feedback = ""
    syntax_error_feedback = ""
    implicit_assumptions = ""
    
    latex_content = ""
    lean_code = ""
    valid_lean_code = None

    from pipeline.export_to_lean import translate_to_lean_via_llm, translate_to_lean_regex, is_semantic_error
    from pipeline.lean_validator import validate_entity, discover_mathlib_signatures
    from pipeline.ensemble_extractor import gather_implicit_assumptions
    from pipeline.export_to_lean import _LLM_PROVIDER
    active_provider_name = (_LLM_PROVIDER or "OLLAMA").upper()

    while current_attempt <= max_attempts:
        print(f"\\n[synthesizer] --- Attempt {current_attempt}/{max_attempts} ---", flush=True)
        
        # 1. Regenerate LaTeX if missing or if semantic error occurred
        if not latex_content or semantic_error_feedback:
            prompt = build_synthesis_prompt(cluster_id, formulations, sources, entity_type, implicit_assumptions)
            current_prompt = prompt
            
            if semantic_error_feedback:
                print(f"[synthesizer] Injecting semantic/type error feedback into LaTeX prompt...", flush=True)
                current_prompt += f"\\n\\nПРЕДУПРЕЖДЕНИЕ: Твоя предыдущая формулировка семантически неполна или отклонена формализатором Lean.\\nОбратная связь от Lean:\\n{semantic_error_feedback}\\n\\nОБЯЗАТЕЛЬНО явно укажи все неявные типы, кванторы (∀, ∃) и домены."

            print(f"[synthesizer] Sending prompt to {active_provider_name} LLM to generate LaTeX...", flush=True)
            t0 = time.time()
            response = query_llm(current_prompt, model=model)
            elapsed = time.time() - t0
            print(f"[synthesizer] LLM responded in {elapsed:.1f}s ({len(response)} chars)", flush=True)

            if not response or len(response.strip()) < 10:
                print("[synthesizer] [ERROR] LLM returned empty response or error. Failing attempt.")
                current_attempt += 1
                semantic_error_feedback = "LLM response was empty or API error occurred."
                continue

            response = re.sub(r'^```latex\\s*', '', response, flags=re.MULTILINE)
            response = re.sub(r'^```\\s*', '', response, flags=re.MULTILINE)

            # Parse LaTeX block
            header_match = re.search(r'(% entity-id:.*)', response, re.DOTALL)
            if header_match:
                latex_content = header_match.group(1).strip()
                second_header = re.search(r'\\n% entity-id:', latex_content[1:])
                if second_header:
                    latex_content = latex_content[:second_header.start() + 1].strip()
            else:
                env_match = re.search(r'(\\\\begin\\{[a-z]+\\}.*?\\\\end\\{[a-z]+\\})', response, re.DOTALL)
                if env_match:
                    latex_content = env_match.group(1).strip()
                else:
                    latex_content = response

            latex_content = enforce_single_entity(latex_content)
            latex_content = sanitize_terminal_entityrefs(latex_content)
            latex_content = sanitize_raw_delimiters(latex_content)
            
            nl_warnings = warn_natural_language(latex_content)
            if nl_warnings:
                print(f"[synthesizer] [WARN] Natural language detected: {nl_warnings}")
                semantic_error_feedback = "\\n".join(nl_warnings)
                current_attempt += 1
                continue
                
            semantic_error_feedback = ""
            syntax_error_feedback = ""
            lean_code = ""

        # 2. Extract metadata for Lean Translation
        match_id_temp = re.search(r"^% entity-id:\\s*(.+)$", latex_content, re.MULTILINE)
        match_type_temp = re.search(r'% entity-type:\\s*([a-zA-Z]+)', latex_content)
        temp_eid = match_id_temp.group(1).strip() if match_id_temp else "temp_entity"
        temp_etype = match_type_temp.group(1).strip() if match_type_temp else "axiom"

        # Mathlib discovery
        import string
        clean_title = temp_eid.replace('def-', '').replace('op-', '').replace('obj-', '').replace('prop-', '').replace('thm-', '').replace('-', ' ')
        entity_words = [w for w in clean_title.split() if len(w) > 2]
        discovery_terms = [w.title() for w in entity_words]
        if len(entity_words) >= 2:
            discovery_terms.append(''.join(w.title() for w in entity_words))
        discovery_terms = list(set(discovery_terms))[:4]
        
        signatures = []
        if discovery_terms and not syntax_error_feedback: 
            print(f"  [synthesizer] Running Mathlib discovery for terms: {discovery_terms}")
            try:
                signatures = discover_mathlib_signatures(discovery_terms)
            except Exception as e:
                pass
        hints = "\\n".join(signatures) if signatures else "No hints found."

        # 3. Translate to Lean
        lean_code_new = translate_to_lean_via_llm(
            temp_eid, temp_etype, latex_content, 
            model=model, mathlib_hints=hints, 
            error_feedback=syntax_error_feedback, previous_code=lean_code
        )
        if not lean_code_new and not lean_code:
            lean_code_new = translate_to_lean_regex(temp_eid, temp_etype, latex_content)
            
        lean_code = lean_code_new or lean_code

        if lean_code:
            print(f"  Lean validating: {lean_code[:80]}...")
            result = validate_entity(temp_eid, lean_code)
        else:
            print("  No translatable content for Lean validation, skipping.")
            result = {"status": "success", "errors": []}

        if result["status"] == "success" and not is_semantic_error(lean_code, [], temp_etype):
            print("  [OK] Lean validation passed!")
            valid_lean_code = lean_code
            break
        elif result["status"] == "timeout":
            print("  [TIMEOUT] Lean validation timed out. Proceeding without validation.")
            break
        else:
            print(f"  [FAIL] Lean validation failed or model cheated.")
            
            messages = []
            for e in result["errors"][:3]:
                msg = e.get("message", "")
                if "don't know how to synthesize placeholder" in msg:
                    type_match = re.search(r'of type\\n\\s*(.+)', msg)
                    if type_match:
                        msg = f"ОШИБКА ПЛЕЙСХОЛДЕРА (`_`): ожидается точный тип `{type_match.group(1).strip()}`."
                messages.append(msg)
                
            if is_semantic_error(lean_code, result["errors"], temp_etype):
                print("  [!] Semantic error detected (e.g. type mismatch or 'sorry' in definition). Routing back to LaTeX synthesizer.")
                semantic_error_feedback = "\\n".join(messages)
                if "sorry" in lean_code and temp_etype != "theorem":
                    semantic_error_feedback = "CRITICAL: You used `sorry` in Lean for a definition. This is strictly FORBIDDEN. You must use real Mathlib structures and explicitly bind all types."
                
                # Context Recovery (Look-back)
                if not implicit_assumptions:
                    print("  [*] Triggering Context Recovery (looking back at previous pages for implicit assumptions)...")
                    recovered_parts = []
                    for src, p_ref in zip(sources, page_refs):
                        if p_ref > 0:
                            assump = gather_implicit_assumptions(src, p_ref, "math entity", model)
                            if assump:
                                recovered_parts.append(f"[{src}]: {assump}")
                    
                    if recovered_parts:
                        implicit_assumptions = "\\n".join(recovered_parts)
                        print(f"  [+] Recovered implicit assumptions:\\n{implicit_assumptions}")
                    else:
                        print("  [-] No implicit assumptions found in preceding pages.")
                        implicit_assumptions = "NONE FOUND" # Mark as checked
            else:
                print("  [!] Syntax error detected. Routing back to Lean formalizer.")
                syntax_error_feedback = "\\n".join(messages)
                
            current_attempt += 1

    return latex_content, valid_lean_code

'''

content = content.replace(old_func, new_func)

with open(r'f:\Universe\Projects\Учебник по матанализу\pipeline\canonical_synthesizer.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated canonical_synthesizer.py")
