import re
f = 'f:/Universe/Projects/Учебник по матанализу/content/mathesis_macros.sty'
c = open(f, 'r', encoding='utf-8').read()

lines = c.split('\n')
new_lines = []

for line in lines:
    if line.startswith('\\newcommand{\\'):
        match0 = re.match(r'\\newcommand\{\\([a-zA-Z]+)\}\[([0-9]+)\]\{\\hyperlink\{([^}]+)\}\{(.+)\}\}$', line)
        if match0:
            new_lines.append(line)
            continue
            
        match1 = re.match(r'\\newcommand\{\\([a-zA-Z]+)\}\{\\hyperlink\{([^}]+)\}\{(.*)\}\}$', line)
        if match1:
            macro, eid, notation = match1.groups()
                
            new_line = f'\\newcommand{{\\{macro}}}{{\\mathrel{{}}\\hyperlink{{{eid}}}{{{notation}}}\\mathrel{{}}}}'
            new_lines.append(new_line)
            continue
            
    new_lines.append(line)

open(f, 'w', encoding='utf-8').write('\n'.join(new_lines))
