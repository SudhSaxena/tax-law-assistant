from pypdf import PdfReader
import pdfplumber

PAGE_INDEX = 10  # any middle page, avoids cover/index pages

print("=" * 60)
print("PYPDF OUTPUT")
print("=" * 60)
reader = PdfReader("data/pub17.pdf")
pypdf_text = reader.pages[PAGE_INDEX].extract_text()
print(pypdf_text[:1500])

print()
print("=" * 60)
print("PDFPLUMBER OUTPUT")
print("=" * 60)
with pdfplumber.open("data/pub17.pdf") as pdf:
    plumber_text = pdf.pages[PAGE_INDEX].extract_text()
print(plumber_text[:1500])