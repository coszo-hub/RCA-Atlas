#!/usr/bin/env python3
import datetime as dt
import json

P="/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_products/retrieval_b/results.jsonl"
NOW=dt.datetime.now(dt.timezone.utc).isoformat()

MANUAL={
"COSZO-PRODB-007":{
 "resolved_title":"A Three-Component Borehole Optical Seismic and Geodetic Sensor",
 "resolved_doi":"10.1785/0120180045",
 "paper_url":"https://doi.org/10.1785/0120180045",
 "abstract":"We constructed a three-component combination seismometer and geodetic sensor suitable for borehole deployment. The instrument uses no electronics at depth in the borehole, rather it relies on optics. Two ∼40 cm pendulums suspended from two orthogonal axes with free periods slightly more than 1 s and a vertical mass-spring suspension with a free period near 5 s are tracked with optical interferometers inside a borehole sonde. Laser light for the interferometers is provided by optical fibers from the surface; the interference fringe signals are transmitted from the sonde to photo detectors at the surface, also via optical fibers. The system was installed in a 60-m-deep borehole at the U.S. Geological Survey's Albuquerque Seismological Laboratory (ASL) for 1 year. The seismic noise floor of the optical seismometer's components compares well with those of a collocated KS-54000 borehole seismometer. Because the optical sensors operate to zero frequency, they also provide useful geodetic records.",
 "abstract_source_url":"https://pubs.geoscienceworld.org/bssa/article/108/4/2022/531341/A-Three-Component-Borehole-Optical-Seismic-and",
 "metadata_source_url":"https://api.crossref.org/works/10.1785%2F0120180045",
 "license":None,
 "notes":"Exact title, four authors, 2018 publication year, volume/pages, and DOI verified against Crossref and the publisher record. Publisher abstract recovered through scholarly page indexing after the publisher rejected automated page retrieval."
},
"COSZO-PRODB-009":{
 "resolved_title":"Automatic classification with an autoencoder of seismic signals on a distributed acoustic sensing cable",
 "resolved_doi":"10.1016/j.compgeo.2022.105223",
 "paper_url":"https://www.sciencedirect.com/science/article/pii/S0266352X22005602",
 "abstract":"This study probes the association between fluid injection in enhanced geothermal systems and certain kinds of seismicity that may result from hydraulic fracturing occurring at depth using unsupervised machine learning. In April and May 2019, a distributed acoustic sensing borehole array at the Frontier Observatory for Research in Geothermal Energy site near Milford, Utah recorded seismic data during hydraulic injection stimulation of a nearby well. Using an autoencoder, a type of deep neural network, we reduce the dimensionality of spectrograms of the detected signals to a lower-dimensional latent feature space with just nine dimensions. Next, Gaussian mixture model clustering is performed on this latent feature space, assigning each detected signal to one of 7 classes. For each signal class, we examine spatiotemporal distributions of the clustered results and find that total detections exhibit a bimodal distribution with respect to channel depth. The shallow mode occurs between 250 and 500 m, and the deep mode is centered around 750 m. In the temporal distribution, clustering results show the two best-clustered signal classes exhibit weak or no correlation with injection-related activities. More generally, we demonstrate the ability to discern not just when and where signals are detected, but also what kind, thus enabling rapid and targeted data exploration and providing constraints on source mechanisms.",
 "abstract_source_url":"https://www.sciencedirect.com/science/article/pii/S0266352X22005602",
 "metadata_source_url":"https://api.crossref.org/works/10.1016%2Fj.compgeo.2022.105223",
 "license":None,
 "notes":"Exact title, five authors, 2023 issue year, article number, PII, and DOI verified against Crossref and the publisher record. Full publisher abstract recovered from the indexed ScienceDirect article page. Crossref's TDM license URL was not treated as an article license."
}}

rs=[json.loads(x) for x in open(P)]
for r in rs:
    if r["id"] in MANUAL:
        r.update(MANUAL[r["id"]]);r["abstract_status"]="retrieved";r["retrieved_at"]=NOW;r["full_text_url"]=None
        r.setdefault("attempts",[]).append({"url":r["abstract_source_url"],"result":"exact title/authors/year and full abstract verified via scholarly page index"})
    # Registry links describing text/data-mining permissions are not article licenses.
    if r.get("license") and any(x in r["license"].lower() for x in ("text-and-data-mining","tdm/userlicense","termsandconditions")):
        r.setdefault("attempts",[]).append({"url":r["license"],"result":"not retained: registry supplied a TDM/terms link, not a publication license"})
        r["license"]=None
with open(P,"w") as f:
    for r in rs:f.write(json.dumps(r,ensure_ascii=False)+"\n")

with open("/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_products/retrieval_b/raw/manual_web_sources.json","w") as f:
    json.dump({k:{"abstract_source_url":v["abstract_source_url"],"abstract":v["abstract"],"verification_note":v["notes"]} for k,v in MANUAL.items()},f,ensure_ascii=False,indent=2)
