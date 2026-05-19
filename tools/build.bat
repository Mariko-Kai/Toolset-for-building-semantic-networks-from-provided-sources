@echo off
setlocal

echo Compiling master.tex...

:: Run pdflatex twice for TOC and references
pdflatex -output-directory=content -interaction=nonstopmode -halt-on-error content/master.tex > nul
if %errorlevel% neq 0 (
    echo [ERROR] First pass failed. Zero Compile Errors requirement violated.
    exit /b %errorlevel%
)

pdflatex -output-directory=content -interaction=nonstopmode -halt-on-error content/master.tex > nul
if %errorlevel% neq 0 (
    echo [ERROR] Second pass failed. Zero Compile Errors requirement violated.
    exit /b %errorlevel%
)

echo [SUCCESS] master.tex compiled successfully! (Zero Compile Errors)
exit /b 0
