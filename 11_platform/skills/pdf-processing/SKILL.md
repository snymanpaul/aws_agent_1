---
name: pdf-processing
description: Extract text, tables, and metadata from PDF documents
allowed_tools:
  - read_file
  - write_file
---

# PDF Processing Skill

You are now equipped to process PDF documents. Follow these steps:

## Step 1: Extract Content
- Use read_file to load the PDF bytes
- Identify document structure: title page, sections, tables, footnotes
- Note page count and document metadata (author, date, version)

## Step 2: Extract Tables
- Look for grid-like structures in the text
- Preserve column headers and row alignment
- Output tables in pipe-delimited markdown format

## Step 3: Summarise
- Write a 3-5 sentence executive summary at the top
- List key figures and statistics found in the document
- Flag any warnings, caveats, or redacted sections

## Output Format
Return a structured report with sections:
- **Summary**: executive overview
- **Tables**: all extracted tables
- **Key Facts**: bullet list of important numbers/dates
- **Notes**: anything unusual about the document structure
