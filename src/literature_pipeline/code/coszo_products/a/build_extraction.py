import json
from pathlib import Path

OUT = Path("/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_products/extraction_a.jsonl")

RELATED = "Products Most Closely Related to the Proposed Project"
OTHER = "Other Significant Products, Whether or Not Related to the Proposed Project"


def rec(citation, dois, pdf_page, packet_page, section, owner, item_number=None, notes=None):
    return {
        "citation": citation,
        "doi_as_cited": dois,
        "pdf_pages_1_based": [pdf_page],
        "printed_packet_pages": [packet_page],
        "section": section,
        "owner": owner,
        "item_number": item_number,
        "notes": notes,
    }


records = []

# Physical PDF page 34 / printed packet page 116 — Harold Tobin.
owner_note = (
    "Owner inferred as Harold Tobin from the repeated author identity and the packet/personnel "
    "sequence; the owner name is not printed on this page. Entry is unnumbered as printed."
)
for citation, dois in [
    ("Tobin, H., Saffer, D., Hirose, T., and Castillo, D., 2022, Direct constraints on in situ stress state from deep drilling into the Nankai subduction zone, Geology, doi:https://doi.org/10.1130/G49639.1.", ["10.1130/G49639.1"]),
    ("Tobin, H., Kimura, G., and Kodaira, S., 2019, Processes governing giant subduction earthquakes: IODP drilling to sample and instrument subduction zone megathrusts, Oceanography, 32 (1), p. 80-93, https://doi.org/10.5670/oceanog.2019.125.", ["10.5670/oceanog.2019.125"]),
    ("Jeppson, T., Tobin, H., and Hashimoto, Y., 2018, Laboratory measurements quantifying elastic properties of accretionary wedge sediments: Implications for slip to the trench during the 2011 Mw 9.0 Tohoku-Oki earthquake, Geosphere, 14 (4): 1411-1424.", []),
    ("Lotto, G., Dunham, E., Jeppson, T., and Tobin, H., 2017, The effect of compliant prisms on subduction zone earthquakes and tsunamis, Earth and Planetary Science Letters, v. 458, p. 213-222. doi: 10.1016/j.epsl.2016.10.050.", ["10.1016/j.epsl.2016.10.050"]),
    ("Kinoshita, M. and Tobin, H., 2013, Interseismic stress accumulation at the locked zone of Nankai Trough seismogenic fault off Kii Peninsula, Tectonophysics, v. 600, p. 153-164, http://dx.doi.org/10.1016/j.tecto.2013.03.015.", ["10.1016/j.tecto.2013.03.015"]),
]:
    records.append(rec(citation, dois, 34, 116, RELATED, "Harold Tobin", notes=owner_note))

for citation, dois in [
    ("Venkateswara, K., Paros, J., Bodin, P., Wilcock, W., & Tobin, H. J., 2021, Rotational Seismology with a Quartz Rotation Sensor. Seismological Research Letters. https://doi.org/10.1785/0220210171.", ["10.1785/0220210171"]),
    ("Walton, M., Staisch, L., Dura, T., Pearl, J., Sherrod, B., Gomberg, J., Engelhart, S., Tréhu, A., Watt, J., Perkins, J., Witter, R., Bartlow, N., Goldfinger, C., Kelsey, H., Morey, A., Sahakian, V., Tobin, H., Wang, K., Wells, R., and Wirth, E., 2021, Toward an integrative geological and geophysical view of Cascadia subduction zone earthquakes, Annual Reviews of Earth and Planetary Sciences, 49:367–98.", []),
    ("Jeppson, T., and Tobin, H., 2020, Acoustic evidence for a broad, hydraulically active damage zone surrounding the Alpine Fault, New Zealand, Tectonophysics, 781, 228410. Doi: https://doi.org/10.1016/j.tecto.2020.228410.", ["10.1016/j.tecto.2020.228410"]),
    ("Tobin, H., Henry, P., Vannucchi, P., and Screaton, E., 2014. Subduction Zones: Structure and Deformation History, in Stein, R., Blackman, D., Inagaki, F., and Larsen, H., eds., Earth and Life Processes Discovered from Subseafloor Environments - A Decade of Science Achieved by the Integrated Ocean Drilling Program (IODP), Elsevier, p. 599-640. doi:10.1016/B978-0-444-62617-2.00020-7.", ["10.1016/B978-0-444-62617-2.00020-7"]),
    ("Saffer, D. and Tobin, H., 2011, Hydrogeology and Mechanics of Subduction Zone Forearcs: Fluid Flow and Pore Pressure, Annu. Rev. Earth Planet. Sci., v. 39, p. 157-186.", []),
]:
    records.append(rec(citation, dois, 34, 116, OTHER, "Harold Tobin", notes=owner_note))

# Physical PDF page 35 / printed packet page 119 — Deborah Kelley.
owner_note = (
    "Owner inferred as Deborah Kelley from the repeated author identity and the packet/personnel "
    "sequence; the owner name is not printed on this page. Entry is unnumbered as printed."
)
for citation, dois in [
    ("Philip, B.T., E.A. Solomon, D.S. Kelley, A.M. Tréhu, T.L. Whorley, E. Roland, M. Tominaga, and R.W. Collier, 2023. Fluid sources and overpressures within the central Cascadia Subduction Zone revealed by a warm, high-flux seafloor seep. Science Advances, 9, doi: 10.1126/sciadv.add6688.", ["10.1126/sciadv.add6688"]),
    ("Früh-Green, G.L., D.S. Kelley, M.D. Lilley, M. Cannat, V. Chavagnac, and J.A. Baross, 2022. Diversity of magmatism, hydrothermal processes and microbial interactions at mid-ocean ridges. Nature Reviews Earth and Environment, 3, 852-871, doi.org/10.1038/s43017-022-00364-y.", ["10.1038/s43017-022-00364-y"]),
    ("Kelley, D.S., 2017. Volcans’ Rule Beneath the Sea. Nature GeoScience, 10, 251-253 https://doi.org/10.1038/ngeo2929.", ["10.1038/ngeo2929"]),
    ("Philip, B.T., A.R. Denny, E.A. Solomon, and D.S. Kelley, 2016. Time series measurements of bubble plume variability and water column methane distribution above Southern Hydrate Ridge, Oregon, Geochemistry, Geophysics, Geosystems. doi: 10.1002/2016GC006250.", ["10.1002/2016GC006250"]),
    ("Karson, J.A., D.S. Kelley, D.J. Fornari, M.R. Perfit, and T.M. Shank, 2016 Discovering the Deep, A Photographic Atlas of the Seafloor and Oceanic Crust. Cambridge University Press, ISBN: 9780521857185, 527 pp.http://www.cambridge.org/us/academic/subjects/earth-and-environmental-science/oceanography-and-marine-science/discovering-deep-photographic-atlas-seafloor-and-ocean-crust. https://doi.org/10.1017/CBO9781139050524.", ["10.1017/CBO9781139050524"]),
]:
    records.append(rec(citation, dois, 35, 119, RELATED, "Deborah Kelley", notes=owner_note))

for citation, dois, extra_note in [
    ("Kelley, D.S., M. Vardaro, Center for Environmental Visualization, 2011-present Interactiveoceans website https://interactiveoceans.washington.edu/.", [], "Website product rather than a journal citation; retained because it is printed as a product."),
    ("Riedel, M., K.M.M. Rohr, G.D. Spence, D. Kelley, J. Delaney, L. Lapham, J.W. Pohlman, R.D. Hyndman, and E.C. Willoughby, 2020. Focused fluid flow along the Nootka Fault Zone and continental slope, Explorer-Juan de Fuca plate boundary. Geochemistry, Geophysics, Geosystems, doi/full/10.1029/2020GC009095.", ["10.1029/2020GC009095"], None),
    ("Smith, L.M., J.A. Barth, D.S. Kelley, A. Plueddemann, I. Rodero, G. Ulses,M. Vardaro, and R. Weller, 2018. The Ocean Observatories Initiative. Oceanography, 31, 16-35, doi.org/10.5670/oceanog.2018.105.", ["10.5670/oceanog.2018.105"], None),
    ("Kelley, D.S. J.R. Delaney, S.K. Juniper, 2014. Establishing a new era of submarine volcanic observatories: Cabling Axial Seamount and the Endeavour Segment of the Juan de Fuca Ridge. Marine Geology 50th Anniversary Special Volume. 352, 426-450, doi.org/10.1016/j.margeo.2014.03.010.", ["10.1016/j.margeo.2014.03.010"], None),
    ("Martin, W., J.A. Baross, D.S. Kelley, and M.J. Russel, 2008. Hydrothermal vents and the origin of life. Nature Reviews Microbiology, 6, 805-814, doi:10.1038/nrmicro1991.", ["10.1038/nrmicro1991"], None),
]:
    note = owner_note if extra_note is None else f"{owner_note} {extra_note}"
    records.append(rec(citation, dois, 35, 119, OTHER, "Deborah Kelley", notes=note))

# Physical PDF page 36 / printed packet page 122 — David Schmidt.
records.append(rec(
    "2016; 87(4):930-943. issn: 1938-2057",
    [], 36, 122, RELATED, "David Schmidt", None,
    "Only this continuation fragment is visible at the top of physical page 36. It is the tail of a Products Most Closely Related citation begun on an omitted prior packet page; its item number, authors, title, and journal are not visible. Owner is confirmed by the page certification."
))
for number, citation in enumerate([
    "Schmidt D, Gao H. Source parameters and time‐dependent slip distributions of slow slip events on the Cascadia subduction zone from 1998 to 2008. Journal of Geophysical Research: Solid Earth. 2010; 115(B4). issn: 0148-0227",
    "Krogstad R, Schmidt D, Weldon R, Burgette R. Constraints on accumulated strain near the ETS zone along Cascadia. Earth and Planetary Science Letters. 2016; 439:109-116. issn: 0012-821X",
    "Hall K, Schmidt D, Houston H. Peak tremor rates lead peak slip rates during propagation of two large slow earthquakes in Cascadia. Geochemistry, Geophysics, Geosystems. 2019; 20(11):4665-4675. issn: 1525-2027",
    "Gao H, Schmidt D, Weldon R. Scaling relationships of source parameters for slow slip events. Bulletin of the Seismological Society of America. 2012; 102(1):352-360. issn: 1943-3573",
    "Newton T, Weldon R, Miller I, Schmidt D, Mauger G, Morgan H, Grossman E. An Assessment of Vertical Land Movement to Support Coastal Hazards Planning in Washington State. Water. 2021; 13(3):281. issn: 2073-4441",
], start=1):
    records.append(rec(citation, [], 36, 122, OTHER, "David Schmidt", str(number), "Owner confirmed by the page certification."))

# Physical PDF page 37 / printed packet page 124 — Michael Harrington.
owner_note = (
    "Owner inferred as Michael Harrington from his presence in all three citations, the engineering "
    "activities listed on the page, and the packet/personnel sequence; the owner name is not printed on this page."
)
for number, citation, dois in [
    ("1", "Wilcock, W. S. D., D. A. Manalang, M. J. Harrington, E. K. Fredrickson, G. Cram, J. Tilley, J. Burnett, D. Martin, T. Kobayashi and J. M. Paros, New approaches to in situ calibration of seafloor geodetic measurements, OCEANS 2018 MTS/IEEE Monterey Kobe, Japan, in press, 2018.", []),
    ("2", "Wilcock, W. S. D., D. A. Schmidt, J. E. Vidale, M. J. Harrington, P. Bodin, G. S. Cram, J. R. Delaney, F. I. Gonzalez, D. S. Kelley, R. J. LeVeque, D. A. Manalang, C. McGuire, E. C. Roland, M. W. Stoermer, J. W. Tilley, C. J. Vogl, Designing an offshore geophysical network in the Pacific Northwest for earthquake and tsunami early warning and hazard research, OCEANS 2016 MTS/IEEE Monterey, Monterey, CA, 2016, pp. 1-8. doi: 10.1109/OCEANS.2016.7761291, 2016", ["10.1109/OCEANS.2016.7761291"]),
    ("3", "Yinger, P., Tennant P., Harkins G., McGuire C., Harrington M., Mulvihill M., Commissioning of a System that Terminates on the Seafloor. Oceans 2013", []),
]:
    records.append(rec(citation, dois, 37, 124, RELATED, "Michael Harrington", number, owner_note))

# Physical PDF page 38 / printed packet page 127 — Dana Manalang.
for number, citation, dois, extra_note in [
    ("4", "Manalang D, Delaney J. Axial seamount - restless, wired and occupied: A conceptual overview of resident AUV operations and technologies. 2016/09/01. 1-7p. DOI: 10.1109/OCEANS.2016.7761305", ["10.1109/OCEANS.2016.7761305"], "Complete item 4 is visible, although items 1–3 occur on an omitted prior packet page."),
    ("5", "Marcon Y, Kelley D, Thornton B, Manalang D, Bohrmann G. Variability of Natural Methane Bubble Release at Southern Hydrate Ridge. Geochemistry, Geophysics, Geosystems. 2021 October 05; 22(10):-. Available from: https://onlinelibrary.wiley.com/doi/10.1029/2021GC009894 DOI: 10.1029/2021GC009894", ["10.1029/2021GC009894"], "Complete item 5 is visible, although items 1–3 occur on an omitted prior packet page; the same DOI is printed in both the URL and DOI field."),
]:
    records.append(rec(citation, dois, 38, 127, RELATED, "Dana Manalang", number, f"Owner confirmed by the page certification. {extra_note}"))

for number, citation, dois, extra_note in [
    ("1", "Delaney JR, Manalang DA. \"Capturing\" Transient Oceanographic Phenomena With \"Resident\" AUVs. MTS Journal. 2020 September; 54(5):8.", [], None),
    ("2", "Song Z, Marburg A, Manalang D. Resident Seabed Robotic Systems: A Review. MTS Journal. 2020 September; 54(5):21.", [], None),
    ("3", "Manalang D, Delaney J, Marburg A, Nawaz A. Resident AUV Workshop 2018: Applications and a Path Forward. 2018/11/01. 1-6p. DOI: 10.1109/AUV.2018.8729720", ["10.1109/AUV.2018.8729720"], None),
    ("4", "Manalang D, Daly K, Wilcock W. Persistent Mobile Ocean Observing: Marine Vehicle Highways. Marine Technology Society Journal. 2021 May 01; 55(3):86-87. Available from: https://www.ingentaconnect.com/content/10.4031/MTSJ.55.3.29 DOI: 10.4031/MTSJ.55.3.29", ["10.4031/MTSJ.55.3.29"], "The same DOI is printed in both the URL and DOI field."),
    ("5", "Manalang D, Waters B, Smith C, LaMothe P, Carlson M, Yan K. Adaptive Wireless Power for Subsea Vehicles. Marine Technology Society Journal. 2022 October 14; 56(5):36-44. Available from: https://www.ingentaconnect.com/content/10.4031/MTSJ.56.5.9 DOI: 10.4031/MTSJ.56.5.9", ["10.4031/MTSJ.56.5.9"], "The same DOI is printed in both the URL and DOI field."),
]:
    note = "Owner confirmed by the page certification."
    if extra_note:
        note += " " + extra_note
    records.append(rec(citation, dois, 38, 127, OTHER, "Dana Manalang", number, note))

# Physical PDF page 39 / printed packet page 129 — Geoffrey Cram.
owner_note = (
    "Owner inferred as Geoffrey Cram from his presence in all four citations and the packet/personnel "
    "sequence; the owner name is not printed on this page. Entry is unnumbered as printed."
)
for citation, dois in [
    ("Designing an Offshore Geophysical Network in the Pacific Northwest for Earthquake and Tsunami Early Warning and Hazard Research. Wilcock, William S. D ; Schmidt, David A ; Vidale, John E ; Harrington, Michael J ; Bodin, Paul ; Cram, Geoffrey S ; Delaney, John R ; Gonzalez, Frank I ; Kelley, Deborah S ; LeVeque, Randall J ; Manalang, Dana A ; McGuire, Chuck ; Roland, Emily C ; Stoermer, Mark W ; Tilley, James W ; Vogl, Chris. OCEANS 2016 MTS/IEEE Monterey, 2016, p.1-8; IEEE", []),
    ("Developing a Warning System for Inbound Tsunamis from the Cascadia Subduction Zone. LeVeque, Randall J ; Bodin, Paul ; Cram, Geoffrey ; Crowell, Brendan W ; Gonzalez, Frank I ; Harrington, Michael ; Manalang, Dana ; Melgar, Diego ; Schmidt, David A ; Vidale, John E ; Vogl, Christopher J ; Wilcock, William S. D. OCEANS 2018 MTS/IEEE Charleston, 2018, p.1-10; IEEE", []),
    ("New Approaches to In Situ Calibration for Seafloor Geodetic Measurements. Wilcock, William S. D ; Manalang, Dana A ; Harrington, Michael J ; Fredrickson, Erik K ; Cram, Geoff ; Tilley, James ; Burnett, Justin ; Martin, Derek ; Kobayashi, Taro ; Paros, Jerome M. 2018 OCEANS - MTS/IEEE Kobe Techno-Oceans (OTO), 2018, p.1-8; IEEE", []),
    ("Lessons Learned from the United States Ocean Observatories Initiative. Smith LM, Yarincik K, Vaccari L, Kaplan MB, Barth JA, Cram GS, Fram JP, Harrington M, Kawka OE, Kelley DS, Matthias P, Newhall K, Palanza M, Plueddemann AJ, Vardaro MF, White SN and Weller RA, (2019) Front. Mar. Sci. 5:494. doi: 10.3389/fmars.2018.00494", ["10.3389/fmars.2018.00494"]),
]:
    records.append(rec(citation, dois, 39, 129, RELATED, "Geoffrey Cram", notes=owner_note))

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", encoding="utf-8") as handle:
    for record in records:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

print(f"wrote {len(records)} records to {OUT}")
