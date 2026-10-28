import glob

from babeldoc.format.pdf import parse_only

src = glob.glob("data/users/translation/**/*aven*.pdf", recursive=True)
print("pdf:", src[0], flush=True)
doc = parse_only.parse_with_new_parser_to_legacy_ir(src[0])
print("IL OK", flush=True)
pages = doc.page if hasattr(doc, "page") else []
print("pages:", len(pages), flush=True)
if pages:
    paras = getattr(pages[0], "paragraph", None) or []
    print("page0 paragraphs:", len(paras), flush=True)
    kinds = {}
    for pp in paras:
        for c in getattr(pp, "composition", None) or []:
            kinds[type(c).__name__] = kinds.get(type(c).__name__, 0) + 1
    print("composition kinds:", kinds, flush=True)
