import os
content_dir = 'content'
tex_files = []
for d in ['axioms', 'defs', 'props', 'foundations']:
    path = os.path.join(content_dir, d)
    if os.path.exists(path):
        for f in sorted(os.listdir(path)):
            if f.endswith('.tex'):
                tex_files.append(f'"content/{d}/{f}"')

master_path = os.path.join(content_dir, 'master.tex')
with open(master_path, 'r', encoding='utf-8') as f:
    master_content = f.read()

start_idx = master_content.find('\\begin{document}') + len('\\begin{document}')
preamble = master_content[:start_idx]

new_master = preamble + '\n\n'
for tf in tex_files:
    new_master += f'\\input{{{tf}}}\n'
new_master += '\\end{document}\n'

with open(master_path, 'w', encoding='utf-8') as f:
    f.write(new_master)
print(f'Rebuilt master.tex with {len(tex_files)} quoted files.')
