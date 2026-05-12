import os
import re

CONTENT_DIR = r"f:\Universe\Projects\Учебник по матанализу\content"

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    # Strip \entityref{obj-function}{...}
    content = re.sub(r"\\entityref\{obj-function\}\{([^}]+)\}", r"\1", content)
    # Strip others to allow re-linking with composites
    content = re.sub(r"\\entityref\{obj-inverse-mapping\}\{([^}]+)\}", r"\1", content)
    content = re.sub(r"\\entityref\{obj-image\}\{([^}]+)\}", r"\1", content)
    content = re.sub(r"\\entityref\{obj-preimage\}\{([^}]+)\}", r"\1", content)
    
    # Also strip obj-inverse-mapping if it was linked badly (e.g. just f^-1 linked to inverse) to allow re-linking
    # But usually it's fine.

    if content != original_content:
        print(f"Resetting links in {filepath}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

def main():
    for root, dirs, files in os.walk(CONTENT_DIR):
        for file in files:
            if file.endswith(".tex"):
                process_file(os.path.join(root, file))

if __name__ == "__main__":
    main()
