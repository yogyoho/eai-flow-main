"""Generate realistic EN/FR test documents for the translation pipeline."""

import os

from docx import Document

OUT_DIR = r"D:\eai\eai-flow-main\backend\tlt-testdocs"
os.makedirs(OUT_DIR, exist_ok=True)


def add_table(doc, rows):
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            t.rows[r].cells[c].text = val


# ── 1. Supply Agreement ──
doc = Document()
doc.add_heading("Supply Agreement", level=1)
doc.add_paragraph("Contract No. SA-2025-0412")
doc.add_heading("1. Parties", level=2)
doc.add_paragraph(
    'This Supply Agreement (the "Agreement") is entered into by and between:\n'
    "Seller: Anglesey Mining plc, registered in Wales (Company No. 03520862);\n"
    "Buyer: Sino-Foreign JV Iron Ore Co. Ltd, registered in the PRC (USCC: 91110000MA01ABC123)."
)
doc.add_heading("2. Scope of Supply", level=2)
doc.add_paragraph(
    "The Seller agrees to supply, and the Buyer agrees to purchase, iron ore concentrate "
    "in accordance with the specifications set out in Schedule A. The total Contract "
    "Quantity shall be 120,000 dry metric tonnes (DMT) plus or minus 5%, delivered in "
    "monthly shipments of not less than 10,000 DMT each."
)
doc.add_heading("3. Quality Specifications", level=2)
doc.add_paragraph("The iron ore concentrate shall conform to the following specifications:")
add_table(doc, [
    ["Parameter", "Specification", "Method"],
    ["Fe content", "\u2265 63.5%", "ISO 3082"],
    ["Moisture", "\u2264 8.0%", "ISO 3087"],
    ["Phosphorus", "\u2264 0.06%", "ISO 4695"],
    ["Size distribution", "-10mm +0.15mm", "ISO 2591"],
])
doc.add_heading("4. Price and Payment", level=2)
doc.add_paragraph(
    "The Base Price shall be USD 128.50 per dry metric tonne (DMT), subject to "
    "quarterly adjustment in accordance with the Platts IODEX 62% Fe index. Payment "
    "shall be made by irrevocable Letter of Credit within 30 days of Bill of Lading date."
)
doc.add_heading("5. Force Majeure", level=2)
doc.add_paragraph(
    "Neither party shall be liable for failure to perform its obligations under this "
    "Agreement if such failure results from Force Majeure events including but not "
    "limited to: acts of God, war, strikes, governmental action, or failure of transportation."
)
doc.add_heading("6. Term and Termination", level=2)
doc.add_paragraph(
    "This Agreement shall commence on the Effective Date and continue for a period "
    "of twelve (12) months, unless terminated earlier in accordance with Clause 14. "
    "Either party may terminate with sixty (60) days written notice in the event of "
    "a material breach not cured within thirty (30) days of notification."
)
add_table(doc, [
    ["Item", "Requirement", "Reference"],
    ["Quality dispute window", "30 days from arrival", "Clause 8.2"],
    ["Demurrage rate", "USD 8,000/day pro rata", "Clause 9.1"],
    ["Force Majeure notice", "7 days written", "Clause 12.3"],
])
doc.save(os.path.join(OUT_DIR, "Supply Agreement SA-2025-0412.docx"))

# ── 2. Safety Policy ──
doc = Document()
doc.add_heading("Safety Management Policy", level=1)
doc.add_paragraph("Document No. HSE-POL-001 | Rev. 3.0 | Effective Date: 2025-01-01")
doc.add_heading("1. Purpose", level=2)
doc.add_paragraph(
    "This policy establishes the minimum safety management requirements for all "
    "personnel, contractors, and visitors at the Iron Ore Concentration Plant."
)
doc.add_heading("2. Scope", level=2)
doc.add_paragraph(
    "This policy applies to all areas of the Concentration Plant including crushing "
    "and screening areas, grinding mills, flotation circuits, thickener and tailings "
    "facilities, and associated conveyor systems."
)
doc.add_heading("3. Personal Protective Equipment", level=2)
doc.add_paragraph(
    "The following minimum PPE requirements apply to all personnel entering "
    "operational areas:\n"
    "\u2022 Safety helmet (EN 397) \u2014 mandatory at all times\n"
    "\u2022 Safety boots with steel toe cap (EN ISO 20345)\n"
    "\u2022 High-visibility vest (EN ISO 20471 Class 2)\n"
    "\u2022 Safety glasses (EN 166) \u2014 mandatory in designated areas\n"
    "\u2022 Hearing protection (EN 352) \u2014 mandatory above 85 dB(A)"
)
doc.add_heading("4. Permit to Work System", level=2)
doc.add_paragraph(
    "All non-routine work including hot work, confined space entry, working at "
    "height, and electrical isolation shall require a valid Permit to Work (PTW) "
    "issued by the Shift Supervisor and countersigned by the HSE Manager."
)
doc.add_heading("5. Emergency Response", level=2)
doc.add_paragraph(
    "Emergency assembly points are located at the main gate (Assembly Point A) "
    "and the workshop yard (Assembly Point B). All personnel must be familiar with "
    "the evacuation routes displayed at each workstation."
)
doc.add_heading("6. Incident Reporting", level=2)
doc.add_paragraph(
    "All incidents, near-misses, and unsafe conditions must be reported to the "
    "Shift Supervisor within 24 hours using the standard incident reporting form "
    "(HSE-FRM-003). Serious incidents must be reported immediately by phone."
)
add_table(doc, [
    ["Incident Category", "Report Deadline", "Investigation Level"],
    ["Fatality / Lost Time", "Immediate", "Full formal investigation"],
    ["Recordable injury", "Within 4 hours", "Supervisor + HSE review"],
    ["Near-miss", "Within 24 hours", "Supervisor assessment"],
    ["Property damage > USD 10k", "Within 24 hours", "Department manager review"],
])
doc.save(os.path.join(OUT_DIR, "HSE Safety Policy EN Rev3.docx"))

# ── 3. Financial Report ──
doc = Document()
doc.add_heading("Quarterly Financial Report \u2014 Q3 2025", level=1)
doc.add_paragraph("Sino-Foreign JV Iron Ore Co. Ltd | Unaudited | Currency: USD")
doc.add_heading("Executive Summary", level=2)
doc.add_paragraph(
    "Total revenue for Q3 2025 reached USD 15,820,000, representing a 12.4% "
    "increase over Q2 2025. The increase was primarily driven by higher iron ore "
    "concentrate prices and a 3.2% improvement in production volume."
)
doc.add_heading("Revenue Breakdown", level=2)
add_table(doc, [
    ["Revenue Stream", "Q3 2025 (USD)", "Q2 2025 (USD)", "Change %"],
    ["Iron ore concentrate sales", "14,200,000", "12,650,000", "+12.3%"],
    ["By-product credits", "1,120,000", "1,420,000", "-21.1%"],
    ["Freight & logistics", "500,000", "380,000", "+31.6%"],
    ["Total Revenue", "15,820,000", "14,450,000", "+9.5%"],
])
doc.add_heading("Cost of Production", level=2)
doc.add_paragraph(
    "Total cost of production for Q3 2025 was USD 10,240,000, resulting in a "
    "gross profit margin of 35.3% (Q2: 32.1%). The improvement reflects lower "
    "diesel consumption following the mill liner replacement completed in August."
)
doc.add_heading("Capital Expenditure", level=2)
doc.add_paragraph(
    "Capital expenditure for Q3 totalled USD 2,800,000, primarily for the "
    "tailings dam Phase III expansion (USD 1,900,000) and the flotation cell "
    "automation upgrade (USD 900,000)."
)
doc.add_heading("Key Ratios", level=2)
add_table(doc, [
    ["Ratio", "Q3 2025", "Q2 2025", "Industry Avg"],
    ["EBITDA margin", "28.4%", "25.6%", "24.8%"],
    ["Current ratio", "1.82", "1.65", "1.50"],
    ["Debt-to-equity", "0.45", "0.48", "0.62"],
    ["ROE (annualised)", "18.2%", "16.8%", "15.4%"],
])
doc.save(os.path.join(OUT_DIR, "Q3 2025 Financial Report.docx"))

# ── 4. French Supply Contract ──
doc = Document()
doc.add_heading("Contrat de Fourniture \u2014 Extrait", level=1)
doc.add_paragraph("Contrat No. CF-2025-0089")
doc.add_heading("Article 1 \u2014 Objet du Contrat", level=2)
doc.add_paragraph(
    "Le pr\u00e9sent Contrat de Fourniture est conclu entre le Vendeur et l'Acheteur "
    "pour la livraison de concentr\u00e9 de fer conform\u00e9ment aux sp\u00e9cifications "
    "d\u00e9finies \u00e0 l'Annexe A. La quantit\u00e9 contractuelle totale est de "
    "85 000 tonnes m\u00e9triques s\u00e8ches (TMS) \u00b15%."
)
doc.add_heading("Article 2 \u2014 Prix et Paiement", level=2)
doc.add_paragraph(
    "Le Prix de Base est fix\u00e9 \u00e0 135,20 USD par tonne m\u00e9trique s\u00e8che (TMS), "
    "sujet \u00e0 ajustement trimestriel selon l'indice Platts IODEX 62% Fe. "
    "Le paiement sera effectu\u00e9 par lettre de cr\u00e9dit irr\u00e9vocable dans les "
    "30 jours suivant la date du Connaissement."
)
doc.add_heading("Article 3 \u2014 Force Majeure", level=2)
doc.add_paragraph(
    "Aucune des Parties ne sera responsable de l'inex\u00e9cution de ses obligations "
    "si cette inex\u00e9cution r\u00e9sulte d'un cas de Force Majeure, y compris mais "
    "sans s'y limiter : catastrophes naturelles, guerres, gr\u00e8ves, mesures "
    "gouvernementales ou d\u00e9faillance des transports."
)
doc.add_heading("Article 4 \u2014 Contr\u00f4le Qualit\u00e9", level=2)
doc.add_paragraph(
    "Le concentr\u00e9 de fer devra \u00eatre conforme aux sp\u00e9cifications suivantes :\n"
    "\u2022 Teneur en fer \u2265 63,5% (ISO 3082)\n"
    "\u2022 Humidit\u00e9 \u2264 8,0% (ISO 3087)\n"
    "\u2022 Phosphore \u2264 0,06% (ISO 4695)\n"
    "\u2022 Granulom\u00e9trie -10mm +0,15mm (ISO 2591)"
)
doc.save(os.path.join(OUT_DIR, "Contrat de Fourniture CF-2025-0089.docx"))

print("Test docs generated:")
for f in sorted(os.listdir(OUT_DIR)):
    sz = os.path.getsize(os.path.join(OUT_DIR, f))
    print(f"  {f} ({sz // 1024}KB)")
