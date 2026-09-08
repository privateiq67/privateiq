# Quarantined parsers

`parser_coord_ocr.py` is the pre-MVP coordinate/OCR heuristic. It was incorrect:
mis-associated labels with numbers, conflated net assets with total assets, ignored
year columns, and invented sparse flat keys. Kept only for historical reference.
Do not import from production code.
