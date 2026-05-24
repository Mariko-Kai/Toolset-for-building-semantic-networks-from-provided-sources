f = 'f:/Universe/Projects/Учебник по матанализу/content/mathesis_macros.sty'
c = open(f, 'r', encoding='utf-8').read()

c = c.replace('\\newcommand{\\Subset}[1]', '\\newcommand{\\SetSubset}[1]')
c = c.replace('\\newcommand{\\TermSubset}{\\mathrel{}\\hyperlink{axiom-subset}{$\\subset$}\\mathrel{}}', '\\newcommand{\\TermSubset}{\\mathrel{}\\hyperlink{axiom-subset}{$\\subset$}\\mathrel{}}')
c = c.replace('\\newcommand{\\Fol5}', '\\newcommand{\\FolFive}')
c = c.replace('\\newcommand{\\Fol4}', '\\newcommand{\\FolFour}')

open(f, 'w', encoding='utf-8').write(c)
