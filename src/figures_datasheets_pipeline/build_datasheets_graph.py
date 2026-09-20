#!/usr/bin/env python3
"""Build a page- and product-aware Graph-RAG corpus from technical datasheet PDFs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from pypdf import PdfReader


SCHEMA_VERSION = "1.0.0"
VISUAL_RE = re.compile(r"\b(figure|fig\.|table|diagram|schematic|pinout|connector|block diagram|board layout|drawing)\b", re.I)

PRODUCTS = {
    "ocelot": {"name": "VersaLogic Ocelot VL-EPMs-21", "type": "embedded_computer", "manufacturer": "VersaLogic", "model": "VL-EPMs-21", "status": "current_COSZO_node_controller"},
    "sandcat": {"name": "VersaLogic SandCat VL-EPM-39", "type": "embedded_computer", "manufacturer": "VersaLogic", "model": "VL-EPM-39", "status": "candidate_node_controller_replacement"},
    "ts7800": {"name": "Technologic Systems TS-7800-V2", "type": "embedded_computer", "manufacturer": "Technologic Systems", "model": "TS-7800-V2", "status": "candidate_node_controller_replacement"},
    "sbe54": {"name": "Sea-Bird SBE 54 Tsunameter", "type": "pressure_sensor", "manufacturer": "Sea-Bird Electronics", "model": "SBE 54", "status": "historical_obsolete_RCA_context"},
    "seed": {"name": "SEED Format Version 2.4", "type": "data_standard", "manufacturer": "FDSN / IRIS / USGS", "model": "2.4", "status": "reference_standard"},
    "tds_eew": {"name": "TDS Earthquake Early Warning Software", "type": "software", "manufacturer": "Trident Data Services", "model": None, "status": "software_description"},
    "warn_method": {"name": "WARN three-component accelerometer processing", "type": "processing_method", "manufacturer": "Andreas Rosenberger", "model": "v0.6", "status": "algorithm_reference"},
    "node_controller": {"name": "COSZO Node Controller Computer", "type": "system_role", "manufacturer": None, "model": None, "status": "requirements_and_selection_context"},
    "titan": {"name": "Nanometrics Titan Class A accelerometer", "type": "instrument_component", "manufacturer": "Nanometrics", "model": "Titan Class A", "status": "COBSO_component"},
    "rbr_tiltmeter": {"name": "RBR tiltmeter", "type": "instrument_model", "manufacturer": "RBR", "model": None, "status": "accepted_EEW_input_model"},
}
for key, value in PRODUCTS.items():
    value["entity_id"] = f"ENTITY-{hashlib.sha256(('datasheet-product\x1f' + key).encode()).hexdigest()[:16]}"

FILE_META = {
    "EEW-arosenberger.pdf": {"title": "Three component accelerometer signal processing for WARN", "document_type": "algorithm_documentation", "products": ["warn_method"]},
    "Node Controller Computer.pdf": {"title": "COSZO Node Controller Computer requirements and candidates", "document_type": "requirements_and_selection", "products": ["node_controller", "ocelot", "sandcat", "ts7800"]},
    "Ocelot-Datasheet.pdf": {"title": "VersaLogic Ocelot datasheet", "document_type": "product_datasheet", "products": ["ocelot"]},
    "Ocelot-ReferenceManual.pdf": {"title": "VersaLogic Ocelot reference manual", "document_type": "hardware_reference_manual", "products": ["ocelot"]},
    "SEEDManual_V2.4.pdf": {"title": "SEED Reference Manual Version 2.4", "document_type": "data_standard_manual", "products": ["seed"]},
    "TDS EEW Software Description.pdf": {"title": "TDS EEW Software Description", "document_type": "software_description", "products": ["tds_eew", "warn_method", "titan", "rbr_tiltmeter"]},
    "Versalogic-SandCatMEPM39_HRM.pdf": {"title": "VersaLogic SandCat VL-EPM-39 Hardware Reference Manual", "document_type": "hardware_reference_manual", "products": ["sandcat"]},
    "seabird_sbe_54_user_manual-v008.pdf": {"title": "Sea-Bird SBE 54 Tsunameter User Manual", "document_type": "instrument_user_manual", "products": ["sbe54"]},
    "ts-7800-v2-schematic.pdf": {"title": "Technologic Systems TS-7800-V2 schematic", "document_type": "electrical_schematic", "products": ["ts7800"]},
}

SHARED_ENTITIES = {
    "COSZO": ("ENTITY-ad531dfdd4e7a1c9", "project", ["Cascadia Offshore Subduction Zone Observatory"]),
    "Regional Cabled Array": ("ENTITY-7b20fdc48eca4ee8", "observatory", ["RCA"]),
}

COBSO_IDS = [
    "INSTRUMENT-107e896447f64d7335",
    "INSTRUMENT-75f64fba174aca6138",
    "INSTRUMENT-ca2fec8152a1ea41fb",
    "INSTRUMENT-e4f2c09f3e3d1c9a50",
]


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def stable_id(prefix: str, *parts: object, size: int = 16) -> str:
    raw = "\x1f".join(map(str, parts)).encode()
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()[:size]}"


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\x00", " ").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{4,}", "\n\n\n", text).strip()


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def render_pdf(pdf: Path, page_dir: Path, key: str, count: int, dpi: int) -> list[Path]:
    final = [page_dir / f"{key}-p{i:04d}.jpg" for i in range(1, count + 1)]
    if all(p.exists() for p in final):
        return final
    prefix = page_dir / f".{key}"
    subprocess.run(["pdftoppm", "-jpeg", "-r", str(dpi), "-jpegopt", "quality=85,progressive=y,optimize=y", str(pdf), str(prefix)], check=True, stdout=subprocess.DEVNULL)
    rendered = sorted(page_dir.glob(f".{key}-*.jpg"), key=lambda p: int(re.search(r"-(\d+)\.jpg$", p.name).group(1)))
    if len(rendered) != count:
        raise RuntimeError(f"{pdf.name}: rendered {len(rendered)} pages, expected {count}")
    for src, dst in zip(rendered, final):
        src.replace(dst)
    return final


def image_pages(pdf: Path) -> set[int]:
    run = subprocess.run(["pdfimages", "-list", str(pdf)], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    found = set()
    for line in run.stdout.splitlines():
        cols = line.split()
        if cols and cols[0].isdigit() and len(cols) > 2 and cols[2] == "image":
            found.add(int(cols[0]))
    return found


def ocr(path: Path) -> tuple[str, float | None]:
    run = subprocess.run(["tesseract", str(path), "stdout", "-l", "eng", "--psm", "11", "tsv"], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    rows = run.stdout.splitlines()
    if not rows:
        return "", None
    header = rows[0].split("\t"); pos = {x: i for i, x in enumerate(header)}
    lines: dict[tuple[int, int, int], list[str]] = defaultdict(list); confs = []
    for row in rows[1:]:
        c = row.split("\t")
        if len(c) < len(header) or not c[pos["text"]].strip():
            continue
        value = c[pos["text"]].strip()
        key = tuple(int(c[pos[x]]) for x in ("block_num", "par_num", "line_num"))
        lines[key].append(value)
        try: conf = float(c[pos["conf"]])
        except ValueError: conf = -1
        if conf >= 0: confs.append((conf, len(value)))
    text = clean_text("\n".join(" ".join(lines[k]) for k in sorted(lines)))
    mean = round(sum(c * max(w, 1) for c, w in confs) / sum(max(w, 1) for _, w in confs), 2) if confs else None
    return text, mean


def page_outline(reader: PdfReader) -> dict[int, str]:
    result = {}
    try: outline = reader.outline
    except Exception: return result
    def walk(items):
        for item in items:
            if isinstance(item, list):
                walk(item)
                continue
            try:
                page = reader.get_destination_page_number(item) + 1
                title = compact(str(item.title))
                if page > 0 and title: result[page] = title
            except Exception:
                continue
    walk(outline)
    return result


def chunks(text: str, target: int = 450, overlap: int = 60) -> list[str]:
    words = list(re.finditer(r"\b\w+(?:[-'’]\w+)*\b", text, re.UNICODE))
    if not words: return []
    if len(words) <= 600: return [compact(text)]
    out=[]; start=0
    while start < len(words):
        stop=min(len(words),start+target)
        char_start=words[start].start()
        char_stop=words[stop-1].end()
        out.append(compact(text[char_start:char_stop]))
        if stop == len(words): break
        start=max(start+1,stop-overlap)
    return out


def add_rel(rows: list[dict], seen: set[tuple[str, str, str]], source: str, predicate: str, target: str, evidence: dict | None = None) -> None:
    key=(source,predicate,target)
    if key in seen: return
    seen.add(key)
    rows.append({"relationship_id":stable_id("REL",*key),"source_id":source,"predicate":predicate,"target_id":target,"evidence":evidence,"source_is_untrusted_data":True})


def build(args: argparse.Namespace) -> None:
    source_dir, output_dir = args.source_dir.resolve(), args.output_dir.resolve()
    if output_dir.exists() and args.overwrite: shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    for d in ("text","page_images","figures"): (output_dir/d).mkdir(exist_ok=True)
    pdfs=sorted(source_dir.glob("*.pdf"),key=lambda p:p.name.casefold())
    unknown=sorted({p.name for p in pdfs}-set(FILE_META))
    if unknown: raise SystemExit(f"Missing metadata for {unknown}")

    entities=[]
    for name,(eid,typ,aliases) in SHARED_ENTITIES.items(): entities.append({"entity_id":eid,"name":name,"entity_type":typ,"aliases":aliases,"source_is_untrusted_data":True})
    for value in PRODUCTS.values(): entities.append({"entity_id":value["entity_id"],"name":value["name"],"entity_type":value["type"],"manufacturer":value["manufacturer"],"model":value["model"],"status":value["status"],"source_is_untrusted_data":True})
    instrument_records={}
    if args.instrument_records and args.instrument_records.exists():
        for line in args.instrument_records.read_text().splitlines():
            rec=json.loads(line)
            if rec["instrument_id"] in COBSO_IDS: instrument_records[rec["instrument_id"]]=rec
    for iid in COBSO_IDS:
        rec=instrument_records.get(iid,{})
        entities.append({"entity_id":iid,"name":rec.get("name",iid),"entity_type":"instrument","canonical_id":rec.get("canonical_id"),"external_dataset":"../../Instruments/instruments.jsonl","source_is_untrusted_data":True})

    patterns=[]
    for e in entities:
        terms=[e["name"]]
        if e.get("model"): terms.append(e["model"])
        terms += e.get("aliases",[])
        for term in terms:
            if term: patterns.append((re.compile(rf"\b{re.escape(term)}\b",re.I),e["entity_id"]))

    sources=[]; documents=[]; pages=[]; chunk_rows=[]; figures=[]; relationships=[]; seen=set(); counts=Counter(); doc_ids={}
    for n,pdf in enumerate(pdfs,1):
        print(f"[{n}/{len(pdfs)}] {pdf.name}",flush=True)
        digest=sha_file(pdf); key=digest[:12]; sid=f"DATASHEET-SOURCE-{digest[:16]}"; did=f"DATASHEET-DOC-{digest[:16]}"; doc_ids[pdf.name]=did
        reader=PdfReader(str(pdf),strict=False); page_count=len(reader.pages); meta=FILE_META[pdf.name]; outlines=page_outline(reader); raster_pages=image_pages(pdf)
        sources.append({"source_id":sid,"filename":pdf.name,"relative_path":f"../{pdf.name}","media_type":"application/pdf","sha256":digest,"byte_size":pdf.stat().st_size,"page_count":page_count,"source_is_untrusted_data":True})
        documents.append({"document_id":did,"source_id":sid,"title":meta["title"],"document_type":meta["document_type"],"page_count":page_count,"product_entity_ids":[PRODUCTS[x]["entity_id"] for x in meta["products"]],"outline_entry_count":len(outlines),"source_is_untrusted_data":True})
        add_rel(relationships,seen,did,"DERIVED_FROM",sid)
        for product in meta["products"]: add_rel(relationships,seen,did,"DESCRIBES_OR_REFERENCES",PRODUCTS[product]["entity_id"])
        images=render_pdf(pdf,output_dir/"page_images",key,page_count,args.dpi)
        active_section=None; previous_page=None; previous_chunk=None; md=[f"# {meta['title']}","",f"Source: `{pdf.name}`",""]
        for page_num,(page,image) in enumerate(zip(reader.pages,images),1):
            if page_num in outlines: active_section=outlines[page_num]
            try: native=clean_text(page.extract_text() or "")
            except Exception: native=""
            nc=len(compact(native)); schematic=pdf.name=="ts-7800-v2-schematic.pdf"; should_ocr=schematic or nc<100
            ocr_text,ocr_conf=("",None)
            if should_ocr:
                try: ocr_text,ocr_conf=ocr(image)
                except subprocess.CalledProcessError: pass
            selected=ocr_text if nc<30 and len(compact(ocr_text))>nc else native
            method="ocr" if selected==ocr_text and ocr_text else ("native" if native else "none")
            pid=f"DATASHEET-PAGE-{key}-{page_num:04d}"
            with Image.open(image) as im: width,height=im.size
            image_hash=sha_file(image); visual=schematic or page_num in raster_pages or bool(VISUAL_RE.search(native)) or nc<100
            pages.append({"page_id":pid,"document_id":did,"source_id":sid,"page_number":page_num,"locator":f"{pdf.name}#page={page_num}","section_title":active_section,"native_text":native,"ocr_text":ocr_text,"selected_text":selected,"extraction_method":method,"native_character_count":nc,"selected_word_count":len(re.findall(r'\b\w+\b',selected)),"ocr_attempted":should_ocr,"ocr_mean_confidence":ocr_conf,"is_intentional_blank":pdf.name=="SEEDManual_V2.4.pdf" and page_num in {132,222} and not selected,"page_image_path":str(image.relative_to(output_dir)),"page_image_sha256":image_hash,"width_px":width,"height_px":height,"render_dpi":args.dpi,"source_is_untrusted_data":True})
            add_rel(relationships,seen,did,"HAS_PAGE",pid,{"page_number":page_num})
            if previous_page: add_rel(relationships,seen,previous_page,"NEXT_PAGE",pid)
            previous_page=pid
            mentioned=sorted({eid for pattern,eid in patterns if pattern.search(selected)})
            for pos,value in enumerate(chunks(selected),1):
                cid=stable_id("DATASHEET-CHUNK",pid,pos,value)
                chunk_rows.append({"chunk_id":cid,"document_id":did,"page_id":pid,"source_id":sid,"page_number":page_num,"position_on_page":pos,"title":active_section or meta["title"],"locator":f"{pdf.name}#page={page_num}","text":value,"word_count":len(re.findall(r'\b\w+\b',value)),"entity_ids":mentioned,"source_is_untrusted_data":True})
                add_rel(relationships,seen,pid,"HAS_CHUNK",cid)
                if previous_chunk: add_rel(relationships,seen,previous_chunk,"NEXT_CHUNK",cid)
                previous_chunk=cid
                for eid in mentioned: add_rel(relationships,seen,cid,"MENTIONS",eid)
            if visual:
                fid=f"DATASHEET-FIG-{key}-p{page_num:04d}-001"; fp=output_dir/"figures"/f"{fid}.jpg"
                if not fp.exists():
                    try: os.link(image,fp)
                    except OSError: shutil.copy2(image,fp)
                figures.append({"figure_id":fid,"document_id":did,"page_id":pid,"source_id":sid,"page_number":page_num,"visual_type":"electrical_schematic" if schematic else "technical_page_visual","image_path":str(fp.relative_to(output_dir)),"image_sha256":image_hash,"caption_or_page_text":compact(selected)[:4000],"representation":"full-page render preserving diagrams, tables, labels, and spatial layout","source_is_untrusted_data":True})
                add_rel(relationships,seen,pid,"HAS_FIGURE",fid)
            md += [f"## Page {page_num}" + (f": {active_section}" if active_section else ""),"",selected or "*[Intentional blank or no machine-readable text; see page image.]*",""]
            counts["ocr_attempted"]+=int(should_ocr); counts["visual_pages"]+=int(visual)
        (output_dir/"text"/f"{key}-{re.sub(r'[^a-z0-9]+','-',pdf.stem.casefold()).strip('-')}.md").write_text("\n".join(md),encoding="utf-8")

    # Product and cross-corpus graph semantics.
    add_rel(relationships,seen,PRODUCTS["node_controller"]["entity_id"],"CURRENT_PRODUCT",PRODUCTS["ocelot"]["entity_id"],{"source_document":doc_ids["Node Controller Computer.pdf"]})
    for candidate in ("sandcat","ts7800"): add_rel(relationships,seen,PRODUCTS["node_controller"]["entity_id"],"CANDIDATE_REPLACEMENT",PRODUCTS[candidate]["entity_id"],{"source_document":doc_ids["Node Controller Computer.pdf"]})
    add_rel(relationships,seen,doc_ids["Ocelot-Datasheet.pdf"],"COMPANION_DOCUMENT",doc_ids["Ocelot-ReferenceManual.pdf"],{"basis":"same product, complementary datasheet and reference manual"})
    add_rel(relationships,seen,PRODUCTS["tds_eew"]["entity_id"],"BASED_ON",PRODUCTS["warn_method"]["entity_id"],{"source_document":doc_ids["TDS EEW Software Description.pdf"]})
    for model in ("titan","rbr_tiltmeter"): add_rel(relationships,seen,PRODUCTS["tds_eew"]["entity_id"],"ACCEPTS_INPUT_FROM_MODEL",PRODUCTS[model]["entity_id"],{"source_document":doc_ids["TDS EEW Software Description.pdf"]})
    for iid in COBSO_IDS: add_rel(relationships,seen,iid,"INCLUDES_COMPONENT",PRODUCTS["titan"]["entity_id"],{"basis":"instrument inventory sensor component"})
    add_rel(relationships,seen,PRODUCTS["sbe54"]["entity_id"],"HISTORICALLY_USED_BY",SHARED_ENTITIES["Regional Cabled Array"][0],{"status":"obsolete context; do not equate with current COSZO APGs","external_evidence":"COSZO kickoff page 37"})
    add_rel(relationships,seen,SHARED_ENTITIES["COSZO"][0],"REFERENCES_STANDARD",PRODUCTS["seed"]["entity_id"],{"external_evidence":"COSZO DataMSRI seismic/acoustic data-product specifications"})

    for name,rows in [("source_documents",sources),("documents",documents),("pages",pages),("chunks",chunk_rows),("figures",figures),("entities",entities),("relationships",relationships)]: write_jsonl(output_dir/f"{name}.jsonl",rows)
    all_ids={x[k] for rows,k in [(sources,"source_id"),(documents,"document_id"),(pages,"page_id"),(chunk_rows,"chunk_id"),(figures,"figure_id"),(entities,"entity_id")] for x in rows}
    unresolved=sorted({v for r in relationships for v in (r["source_id"],r["target_id"]) if v not in all_ids})
    covered=Counter(c["page_id"] for c in chunk_rows); covered.update(f["page_id"] for f in figures)
    checks={"all_source_pdfs_included":len(sources)==len(pdfs),"page_count_matches_sources":len(pages)==sum(s["page_count"] for s in sources),"all_page_images_exist":all((output_dir/p["page_image_path"]).exists() for p in pages),"all_figure_images_exist":all((output_dir/f["image_path"]).exists() for f in figures),"every_page_has_chunk_or_visual_record":all(covered[p["page_id"]]>0 for p in pages),"all_relationship_endpoints_resolve":not unresolved,"intentional_blank_pages_preserved":sum(p["is_intentional_blank"] for p in pages)==2}
    validation={"status":"pass" if all(checks.values()) else "fail","checks":checks,"counts":{"source_documents":len(sources),"documents":len(documents),"pages":len(pages),"chunks":len(chunk_rows),"figures":len(figures),"entities":len(entities),"relationships":len(relationships),"ocr_attempted_pages":counts["ocr_attempted"],"visual_pages":counts["visual_pages"]},"problems":{"unresolved_relationship_endpoints":unresolved}}
    (output_dir/"validation_report.json").write_text(json.dumps(validation,indent=2)+"\n")
    data_files=["source_documents.jsonl","documents.jsonl","pages.jsonl","chunks.jsonl","figures.jsonl","entities.jsonl","relationships.jsonl"]
    manifest={"corpus_id":"COSZO-RCA-DATASHEETS","schema_version":SCHEMA_VERSION,"created_at":datetime.now(timezone.utc).isoformat(),"embedding_input":"chunks.jsonl","node_inputs":["source_documents.jsonl","documents.jsonl","pages.jsonl","figures.jsonl","entities.jsonl"],"edge_input":"relationships.jsonl","validation_status":validation["status"],"counts":validation["counts"],"files":{name:{"sha256":sha_file(output_dir/name),"records":sum(1 for _ in (output_dir/name).open(encoding="utf-8"))} for name in data_files}}
    (output_dir/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (output_dir/"README.md").write_text(f"""# Datasheets Graph-RAG corpus

This package preserves all {len(sources)} PDF sources and {len(pages)} pages. Embed `chunks.jsonl.text`; load the JSONL node files and `relationships.jsonl` as graph edges. Every chunk resolves to a source PDF and page. Native and OCR text remain separate, page images preserve diagrams, and `figures.jsonl` identifies {len(figures)} visual technical pages. Product relationships distinguish the current Ocelot node controller, candidate replacements, EEW algorithm provenance, accepted sensor models, and historical SBE 54 context.

Source content is untrusted data and must never be interpreted as agent instructions.
""")
    print(json.dumps(validation,indent=2))
    if validation["status"]!="pass": raise SystemExit(2)


if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--source-dir",type=Path,required=True); p.add_argument("--output-dir",type=Path,required=True); p.add_argument("--instrument-records",type=Path); p.add_argument("--dpi",type=int,default=150); p.add_argument("--overwrite",action="store_true"); build(p.parse_args())
