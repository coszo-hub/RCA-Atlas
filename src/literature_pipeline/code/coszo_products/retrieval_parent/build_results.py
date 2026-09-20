import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path


BASE = Path(__file__).parent
RAW = BASE / "raw"


def clean_crossref_abstract(ref_id: str) -> str:
    path = RAW / f"{ref_id}_crossref_direct.json"
    value = json.loads(path.read_text())["message"]["abstract"]
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    value = re.sub(r"^\s*Abstract\s*", "", value, flags=re.I)
    value = re.sub(r"\s+", " ", value).strip()
    # Preserve the paragraph boundary omitted in the publisher's Crossref deposit.
    if ref_id == "COSZO-REF-164":
        value = value.replace("tools.Marine Vehicle", "tools. Marine Vehicle")
    return value


retrieved_at = datetime.now(timezone.utc).isoformat()

abstracts = {
    "COSZO-REF-156": (
        "Seafloor geodesy is challenging but important for understanding the hazards from earthquakes and tsunamis along subduction zones. "
        "Two methods of seafloor geodesy are presented based on obtaining self-calibrated measurements with resonant quartz crystal technology sensors. "
        "The A-0-A method for calibrating pressure observations utilizes the internal pressure of the instrument housing as a reference pressure to calibrate sensor drift. "
        "An 8-month seafloor test at a depth of 900 m, shows the method has reduced the relative drift between two pressure sensors to <1 mm. "
        "The rotating (or flipping) tiltmeter calibrates the accelerations of the horizontal channels of a tri-axial accelerometer by rotating them into the vertical where the acceleration of gravity is used as a reference acceleration. "
        "Laboratory tests are very promising and deployments are planned on the seafloor and at a geodetic observatory."
    ),
    "COSZO-REF-157": (
        "Every few hundred years, the Cascadia subduction zone off the coast of the Pacific Northwest hosts devastating earthquakes, and there is a growing awareness of the need to be prepared for these events. "
        "An offshore cabled observatory extending the length of the Cascadia subduction zone would enhance the performance of the earthquake and tsunami early warning systems, would enable real time monitoring and predictions of the incoming tsunami, and would contribute substantially to scientific research aimed at mitigating the hazard. "
        "The University of Washington has recently initiated a study to develop a conceptual design for the U.S. portion of an offshore observatory for earthquake and tsunami early warning and research. "
        "This paper presents the motivation for this work and plans for the study."
    ),
    "COSZO-REF-158": (
        "Ocean observatories introduce demanding requirements and a variety of new complexities in the commissioning phase of a program. "
        "For the National Science Foundation's Ocean Observatories Initiative's Regional Scale Nodes (RSN) observatory program, the backbone telecommunication cables were first installed in 2011. "
        "The in-water nodes and shore terminal equipment were successfully installed in 2012, followed by the installation of the in-water secondary infrastructure, later in 2013. "
        "When the commissioning phase occurred, the primary infrastructure was already installed but connections to the secondary infrastructure had yet to be made. "
        "The RSN system test plan mitigates risk with a stepwise verification process maximizing end-to-end post installation testing possibilities. "
        "This paper reviews the test processes required to assure successful optical performance, power distribution, and network integrity after system installation."
    ),
    "COSZO-REF-159": (
        "The Ocean Observatories Initiative Cabled Array has provided an unprecedented real-time window on the dynamics of Axial Volcano since fall 2014. "
        "In April and May of 2015, for the first time, researchers on shore were able to monitor an eruption event as it happened. "
        "The seismic, deformation and acoustic signals sent to shore were analyzed to determine the precise locations of diking events, followed hours later by acoustic impulses corresponding to lava expulsion from the seafloor. "
        "Although these locations informed follow-up Autonomous Underwater Vehicle (AUV) mapping expeditions which produced high resolution bathymetry, to date, the evolution of an eruptive event and its immediate impact on the surrounding ecosystem have not been observed. "
        "Although the 70,000 km-long mid ocean ridge (MOR) must generate many hundreds of powerful, transient events every year, they have never been characterized as they form. "
        "We envision a Resident AUV with in situ charging and data download capabilities, shore-based mission control, and an array of bottom-mounted acoustic positioning beacons that can concurrently be used as a multi-hop sensor network. "
        "This system will provide unprecedented observing capabilities before, during, and after the next eruption and formation of the highly energetic eruptive (mega) plume. "
        "AUV capabilities will include high-resolution bathymetry, high definition video and still imagery, and 3-D water chemistry and microbial sampling throughout the water column, while the acoustic array will monitor horizontal and vertical deformation."
    ),
    "COSZO-REF-160": clean_crossref_abstract("COSZO-REF-160"),
    "COSZO-REF-161": None,
    "COSZO-REF-162": clean_crossref_abstract("COSZO-REF-162"),
    "COSZO-REF-163": (
        "Long-term, persistent Resident AUV (RAUV) systems, able to be deployed for months to years without manned support vessels, will have a profound impact on our ability to observe temporally and spatially changing phenomena throughout entire volumes of the ocean. "
        "Further, RAUVs may provide a means of remotely interacting with subsea infrastructure, offering tremendous savings on maintenance that would otherwise require manned vessels and ROVs. "
        "During a workshop in May, 2018, 100 participants gathered in Seattle, WA to assess opportunities for RAUVs. Applications evaluated range from observing mid-ocean ridge volcanic eruptions, to intermittent methane seep activity, to arctic ice motion, and eventually to the search for life in off-planet oceans. "
        "In all cases, long-term RAUV deployments will require a system of components for energy management, communications, navigation, as well as self-diagnostics and advanced autonomy functions. "
        "While many of the subsystems necessary for viable residency have been demonstrated individually, it will take time, testing and focused system and reliability engineering before RAUV operations become routine. "
        "As evidenced by the spectrum of industry and academic participants in the workshop, industry-academic partnerships may be a plausible means of accelerating RAUV systems and applications."
    ),
    "COSZO-REF-164": clean_crossref_abstract("COSZO-REF-164"),
    "COSZO-REF-165": clean_crossref_abstract("COSZO-REF-165"),
    "COSZO-REF-166": (
        "Real-time tsunami warning in the nearfield is considerably more difficult than producing warnings for distant events. "
        "Although in some cases strong shaking will provide the only warning, there are several situations in which better early tsunami warning systems could be critical. "
        "We discuss some of the issues that arise, particularly the difficulty of interpreting ocean bottom pressure recordings in the near source region, and make some recommendations for future research and first steps toward a better warning system for the Pacific Northwest."
    ),
    "COSZO-REF-167": (
        "The Ocean Observatories Initiative (OOI) is a United States National Science Foundation-funded major research facility that provides continuous observations of the ocean and seafloor from coastal and open ocean locations in the Atlantic and Pacific. "
        "Multiple cycles of OOI infrastructure deployment, recovery, and refurbishment have occurred since operations began in 2014. "
        "This heterogeneous ocean observing infrastructure with multidisciplinary sampling in important but challenging locations has provided new scientific and engineering insights into the operation of a sustained ocean observing system. "
        "This paper summarizes the challenges, successes, and failures experienced to date and shares recommendations on best practices that will be of benefit to the global ocean observing community."
    ),
}

specs = {
    "COSZO-REF-156": dict(title="New Approaches to In Situ Calibration for Seafloor Geodetic Measurements", doi="10.1109/OCEANSKOBE.2018.8559178", resource_type="conference_paper", abstract_source="https://faculty.washington.edu/wilcock/files/PaperPDFs/Wilcocketal_Oceans18_2018.pdf", metadata="https://api.crossref.org/works/10.1109%2FOCEANSKOBE.2018.8559178", license=None, full_text="https://faculty.washington.edu/wilcock/files/PaperPDFs/Wilcocketal_Oceans18_2018.pdf", note="Exact title, ten authors, 2018 conference, and DOI verified against Crossref; abstract transcribed from the labeled abstract in the University of Washington-hosted paper PDF."),
    "COSZO-REF-157": dict(title="Designing an offshore geophysical network in the Pacific Northwest for earthquake and tsunami early warning and hazard research", doi="10.1109/OCEANS.2016.7761291", resource_type="conference_paper", abstract_source="https://www.researchgate.net/publication/311753878_Designing_an_offshore_geophysical_network_in_the_Pacific_Northwest_for_earthquake_and_tsunami_early_warning_and_hazard_research", metadata="https://api.crossref.org/works/10.1109%2FOCEANS.2016.7761291", license=None, full_text=None, note="Exact title, 16 authors, September 2016 conference, pages 1–8, and DOI verified against Crossref. The full abstract was recovered from the exact scholarly publication record; publisher metadata did not expose abstract text and no verified open full text was found."),
    "COSZO-REF-158": dict(title="Commissioning of a system that terminates on the seafloor", doi="10.23919/OCEANS.2013.6741353", resource_type="conference_paper", abstract_source="https://itticoinnova.it/innovazioni/54939-commissioning_of_a_system_that_terminates_on_the_seafloor/", metadata="https://itticoinnova.it/innovazioni/54939-commissioning_of_a_system_that_terminates_on_the_seafloor/", license=None, full_text=None, note="Exact title, all seven authors (including John Reardon, omitted from the source citation), 2013 OCEANS San Diego venue, pages 1–6, DOI, and full abstract were recovered from an exact scholarly-index record. The DOI was absent from the packet citation and was not present in Crossref's searchable record."),
    "COSZO-REF-159": dict(title="Axial seamount - restless, wired and occupied: A conceptual overview of resident AUV operations and technologies", doi="10.1109/OCEANS.2016.7761305", resource_type="conference_paper", abstract_source="https://paroscientific.com/pdf/UW%20Papers%202016/UW-Axial%20PID4388189.pdf", metadata="https://api.crossref.org/works/10.1109%2FOCEANS.2016.7761305", license=None, full_text="https://paroscientific.com/pdf/UW%20Papers%202016/UW-Axial%20PID4388189.pdf", note="Exact title, two authors, September 2016 conference, and DOI verified against Crossref; abstract transcribed from the labeled abstract in the complete paper PDF."),
    "COSZO-REF-160": dict(title="Variability of Natural Methane Bubble Release at Southern Hydrate Ridge", doi="10.1029/2021GC009894", resource_type="journal_article", abstract_source="https://api.crossref.org/works/10.1029%2F2021GC009894", metadata="https://api.crossref.org/works/10.1029%2F2021GC009894", license="http://creativecommons.org/licenses/by/4.0/", full_text="https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2021GC009894", note="Exact title, five authors, October 2021 journal issue, and DOI verified against Crossref and the AGU/Wiley article. Crossref supplies the publisher-deposited full abstract and CC BY 4.0 license."),
    "COSZO-REF-161": dict(title="“Capturing” Transient Oceanographic Phenomena With “Resident” AUVs", doi="10.4031/MTSJ.54.5.3", resource_type="journal_article", abstract_source=None, metadata="https://api.crossref.org/works/10.4031%2FMTSJ.54.5.3", license=None, full_text=None, note="Exact title, two authors, September 2020 date, volume 54(5), pages 8–14, and DOI verified against Crossref. Crossref has no abstract, the publisher landing page returned HTTP 403 to automated retrieval, and exact-title scholarly searches exposed no abstract text; marked not_found rather than substituting related text."),
    "COSZO-REF-162": dict(title="Resident Subsea Robotic Systems: A Review", doi="10.4031/MTSJ.54.5.4", resource_type="journal_review_article", abstract_source="https://api.crossref.org/works/10.4031%2FMTSJ.54.5.4", metadata="https://api.crossref.org/works/10.4031%2FMTSJ.54.5.4", license=None, full_text=None, note="The source citation says ‘Resident Seabed’; exact publisher-deposited metadata gives ‘Resident Subsea Robotic Systems: A Review.’ Exact three authors, September 2020 date, volume 54(5), pages 21–31, DOI, and full abstract verified against Crossref and corroborated by the TRID record."),
    "COSZO-REF-163": dict(title="Resident AUV Workshop 2018: Applications and a Path Forward", doi="10.1109/AUV.2018.8729720", resource_type="conference_paper", abstract_source="https://itticoinnova.it/innovazioni/5282-resident_auv_workshop_2018_applications_and_a_path_forward/", metadata="https://api.crossref.org/works/10.1109%2FAUV.2018.8729720", license=None, full_text=None, note="Exact title, four authors, November 2018 IEEE/OES AUV Workshop, pages 1–6, and DOI verified against Crossref; full abstract recovered from an exact scholarly-index record after publisher metadata exposed no abstract."),
    "COSZO-REF-164": dict(title="Persistent Mobile Ocean Observing: Marine Vehicle Highways", doi="10.4031/MTSJ.55.3.29", resource_type="journal_commentary", abstract_source="https://www.mtsociety.org/assets/May%20June%20Journal%20Final%20MTS55-3-FINAL%201.pdf", metadata="https://api.crossref.org/works/10.4031%2FMTSJ.55.3.29", license=None, full_text="https://www.mtsociety.org/assets/May%20June%20Journal%20Final%20MTS55-3-FINAL%201.pdf", note="Exact title, three authors, May 2021 issue, pages 86–87, and DOI verified against Crossref. The item is an Ocean-Shot/commentary in the journal; its labeled abstract was verified in the complete publisher-hosted issue PDF."),
    "COSZO-REF-165": dict(title="Adaptive Wireless Power for Subsea Vehicles", doi="10.4031/MTSJ.56.5.9", resource_type="journal_article", abstract_source="https://api.crossref.org/works/10.4031%2FMTSJ.56.5.9", metadata="https://api.crossref.org/works/10.4031%2FMTSJ.56.5.9", license=None, full_text=None, note="Exact journal version verified: six authors, 14 October 2022, volume 56(5), pages 36–44, and DOI. Crossref supplies the publisher-deposited abstract; this was kept distinct from the 2021 IEEE conference paper with the same title (DOI 10.23919/OCEANS44145.2021.9705989)."),
    "COSZO-REF-166": dict(title="Developing a Warning System for Inbound Tsunamis from the Cascadia Subduction Zone", doi="10.1109/OCEANS.2018.8604709", resource_type="conference_paper", abstract_source="https://faculty.washington.edu/wilcock/files/PaperPDFs/LeVequeetal_Oceans18_2018.pdf", metadata="https://api.crossref.org/works/10.1109%2FOCEANS.2018.8604709", license=None, full_text="https://faculty.washington.edu/wilcock/files/PaperPDFs/LeVequeetal_Oceans18_2018.pdf", note="The packet omitted the DOI. Exact title, 12 authors, October 2018 conference, pages 1–10, and DOI verified against Crossref and UW/author bibliographies; abstract transcribed from the labeled abstract in the University of Washington-hosted paper PDF."),
    "COSZO-REF-167": dict(title="Lessons Learned From the United States Ocean Observatories Initiative", doi="10.3389/fmars.2018.00494", resource_type="journal_mini_review", abstract_source="https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2018.00494/full", metadata="https://api.crossref.org/works/10.3389%2Ffmars.2018.00494", license="https://creativecommons.org/licenses/by/4.0/", full_text="https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2018.00494/full", note="Exact title, 17 authors, Frontiers mini-review type, 4 January 2019 publication date, volume 5 article 494, and DOI verified against the publisher and Crossref. The abstract and CC BY 4.0 license come from the publisher page."),
}

attempts = {
    "COSZO-REF-156": [
        {"url": "https://api.crossref.org/works/10.1109%2FOCEANSKOBE.2018.8559178", "result": "HTTP 200; exact title, ten authors, May 2018, proceedings article; no abstract"},
        {"url": "https://faculty.washington.edu/wilcock/files/PaperPDFs/Wilcocketal_Oceans18_2018.pdf", "result": "HTTP 200; complete 2018 IEEE paper; exact labeled abstract retrieved"},
    ],
    "COSZO-REF-157": [
        {"url": "https://api.crossref.org/works/10.1109%2FOCEANS.2016.7761291", "result": "HTTP 200; exact title, 16 authors, September 2016, proceedings article; no abstract"},
        {"url": "https://www.researchgate.net/publication/311753878_Designing_an_offshore_geophysical_network_in_the_Pacific_Northwest_for_earthquake_and_tsunami_early_warning_and_hazard_research", "result": "Exact-title scholarly record exposes the complete abstract; automated HTML fetch returned 403"},
        {"url": "https://staff.washington.edu/rjl/pubs/", "result": "University of Washington author bibliography corroborates exact title and DOI; no open paper located"},
    ],
    "COSZO-REF-158": [
        {"url": "https://api.crossref.org/works?query.bibliographic=Commissioning%20of%20a%20System%20that%20Terminates%20on%20the%20Seafloor&rows=4", "result": "HTTP 200; no matching record among returned candidates"},
        {"url": "https://itticoinnova.it/innovazioni/54939-commissioning_of_a_system_that_terminates_on_the_seafloor/", "result": "HTTP 200; exact title, seven authors, date, venue, pages, DOI, and complete abstract retrieved"},
        {"url": "https://www.proceedings.com/content/021/021340webtoc.pdf", "result": "Conference table of contents corroborates title, seven authors, and page 1009 start"},
    ],
    "COSZO-REF-159": [
        {"url": "https://api.crossref.org/works/10.1109%2FOCEANS.2016.7761305", "result": "HTTP 200; exact title, two authors, September 2016, proceedings article; no abstract"},
        {"url": "https://paroscientific.com/pdf/UW%20Papers%202016/UW-Axial%20PID4388189.pdf", "result": "HTTP 200; complete 2016 IEEE paper; exact labeled abstract retrieved"},
    ],
    "COSZO-REF-160": [
        {"url": "https://api.crossref.org/works/10.1029%2F2021GC009894", "result": "HTTP 200; exact title/authors/year and full publisher-deposited abstract; CC BY 4.0"},
        {"url": "https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2021GC009894", "result": "Publisher full article and abstract verified"},
    ],
    "COSZO-REF-161": [
        {"url": "https://api.crossref.org/works/10.4031%2FMTSJ.54.5.3", "result": "HTTP 200; exact title/authors/date/pages; no abstract"},
        {"url": "https://www.ingentaconnect.com/content/mts/mtsj/2020/00000054/00000005/art00003", "result": "Publisher landing page identified by Crossref; automated retrieval returned HTTP 403"},
        {"url": "https://www.researchgate.net/publication/346382370_Capturing_Transient_Oceanographic_Phenomena_With_Resident_AUVs", "result": "Exact record confirms title, authors, journal, pages, and DOI but exposes no abstract text"},
    ],
    "COSZO-REF-162": [
        {"url": "https://api.crossref.org/works/10.4031%2FMTSJ.54.5.4", "result": "HTTP 200; exact corrected title/authors/date/pages and full publisher-deposited abstract"},
        {"url": "https://trid.trb.org/View/1748239", "result": "Independent scholarly index corroborates exact metadata and complete abstract"},
    ],
    "COSZO-REF-163": [
        {"url": "https://api.crossref.org/works/10.1109%2FAUV.2018.8729720", "result": "HTTP 200; exact title, four authors, November 2018, proceedings article; no abstract"},
        {"url": "https://itticoinnova.it/innovazioni/5282-resident_auv_workshop_2018_applications_and_a_path_forward/", "result": "HTTP 200; exact metadata and complete abstract retrieved"},
    ],
    "COSZO-REF-164": [
        {"url": "https://api.crossref.org/works/10.4031%2FMTSJ.55.3.29", "result": "HTTP 200; exact title/authors/date/pages and full publisher-deposited abstract"},
        {"url": "https://www.mtsociety.org/assets/May%20June%20Journal%20Final%20MTS55-3-FINAL%201.pdf", "result": "HTTP 200; complete publisher issue; labeled abstract and full two-page item verified"},
    ],
    "COSZO-REF-165": [
        {"url": "https://api.crossref.org/works/10.4031%2FMTSJ.56.5.9", "result": "HTTP 200; exact journal version, six authors, date/pages, and full publisher-deposited abstract"},
        {"url": "https://www.ingentaconnect.com/content/mts/mtsj/2022/00000056/00000005/art00007", "result": "Publisher landing URL identified by Crossref; automated retrieval returned HTTP 403"},
        {"url": "https://tethys-engineering.pnnl.gov/publications/adaptive-wireless-power-subsea-vehicles", "result": "PNNL scholarly index identified a distinct 2021 IEEE conference version; not substituted for the cited 2022 journal article"},
    ],
    "COSZO-REF-166": [
        {"url": "https://api.crossref.org/works/10.1109%2FOCEANS.2018.8604709", "result": "HTTP 200; exact title, 12 authors, October 2018, proceedings article; no abstract"},
        {"url": "https://faculty.washington.edu/wilcock/files/PaperPDFs/LeVequeetal_Oceans18_2018.pdf", "result": "HTTP 200; complete 10-page IEEE paper; exact labeled abstract retrieved"},
        {"url": "https://digital.lib.washington.edu/bitstreams/af1746ff-3ada-4d32-ab9a-f322e511a5d9/download", "result": "HTTP 200; UW repository copy corroborates full paper and abstract"},
    ],
    "COSZO-REF-167": [
        {"url": "https://api.crossref.org/works/10.3389%2Ffmars.2018.00494", "result": "HTTP 200; exact title, 17 authors, DOI/date; CC BY 4.0; Crossref has no abstract"},
        {"url": "https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2018.00494/full", "result": "HTTP 200; publisher page supplies full abstract, article type, publication date, and CC BY license"},
    ],
}

results = []
for ref_id in sorted(specs, key=lambda x: int(x.rsplit("-", 1)[-1])):
    spec = specs[ref_id]
    abstract = abstracts[ref_id]
    results.append({
        "id": ref_id,
        "resolved_title": spec["title"],
        "resolved_doi": spec["doi"],
        "resource_type": spec["resource_type"],
        "paper_url": f"https://doi.org/{spec['doi']}",
        "abstract": abstract,
        "abstract_status": "retrieved" if abstract else "not_found",
        "abstract_source_url": spec["abstract_source"],
        "retrieved_at": retrieved_at,
        "metadata_source_url": spec["metadata"],
        "license": spec["license"],
        "full_text_url": spec["full_text"],
        "notes": spec["note"],
        "attempts": attempts[ref_id],
    })

(BASE / "results.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in results))

web_evidence = {
    "generated_at": retrieved_at,
    "purpose": "Verbatim abstract text recovered through scholarly web indexes when direct HTML retrieval was unavailable; each URL and matching metadata are recorded in results.jsonl.",
    "records": [
        {"id": "COSZO-REF-157", "source_url": specs["COSZO-REF-157"]["abstract_source"], "abstract": abstracts["COSZO-REF-157"]},
    ],
}
(RAW / "web_evidence.json").write_text(json.dumps(web_evidence, ensure_ascii=False, indent=2) + "\n")

manifest = []
for path in sorted(RAW.iterdir()):
    if path.is_file():
        manifest.append({"file": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
(BASE / "raw_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

print(json.dumps({
    "records": len(results),
    "retrieved": sum(r["abstract_status"] == "retrieved" for r in results),
    "not_found": sum(r["abstract_status"] == "not_found" for r in results),
    "resource_types": {r["id"]: r["resource_type"] for r in results},
}, indent=2))
