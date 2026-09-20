#!/usr/bin/env python3
import json
from pathlib import Path
from pypdf import PdfReader

PDF = Path("/Users/quakehunter/Documents/RCN Agent /data/Project info/COSZO Project DataMSRI.pdf")
CACHED = Path("/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo/pages.json")
OUT = Path("/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_products/extraction_b.jsonl")
EVIDENCE = Path("/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_products/b")

MOST = "Products Most Closely Related to the Proposed Project"
OTHER = "Other Significant Products, Whether or Not Related to the Proposed Project"

records = [
    {
        "citation": "Labrado AL, Brunner B, Bernasconi SM, Peckmann J. Formation of Large Native Sulfur Deposits Does Not Require Molecular Oxygen. Front Microbiol. 2019;10:24. PubMed Central PMCID: PMC6355691.",
        "doi_as_cited": [], "pdf_pages_1_based": [40], "printed_packet_pages": [132],
        "section": OTHER, "owner": "Amanda Labrado", "item_number": 1,
        "notes": "The 'Products Most Closely Related' heading is immediately followed by the 'Other Significant Products' heading, so this item belongs to the latter section. No DOI is printed; PMCID is retained in the citation."
    },
    {
        "citation": "Stelmach KB, Neveu M, Vick-Majors TJ, Mickol RL, Chou L, Webster KD, Tilley M, Zacchei F, Escudero C, Flores Martinez CL, Labrado A, Fernández EJG. Secondary Electrons as an Energy Source for Life. Astrobiology. 2018 Jan;18(1):73-85. PubMed PMID: 29314901.",
        "doi_as_cited": [], "pdf_pages_1_based": [40], "printed_packet_pages": [132],
        "section": OTHER, "owner": "Amanda Labrado", "item_number": 2,
        "notes": "No DOI is printed; PMID is retained in the citation."
    },
    {
        "citation": "Sasagawa G, Zumberge M. A Self-Calibrating Pressure Recorder for Detecting Seafloor Height Change. IEEE Journal of Oceanic Engineering. 2013 July; 38(3):447-454. Available from: http://ieeexplore.ieee.org/document/6423803/ DOI: 10.1109/JOE.2012.2233312",
        "doi_as_cited": ["10.1109/JOE.2012.2233312"], "pdf_pages_1_based": [42], "printed_packet_pages": [137],
        "section": MOST, "owner": "Mark Zumberge", "item_number": 3,
        "notes": "Page begins with item 3. The section heading and items 1-2 are absent because intervening packet pages are omitted from the supplied PDF; classification follows the immediate transition to 'Other Significant Products' after item 5."
    },
    {
        "citation": "Zumberge M, Xie S, Wyatt F, Steckler M, Li G, Hatfield W, Elliott D, Dixon T, Bridgeman J, Chamberlain E, Allison M, Törnqvist T. Novel Integration of Geodetic and Geologic Methods for High-Resolution Monitoring of Subsidence in the Mississippi Delta. Journal of Geophysical Research: Earth Surface. 2022 September 03; 127(9):-. Available from: https://onlinelibrary.wiley.com/doi/10.1029/2022JF006718 DOI: 10.1029/2022JF006718",
        "doi_as_cited": ["10.1029/2022JF006718"], "pdf_pages_1_based": [42], "printed_packet_pages": [137],
        "section": MOST, "owner": "Mark Zumberge", "item_number": 4,
        "notes": "The section heading and items 1-2 are on omitted packet pages; section classification is determined from the visible sequence ending immediately before the 'Other Significant Products' heading."
    },
    {
        "citation": "Xie S, Chen J, Dixon T, Weisberg R, Zumberge M. Offshore Sea Levels Measured With an Anchored Spar-Buoy System Using GPS Interferometric Reflectometry. Journal of Geophysical Research: Oceans. 2021 November 08; 126(11):-. Available from: https://onlinelibrary.wiley.com/doi/10.1029/2021JC017734 DOI: 10.1029/2021JC017734",
        "doi_as_cited": ["10.1029/2021JC017734"], "pdf_pages_1_based": [42], "printed_packet_pages": [137],
        "section": MOST, "owner": "Mark Zumberge", "item_number": 5,
        "notes": "The section heading and items 1-2 are on omitted packet pages; the next visible heading is 'Other Significant Products'."
    },
    {
        "citation": "DeWolf S, Wyatt FK, Zumberge MA, Hatfield W. Improved vertical optical fiber borehole strainmeter design for measuring Earth strain. Rev Sci Instrum. 2015 Nov;86(11):114502. PubMed PMID: 26628152.",
        "doi_as_cited": [], "pdf_pages_1_based": [42], "printed_packet_pages": [137],
        "section": OTHER, "owner": "Mark Zumberge", "item_number": 1,
        "notes": "No DOI is printed; PMID is retained in the citation."
    },
    {
        "citation": "Zumberge M, Berger J, Hatfield W, Wielandt E. A Three-Component Borehole Optical Seismic and Geodetic Sensor. Bulletin of the Seismological Society of America. 2018 May 29; 108(4):2022-2031. Available from: https://pubs.geoscienceworld.org/ssa/bssa/article/108/4/2022/531341/A-ThreeComponent-Borehole-Optical-Seismic-and DOI: 10.1785/0120180045",
        "doi_as_cited": ["10.1785/0120180045"], "pdf_pages_1_based": [42], "printed_packet_pages": [137],
        "section": OTHER, "owner": "Mark Zumberge", "item_number": 2,
        "notes": "Citation occurs again as item 5 in the same section."
    },
    {
        "citation": "Hatfield W, Elliott D, Wyatt F, Xie S, Zumberge M. Results From a Decade of Optical Fiber Strainmeters at Piñon Flat Observatory. Earth and Space Science. 2022 September 07; 9(9):-. Available from: https://onlinelibrary.wiley.com/doi/10.1029/2022EA002381 DOI: 10.1029/2022EA002381",
        "doi_as_cited": ["10.1029/2022EA002381"], "pdf_pages_1_based": [42], "printed_packet_pages": [137],
        "section": OTHER, "owner": "Mark Zumberge", "item_number": 3,
        "notes": "Complete citation is visible on this page."
    },
    {
        "citation": "Chien C, Jenkins W, Gerstoft P, Zumberge M, Mellors R. Automatic classification with an autoencoder of seismic signals on a distributed acoustic sensing cable. Computers and Geotechnics. 2023 March; 155:105223-. Available from: https://linkinghub.elsevier.com/retrieve/pii/S0266352X22005602 DOI: 10.1016/j.compgeo.2022.105223",
        "doi_as_cited": ["10.1016/j.compgeo.2022.105223"], "pdf_pages_1_based": [42], "printed_packet_pages": [137],
        "section": OTHER, "owner": "Mark Zumberge", "item_number": 4,
        "notes": "Complete citation is visible on this page."
    },
    {
        "citation": "Zumberge M, Berger J, Hatfield W, Wielandt E. A Three-Component Borehole Optical Seismic and Geodetic Sensor. Bulletin of the Seismological Society of America. 2018 May 29; 108(4):2022-2031. Available from: https://pubs.geoscienceworld.org/ssa/bssa/article/108/4/2022/531341/A-ThreeComponent-Borehole-Optical-Seismic-and DOI: 10.1785/0120180045",
        "doi_as_cited": ["10.1785/0120180045"], "pdf_pages_1_based": [42], "printed_packet_pages": [137],
        "section": OTHER, "owner": "Mark Zumberge", "item_number": 5,
        "notes": "Exact duplicate occurrence of item 2 in the same section; retained because every product occurrence was requested."
    },
    {
        "citation": "Sasagawa G, Zumberge M, Cook M. Drift Corrected Seafloor Pressure Observations of Vertical Deformation at Axial Seamount 2018-2021. Earth and Space Science. 2023 February 08; 10(2):-. Available from: https://onlinelibrary.wiley.com/doi/10.1029/2022EA002434 DOI: 10.1029/2022EA002434",
        "doi_as_cited": ["10.1029/2022EA002434"], "pdf_pages_1_based": [44], "printed_packet_pages": [139],
        "section": MOST, "owner": "Glenn Sasagawa", "item_number": 1,
        "notes": "Citation occurs again as item 3, which spans physical pages 44-45."
    },
    {
        "citation": "Cook M, Frederickson E, Roland E, Sasagawa G, Schmidt D, Wilcock W, Zumberge M. Calibrated absolute seafloor pressure measurements for geodesy in Cascadia. [Preprint]. 2023. DOI: 10.22541/essoar.167525205.55700045/v1",
        "doi_as_cited": ["10.22541/essoar.167525205.55700045/v1"], "pdf_pages_1_based": [44], "printed_packet_pages": [139],
        "section": MOST, "owner": "Glenn Sasagawa", "item_number": 2,
        "notes": "Preprint citation occurs again as item 5 on physical page 45."
    },
    {
        "citation": "Sasagawa G, Zumberge M, Cook M. Drift Corrected Seafloor Pressure Observations of Vertical Deformation at Axial Seamount 2018-2021. Earth and Space Science. 2023 February 08; 10(2):-. Available from: https://onlinelibrary.wiley.com/doi/10.1029/2022EA002434 DOI: 10.1029/2022EA002434",
        "doi_as_cited": ["10.1029/2022EA002434"], "pdf_pages_1_based": [44, 45], "printed_packet_pages": [139, 140],
        "section": MOST, "owner": "Glenn Sasagawa", "item_number": 3,
        "notes": "Citation begins on physical page 44 and continues on physical page 45. Exact duplicate occurrence of item 1; retained because every product occurrence was requested."
    },
    {
        "citation": "Sasagawa G, Zumberge M, Cook M. Laboratory Simulation and Measurement of Instrument Drift in Quartz-Resonant Pressure Gauges. IEEE Access. 2018; 6:57334-57340. Available from: https://ieeexplore.ieee.org/document/8478790/ DOI: 10.1109/ACCESS.2018.2873479",
        "doi_as_cited": ["10.1109/ACCESS.2018.2873479"], "pdf_pages_1_based": [45], "printed_packet_pages": [140],
        "section": MOST, "owner": "Glenn Sasagawa", "item_number": 4,
        "notes": "Complete citation is visible on this page."
    },
    {
        "citation": "Cook M, Frederickson E, Roland E, Sasagawa G, Schmidt D, Wilcock W, Zumberge M. Calibrated absolute seafloor pressure measurements for geodesy in Cascadia. [Preprint]. 2023. DOI: 10.22541/essoar.167525205.55700045/v1",
        "doi_as_cited": ["10.22541/essoar.167525205.55700045/v1"], "pdf_pages_1_based": [45], "printed_packet_pages": [140],
        "section": MOST, "owner": "Glenn Sasagawa", "item_number": 5,
        "notes": "Exact duplicate occurrence of item 2; retained because every product occurrence was requested. The following 'Other Significant Products' section is empty."
    },
]

EVIDENCE.mkdir(parents=True, exist_ok=True)
reader = PdfReader(str(PDF))
layout = []
for page_no in range(40, 46):
    text = reader.pages[page_no - 1].extract_text(extraction_mode="layout")
    layout.append({"pdf_page_1_based": page_no, "text": text})
with open(EVIDENCE / "pypdf_layout_pages_40_45.json", "w", encoding="utf-8") as f:
    json.dump(layout, f, ensure_ascii=False, indent=2)
with open(CACHED, encoding="utf-8") as f:
    cached_pages = json.load(f)
cached_subset = [
    {"pdf_page_1_based": page_no, "text": cached_pages[page_no - 1]}
    for page_no in range(40, 46)
]
with open(EVIDENCE / "cached_pages_40_45.json", "w", encoding="utf-8") as f:
    json.dump(cached_subset, f, ensure_ascii=False, indent=2)
with open(OUT, "w", encoding="utf-8") as f:
    for record in records:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
print(json.dumps({"records": len(records), "output": str(OUT), "layout_pages": len(layout), "cached_pages": len(cached_subset)}))
