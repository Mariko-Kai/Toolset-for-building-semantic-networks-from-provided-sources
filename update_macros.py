#!/usr/bin/env python3
"""Обновление макросов в файлах контента на актуальную версию."""

import re
from pathlib import Path

def update_macros(content: str) -> str:
    """Заменить старые макросы на новые."""
    
    replacements = [
        # Числовые множества
        (r'\\mathbb\{R\}', r'\\RealNumbers'),
        (r'\\mathbb\{N\}', r'\\NaturalNumbers'),
        (r'\\mathbb\{Z\}', r'\\IntegerNumbers'),
        (r'\\mathbb\{Q\}', r'\\RationalNumbers'),
        (r'\\mathbb\{C\}', r'\\ComplexNumbers'),
        # Пустое множество
        (r'\\emptyset', r'\\EmptyNumbers'),
    ]
    
    result = content
    for old_pattern, new_pattern in replacements:
        result = re.sub(old_pattern, new_pattern, result)
    
    return result

def main():
    content_dir = Path("content")
    tex_files = sorted(content_dir.rglob("*.tex"))
    
    # Исключаем специальные файлы
    exclude_files = {"master.tex", "TEMPLATE.tex"}
    tex_files = [f for f in tex_files if f.name not in exclude_files]
    
    updated_count = 0
    
    for filepath in tex_files:
        original_content = filepath.read_text(encoding='utf-8')
        updated_content = update_macros(original_content)
        
        if original_content != updated_content:
            filepath.write_text(updated_content, encoding='utf-8')
            print(f"✓ {filepath.relative_to(content_dir.parent)}")
            updated_count += 1
    
    print(f"\nОбновлено файлов: {updated_count}/{len(tex_files)}")

if __name__ == "__main__":
    main()
