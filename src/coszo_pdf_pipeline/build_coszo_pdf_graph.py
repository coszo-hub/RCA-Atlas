#!/usr/bin/env python3
"""Build a provenance-preserving Graph RAG corpus from the COSZO PDF folder."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image
from pypdf import PdfReader


SCHEMA_VERSION = "1.0.0"
VISUAL_DOCUMENTS = {
    "CASIE-PD13+quakes.pdf",
    "COSZO-Kickoff-2023-10-18.pdf",
    "Visio-COSZO Instrument Data Flows_20260505.pdf",
    "Wilcock_A0A_poster_SSA_2022_afd2.pdf",
}
DOCUMENT_TYPES = {
    "CASIE-PD13+quakes.pdf": "map",
    "COSZO Project DataMSRI.pdf": "composite_project_packet",
    "COSZO-Kickoff-2023-10-18.pdf": "presentation",
    "COSZO_Description.pdf": "project_description",
    "ConceptOfOperations_PEP1.3_version.pdf": "concept_of_operations",
    "Data QA_QC Tools.pdf": "technical_note",
    "REU_projectDescription_2020.pdf": "project_description",
    "RIG nsf21107.pdf": "external_reference_guide",
    "Visio-COSZO Instrument Data Flows_20260505.pdf": "data_flow_diagram",
    "Wilcock_A0A_poster_SSA_2022_afd2.pdf": "poster",
}
SHARED_ENTITIES = {
    "COSZO": ("ENTITY-ad531dfdd4e7a1c9", "project", ["Cascadia Offshore Subduction Zone Observatory"]),
    "Regional Cabled Array": ("ENTITY-7b20fdc48eca4ee8", "observatory_array", ["RCA"]),
    "Axial Seamount": ("ENTITY-ef4071be4a479e64", "site", ["Axial", "Axial Volcano"]),
    "Southern Hydrate Ridge": ("ENTITY-72270d295400c13b", "site", ["SHR"]),
    "Oregon Slope Base": ("ENTITY-89195eb2518e747b", "site", ["Slope Base"]),
}
GENERIC_INSTRUMENTS = {
    "broadband seismometer": ["broadband seismometer", "broadband seismic"],
    "short-period seismometer": ["short-period seismometer", "short period seismometer"],
    "hydrophone": ["hydrophone"],
    "bottom pressure recorder": ["bottom pressure recorder", "BPR"],
    "differential pressure gauge": ["differential pressure gauge", "DPG"],
    "tiltmeter": ["tiltmeter"],
    "gravimeter": ["gravimeter", "gravity meter"],
    "current meter": ["current meter", "VEL3D", "ADCP"],
    "temperature sensor": ["temperature sensor", "thermistor"],
    "oxygen sensor": ["oxygen sensor"],
    "camera": ["camera", "CamHD"],
    "mass spectrometer": ["mass spectrometer", "MASSP"],
    "pore-fluid sampler": ["pore fluid sampler", "pore-fluid sampler", "PREST"],
    "COVIS sonar": ["COVIS"],
    "distributed acoustic sensing": ["distributed acoustic sensing", "DAS"],
}
VISUAL_RE = re.compile(r"\b(fig(?:ure)?\.?|table|diagram|schematic|map|photo(?:graph)?|poster)\b", re.I)
DATAMSRI_LOGICAL_RANGES = [
    (1, 1, "cover/map"),
    (2, 31, "project description and references"),
    (32, 33, "facilities, equipment, and resources"),
    (34, 35, "data management plan"),
    (36, 38, "REU supplement request"),
    (39, 47, "ship-time and marine equipment request"),
    (48, 89, "project execution plan main text"),
    (90, 96, "project schedule appendix"),
    (97, 103, "COSZO testing and integration plan"),
    (104, 114, "RCA instrument test plan"),
    (115, 126, "RCA secondary-nodes test plan"),
    (127, 136, "medium-power junction-box ICD"),
    (137, 146, "COSZO design files part 1 - functional block diagrams"),
    (147, 159, "broadband ground velocity data-product specification"),
    (160, 172, "broadband ground acceleration data-product specification"),
    (173, 189, "seafloor pressure data-product specification"),
    (190, 211, "mean point water velocity data-product specification"),
    (212, 223, "low-frequency acoustic pressure data-product specification"),
    (224, 238, "OOI-Digi interface-control document"),
    (239, 248, "duplicate copy of medium-power junction-box ICD"),
    (249, 256, "input-filter PCB ICD"),
    (257, 271, "instrument-interface PCB ICD"),
    (272, 281, "hotel-power PCB ICD"),
    (282, 294, "expansion-power PCB ICD"),
    (295, 300, "instrument high-power PCB ICD"),
    (301, 319, "controller-interface PCB ICD"),
    (320, 324, "network-switch ICD"),
    (325, 383, "mechanical/CAD drawing set"),
    (384, 479, "COSZO design files part 2 - electrical schematics"),
    (480, 524, "scanned executed electrical, communications, environmental, corrosion, and pressure test records"),
]


def sha_file(path: Path, block: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(block), b""):
            h.update(part)
    return h.hexdigest()


def stable_id(prefix: str, *parts: object, size: int = 16) -> str:
    raw = "\x1f".join(str(p) for p in parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()[:size]}"


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{4,}", "\n\n\n", value)
    return value.strip()


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalized_hash(value: str) -> str:
    norm = re.sub(r"\W+", " ", value.casefold()).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def word_count(value: str) -> int:
    return len(re.findall(r"\b\w+(?:[-'’]\w+)*\b", value, re.UNICODE))


def write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n")


def render_pdf(pdf: Path, page_dir: Path, source_key: str, expected_pages: int, dpi: int) -> list[Path]:
    page_dir.mkdir(parents=True, exist_ok=True)
    final = [page_dir / f"{source_key}-p{i:04d}.jpg" for i in range(1, expected_pages + 1)]
    if all(p.exists() and p.stat().st_size > 0 for p in final):
        return final
    temp_prefix = page_dir / f".{source_key}"
    for old in page_dir.glob(f".{source_key}-*.jpg"):
        old.unlink()
    cmd = [
        "pdftoppm", "-jpeg", "-r", str(dpi),
        "-jpegopt", "quality=85,progressive=y,optimize=y",
        str(pdf), str(temp_prefix),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    rendered = sorted(
        page_dir.glob(f".{source_key}-*.jpg"),
        key=lambda p: int(re.search(r"-(\d+)\.jpg$", p.name).group(1)),
    )
    if len(rendered) != expected_pages:
        raise RuntimeError(f"Rendered {len(rendered)} pages for {pdf.name}; expected {expected_pages}")
    for src, dst in zip(rendered, final):
        src.replace(dst)
    return final


def tesseract_ocr(image_path: Path) -> tuple[str, float | None]:
    cmd = ["tesseract", str(image_path), "stdout", "-l", "eng", "--psm", "3", "tsv"]
    run = subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    lines: dict[tuple[int, int, int, int], list[str]] = defaultdict(list)
    confidences: list[tuple[float, int]] = []
    rows = run.stdout.splitlines()
    if not rows:
        return "", None
    header = rows[0].split("\t")
    pos = {name: i for i, name in enumerate(header)}
    for row in rows[1:]:
        cols = row.split("\t")
        if len(cols) < len(header):
            continue
        text = cols[pos["text"]].strip()
        if not text:
            continue
        key = tuple(int(cols[pos[x]]) for x in ("block_num", "par_num", "line_num", "page_num"))
        lines[key].append(text)
        try:
            conf = float(cols[pos["conf"]])
        except (ValueError, KeyError):
            conf = -1
        if conf >= 0:
            confidences.append((conf, max(1, len(text))))
    text = "\n".join(" ".join(lines[k]) for k in sorted(lines))
    confidence = None
    if confidences:
        confidence = round(sum(c * w for c, w in confidences) / sum(w for _, w in confidences), 2)
    return clean_text(text), confidence


def select_text(native: str, ocr: str, visual_doc: bool) -> tuple[str, str]:
    nc, oc = len(compact(native)), len(compact(ocr))
    if nc < 60 and oc >= max(30, nc * 2):
        return ocr, "ocr"
    if nc == 0 and oc:
        return ocr, "ocr"
    if native and ocr and visual_doc:
        ratio = SequenceMatcher(None, compact(native).casefold()[:12000], compact(ocr).casefold()[:12000]).ratio()
        if ratio < 0.82 and word_count(ocr) >= 10:
            return clean_text(native + "\n\n[OCR from visual labels]\n" + ocr), "hybrid_native_ocr"
    if native:
        return native, "native"
    return ocr, "ocr" if ocr else "none"


def chunk_text(text: str, target_words: int = 450, overlap_words: int = 60) -> list[str]:
    words = re.findall(r"\S+", text)
    if not words:
        return []
    if len(words) <= 650:
        return [" ".join(words)]
    chunks = []
    start = 0
    while start < len(words):
        stop = min(len(words), start + target_words)
        if stop < len(words):
            search_from = max(start + 250, stop - 80)
            for idx in range(stop, search_from, -1):
                if re.search(r"[.!?:;)]$", words[idx - 1]):
                    stop = idx
                    break
        chunks.append(" ".join(words[start:stop]))
        if stop == len(words):
            break
        start = max(start + 1, stop - overlap_words)
    return chunks


def title_from_metadata(reader: PdfReader, pdf: Path) -> str:
    title = ""
    try:
        title = str((reader.metadata or {}).get("/Title") or "").strip()
    except Exception:
        pass
    if not title or title.lower() in {"untitled", "microsoft word - document1"}:
        title = pdf.stem.replace("_", " ")
    return title


def load_instrument_terms(path: Path | None) -> tuple[list[dict], list[tuple[re.Pattern, str]]]:
    if not path or not path.exists():
        return [], []
    entities, patterns = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        iid = rec["instrument_id"]
        entities.append({
            "entity_id": iid,
            "name": rec.get("name") or rec.get("canonical_id") or iid,
            "entity_type": "instrument",
            "canonical_id": rec.get("canonical_id"),
            "aliases": rec.get("aliases", []),
            "external_dataset": "../../Instruments/instruments.jsonl",
            "source_is_untrusted_data": True,
        })
        terms = [rec.get("canonical_id")]
        terms += [a for a in rec.get("aliases", []) if len(a) >= 5 and re.search(r"\d", a)]
        for term in filter(None, terms):
            patterns.append((re.compile(rf"(?<![\w-]){re.escape(term)}(?![\w-])", re.I), iid))
    return entities, patterns


def mention_entities(text: str, local_patterns: list[tuple[re.Pattern, str]], instrument_patterns: list[tuple[re.Pattern, str]]) -> list[str]:
    found = {eid for pattern, eid in local_patterns if pattern.search(text)}
    found.update(eid for pattern, eid in instrument_patterns if pattern.search(text))
    return sorted(found)


def add_relationship(records: list[dict], seen: set[tuple[str, str, str]], source: str, rel_type: str, target: str, evidence: dict | None = None) -> None:
    key = (source, rel_type, target)
    if key in seen:
        return
    seen.add(key)
    records.append({
        "relationship_id": stable_id("REL", source, rel_type, target),
        "source_id": source,
        "relationship_type": rel_type,
        "target_id": target,
        "evidence": evidence,
        "source_is_untrusted_data": True,
    })


def build(args: argparse.Namespace) -> None:
    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    pdfs = sorted(source_dir.glob("*.pdf"), key=lambda p: p.name.casefold())
    if not pdfs:
        raise SystemExit(f"No PDFs found in {source_dir}")
    required = ["pdftoppm", "tesseract"]
    missing = [name for name in required if not shutil.which(name)]
    if missing:
        raise SystemExit("Missing required tools: " + ", ".join(missing))
    if output_dir.exists() and args.overwrite:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in ("text", "page_images", "figures"):
        (output_dir / name).mkdir(exist_ok=True)

    source_records: list[dict] = []
    documents: list[dict] = []
    pages: list[dict] = []
    chunks: list[dict] = []
    figures: list[dict] = []
    relationships: list[dict] = []
    rel_seen: set[tuple[str, str, str]] = set()
    entities: list[dict] = []
    local_patterns: list[tuple[re.Pattern, str]] = []
    for name, (eid, entity_type, aliases) in SHARED_ENTITIES.items():
        entities.append({"entity_id": eid, "name": name, "entity_type": entity_type, "aliases": aliases, "source_is_untrusted_data": True})
        for term in [name] + aliases:
            local_patterns.append((re.compile(rf"\b{re.escape(term)}\b", re.I), eid))
    for name, aliases in GENERIC_INSTRUMENTS.items():
        eid = stable_id("ENTITY", "instrument_type", name)
        entities.append({"entity_id": eid, "name": name, "entity_type": "instrument_type", "aliases": aliases, "source_is_untrusted_data": True})
        for term in aliases:
            local_patterns.append((re.compile(rf"\b{re.escape(term)}\b", re.I), eid))
    instrument_entities, instrument_patterns = load_instrument_terms(args.instrument_records)
    entities.extend(instrument_entities)

    duplicate_pages: dict[str, str] = {}
    duplicate_chunks: dict[str, str] = {}
    document_lookup: dict[tuple[str, int, int], str] = {}
    parent_document_lookup: dict[str, str] = {}
    totals = Counter()
    for pdf_index, pdf in enumerate(pdfs, 1):
        print(f"[{pdf_index}/{len(pdfs)}] Reading {pdf.name}", flush=True)
        source_sha = sha_file(pdf)
        source_key = source_sha[:12]
        source_id = f"COSZO-SOURCE-{source_sha[:16]}"
        document_id = stable_id("COSZO-DOC", source_sha)
        reader = PdfReader(str(pdf), strict=False)
        page_count = len(reader.pages)
        title = title_from_metadata(reader, pdf)
        visual_doc = pdf.name in VISUAL_DOCUMENTS
        source_records.append({
            "source_id": source_id,
            "filename": pdf.name,
            "relative_path": f"../{pdf.name}",
            "media_type": "application/pdf",
            "sha256": source_sha,
            "byte_size": pdf.stat().st_size,
            "page_count": page_count,
            "rights": "unknown; preserve source terms",
            "source_is_untrusted_data": True,
        })
        parent_document_lookup[pdf.name] = document_id
        documents.append({
            "document_id": document_id,
            "source_id": source_id,
            "title": title,
            "document_type": DOCUMENT_TYPES.get(pdf.name, "pdf_document"),
            "page_count": page_count,
            "is_composite": pdf.name == "COSZO Project DataMSRI.pdf",
            "scope": "COSZO/RCA source folder" if pdf.name != "RIG nsf21107.pdf" else "external infrastructure reference retained from COSZO source folder",
            "source_is_untrusted_data": True,
        })
        add_relationship(relationships, rel_seen, document_id, "DERIVED_FROM", source_id)
        logical_ranges = DATAMSRI_LOGICAL_RANGES if pdf.name == "COSZO Project DataMSRI.pdf" else []
        for range_start, range_end, range_title in logical_ranges:
            logical_id = stable_id("COSZO-DOC", source_sha, range_start, range_end, range_title)
            document_lookup[(pdf.name, range_start, range_end)] = logical_id
            documents.append({
                "document_id": logical_id,
                "source_id": source_id,
                "parent_document_id": document_id,
                "title": f"{title}: {range_title}",
                "document_type": "logical_packet_section",
                "page_start": range_start,
                "page_end": range_end,
                "page_count": range_end - range_start + 1,
                "is_composite": False,
                "scope": "COSZO project packet logical section",
                "source_is_untrusted_data": True,
            })
            add_relationship(relationships, rel_seen, document_id, "HAS_PART", logical_id, {"page_start": range_start, "page_end": range_end})
            add_relationship(relationships, rel_seen, logical_id, "DERIVED_FROM", source_id)
        rendered = render_pdf(pdf, output_dir / "page_images", source_key, page_count, args.dpi)
        doc_md = [f"# {title}", "", f"Source: `{pdf.name}`", f"Document ID: `{document_id}`", ""]
        previous_page_id = None
        previous_chunk_id = None
        for page_index, (pdf_page, image_path) in enumerate(zip(reader.pages, rendered), 1):
            try:
                native = clean_text(pdf_page.extract_text() or "")
            except Exception as exc:
                native = ""
                print(f"  page {page_index}: native extraction failed: {exc}", file=sys.stderr, flush=True)
            native_chars = len(compact(native))
            datamsri_visual = pdf.name == "COSZO Project DataMSRI.pdf" and (
                90 <= page_index <= 96 or 137 <= page_index <= 146 or 325 <= page_index <= 524
            )
            should_ocr = native_chars < args.ocr_below_chars or visual_doc or datamsri_visual or bool(VISUAL_RE.search(native))
            ocr, ocr_conf = ("", None)
            if should_ocr:
                try:
                    ocr, ocr_conf = tesseract_ocr(image_path)
                except subprocess.CalledProcessError as exc:
                    print(f"  page {page_index}: OCR failed ({exc})", file=sys.stderr, flush=True)
            selected, method = select_text(native, ocr, visual_doc)
            selected_chars = len(compact(selected))
            is_scan = native_chars < 30 and len(compact(ocr)) >= 60
            page_id = f"COSZO-PAGE-{source_key}-{page_index:04d}"
            logical_document_id = document_id
            for range_start, range_end, _ in logical_ranges:
                if range_start <= page_index <= range_end:
                    logical_document_id = document_lookup[(pdf.name, range_start, range_end)]
                    break
            with Image.open(image_path) as im:
                image_width, image_height = im.size
            image_sha = sha_file(image_path)
            page_hash = normalized_hash(selected) if selected_chars >= 100 else None
            page_record = {
                "page_id": page_id,
                "document_id": logical_document_id,
                "parent_document_id": document_id if logical_document_id != document_id else None,
                "source_id": source_id,
                "page_number": page_index,
                "locator": f"{pdf.name}#page={page_index}",
                "native_text": native,
                "ocr_text": ocr,
                "selected_text": selected,
                "extraction_method": method,
                "native_character_count": native_chars,
                "ocr_character_count": len(compact(ocr)),
                "selected_character_count": selected_chars,
                "selected_word_count": word_count(selected),
                "ocr_attempted": should_ocr,
                "ocr_mean_confidence": ocr_conf,
                "is_scan": is_scan,
                "is_visual_document": visual_doc,
                "page_image_path": str(image_path.relative_to(output_dir)),
                "page_image_sha256": image_sha,
                "image_width_px": image_width,
                "image_height_px": image_height,
                "render_dpi": args.dpi,
                "text_sha256": page_hash,
                "source_is_untrusted_data": True,
            }
            pages.append(page_record)
            add_relationship(relationships, rel_seen, logical_document_id, "HAS_PAGE", page_id, {"page_number": page_index})
            if previous_page_id:
                add_relationship(relationships, rel_seen, previous_page_id, "NEXT_PAGE", page_id)
            previous_page_id = page_id
            if page_hash:
                if page_hash in duplicate_pages:
                    add_relationship(relationships, rel_seen, page_id, "SAME_CONTENT_AS", duplicate_pages[page_hash], {"basis": "normalized selected text SHA-256"})
                    totals["duplicate_pages"] += 1
                else:
                    duplicate_pages[page_hash] = page_id

            page_is_figure = visual_doc or datamsri_visual or is_scan or bool(VISUAL_RE.search(native)) or (should_ocr and selected_chars < 500)
            if page_is_figure:
                figure_id = f"COSZO-FIG-{source_key}-p{page_index:04d}-001"
                figure_path = output_dir / "figures" / f"{figure_id}.jpg"
                if not figure_path.exists():
                    try:
                        os.link(image_path, figure_path)
                    except OSError:
                        shutil.copy2(image_path, figure_path)
                if pdf.name.endswith("poster_SSA_2022_afd2.pdf"):
                    visual_type = "poster"
                elif "Visio" in pdf.name:
                    visual_type = "data_flow_diagram"
                elif pdf.name.startswith("CASIE"):
                    visual_type = "map"
                elif visual_doc:
                    visual_type = "presentation_slide"
                elif is_scan:
                    visual_type = "full_page_scan"
                else:
                    visual_type = "page_visual"
                figures.append({
                    "figure_id": figure_id,
                    "document_id": logical_document_id,
                    "page_id": page_id,
                    "source_id": source_id,
                    "page_number": page_index,
                    "visual_type": visual_type,
                    "image_path": str(figure_path.relative_to(output_dir)),
                    "image_sha256": image_sha,
                    "caption_or_page_text": compact(selected)[:4000],
                    "ocr_text": ocr,
                    "representation": "full-page render preserving text, figures, tables, and spatial context",
                    "source_is_untrusted_data": True,
                })
                add_relationship(relationships, rel_seen, page_id, "HAS_FIGURE", figure_id)

            page_chunks = chunk_text(selected)
            for ordinal, chunk_value in enumerate(page_chunks, 1):
                chunk_id = stable_id("COSZO-CHUNK", page_id, ordinal, chunk_value)
                chunk_hash = normalized_hash(chunk_value)
                mentioned = mention_entities(chunk_value, local_patterns, instrument_patterns)
                chunks.append({
                    "chunk_id": chunk_id,
                    "document_id": logical_document_id,
                    "page_id": page_id,
                    "source_id": source_id,
                    "page_number": page_index,
                    "chunk_ordinal_on_page": ordinal,
                    "locator": f"{pdf.name}#page={page_index}",
                    "text": chunk_value,
                    "word_count": word_count(chunk_value),
                    "text_sha256": chunk_hash,
                    "extraction_method": method,
                    "entity_ids": mentioned,
                    "source_is_untrusted_data": True,
                })
                add_relationship(relationships, rel_seen, page_id, "HAS_CHUNK", chunk_id)
                if previous_chunk_id:
                    add_relationship(relationships, rel_seen, previous_chunk_id, "NEXT_CHUNK", chunk_id)
                previous_chunk_id = chunk_id
                for eid in mentioned:
                    add_relationship(relationships, rel_seen, chunk_id, "MENTIONS", eid, {"locator": f"{pdf.name}#page={page_index}"})
                if len(chunk_value) >= 100:
                    if chunk_hash in duplicate_chunks:
                        add_relationship(relationships, rel_seen, chunk_id, "SAME_CONTENT_AS", duplicate_chunks[chunk_hash], {"basis": "normalized chunk text SHA-256"})
                        totals["duplicate_chunks"] += 1
                    else:
                        duplicate_chunks[chunk_hash] = chunk_id
            doc_md.extend([f"## Page {page_index}", "", selected or "*[No machine-readable text; see page image.]*", ""])
            totals["pages"] += 1
            totals["ocr_attempted"] += int(should_ocr)
            totals["ocr_selected"] += int(method in {"ocr", "hybrid_native_ocr"})
            totals["scan_pages"] += int(is_scan)
        text_path = output_dir / "text" / f"{source_key}-{re.sub(r'[^a-z0-9]+', '-', pdf.stem.casefold()).strip('-')}.md"
        text_path.write_text("\n".join(doc_md).strip() + "\n", encoding="utf-8")

    # Known whole-section duplication/version relationships discovered during the PDF audit.
    packet_icd = document_lookup.get(("COSZO Project DataMSRI.pdf", 127, 136))
    packet_icd_copy = document_lookup.get(("COSZO Project DataMSRI.pdf", 239, 248))
    packet_description = document_lookup.get(("COSZO Project DataMSRI.pdf", 2, 31))
    standalone_description = parent_document_lookup.get("COSZO_Description.pdf")
    packet_pep = document_lookup.get(("COSZO Project DataMSRI.pdf", 48, 89))
    concept = parent_document_lookup.get("ConceptOfOperations_PEP1.3_version.pdf")
    if packet_icd and packet_icd_copy:
        add_relationship(relationships, rel_seen, packet_icd_copy, "DUPLICATE_OF", packet_icd, {"confidence": "high", "basis": "PDF content audit"})
    if packet_description and standalone_description:
        add_relationship(relationships, rel_seen, packet_description, "DUPLICATE_OF", standalone_description, {"confidence": 0.997, "basis": "mean normalized page similarity"})
    if concept and packet_pep:
        add_relationship(relationships, rel_seen, concept, "UPDATES", packet_pep, {"basis": "overlapping revised concept-of-operations content"})

    # Keep only instrument projections that are actually referenced.
    referenced = {rel["target_id"] for rel in relationships if rel["relationship_type"] == "MENTIONS"}
    entity_by_id = {e["entity_id"]: e for e in entities}
    entities = [e for eid, e in entity_by_id.items() if e["entity_type"] != "instrument" or eid in referenced]

    write_jsonl(output_dir / "source_documents.jsonl", source_records)
    write_jsonl(output_dir / "documents.jsonl", documents)
    write_jsonl(output_dir / "pages.jsonl", pages)
    write_jsonl(output_dir / "chunks.jsonl", chunks)
    write_jsonl(output_dir / "figures.jsonl", figures)
    write_jsonl(output_dir / "entities.jsonl", entities)
    write_jsonl(output_dir / "relationships.jsonl", relationships)

    all_ids = {r[k] for records, k in [
        (source_records, "source_id"), (documents, "document_id"), (pages, "page_id"),
        (chunks, "chunk_id"), (figures, "figure_id"), (entities, "entity_id"),
    ] for r in records}
    unresolved = sorted({x for rel in relationships for x in (rel["source_id"], rel["target_id"]) if x not in all_ids})
    page_images_missing = [p["page_id"] for p in pages if not (output_dir / p["page_image_path"]).exists()]
    figures_missing = [f["figure_id"] for f in figures if not (output_dir / f["image_path"]).exists()]
    uncovered = []
    chunks_by_page = Counter(c["page_id"] for c in chunks)
    figures_by_page = Counter(f["page_id"] for f in figures)
    for p in pages:
        if not chunks_by_page[p["page_id"]] and not figures_by_page[p["page_id"]]:
            uncovered.append(p["page_id"])
    expected_pages = sum(s["page_count"] for s in source_records)
    checks = {
        "all_source_pdfs_included": len(source_records) == len(pdfs),
        "page_count_matches_sources": len(pages) == expected_pages,
        "all_page_images_exist": not page_images_missing,
        "all_figure_images_exist": not figures_missing,
        "all_relationship_endpoints_resolve": not unresolved,
        "every_page_has_text_chunk_or_figure": not uncovered,
        "all_low_text_pages_ocr_attempted": all(p["ocr_attempted"] for p in pages if p["native_character_count"] < args.ocr_below_chars),
    }
    validation = {
        "status": "pass" if all(checks.values()) else "fail",
        "schema_version": SCHEMA_VERSION,
        "checks": checks,
        "counts": {
            "source_documents": len(source_records), "documents": len(documents), "pages": len(pages),
            "chunks": len(chunks), "figures": len(figures), "entities": len(entities),
            "relationships": len(relationships), "ocr_attempted_pages": totals["ocr_attempted"],
            "ocr_or_hybrid_selected_pages": totals["ocr_selected"], "scan_pages": totals["scan_pages"],
            "duplicate_pages_linked": totals["duplicate_pages"], "duplicate_chunks_linked": totals["duplicate_chunks"],
        },
        "problems": {
            "missing_page_images": page_images_missing,
            "missing_figure_images": figures_missing,
            "unresolved_relationship_endpoints": unresolved,
            "uncovered_pages": uncovered,
        },
    }
    (output_dir / "validation_report.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "corpus_id": "COSZO-PDF-GRAPHRAG",
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_directory": str(source_dir),
        "source_count": len(source_records),
        "page_count": len(pages),
        "files": {
            name: {"sha256": sha_file(output_dir / name), "records": sum(1 for _ in (output_dir / name).open(encoding="utf-8"))}
            for name in ["source_documents.jsonl", "documents.jsonl", "pages.jsonl", "chunks.jsonl", "figures.jsonl", "entities.jsonl", "relationships.jsonl"]
        },
        "validation_status": validation["status"],
        "source_is_untrusted_data": True,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    readme = f"""# COSZO PDF Graph RAG corpus

This package preserves all {len(source_records)} source PDFs and all {len(pages)} pages as provenance-linked Graph RAG records. The original PDFs remain one directory above this package.

## Runtime files

- `source_documents.jsonl`: immutable source metadata and hashes
- `documents.jsonl`: logical PDF documents
- `pages.jsonl`: native text, OCR text, selected text, extraction quality, and page-image provenance
- `chunks.jsonl`: page-bounded retrieval chunks with exact locators
- `figures.jsonl`: visual-page records for scans, slides, maps, diagrams, posters, and figure-bearing pages
- `entities.jsonl`: projects, places, instrument types, and linked instrument inventory projections
- `relationships.jsonl`: graph edges (`DERIVED_FROM`, `HAS_PAGE`, `NEXT_PAGE`, `HAS_CHUNK`, `NEXT_CHUNK`, `HAS_FIGURE`, `MENTIONS`, `SAME_CONTENT_AS`)
- `text/`: readable Markdown transcriptions by PDF
- `page_images/`: JPEG render of every page at {args.dpi} DPI
- `figures/`: hard-linked or copied visual-page images; semantic visual records point here
- `validation_report.json`: structural and referential-integrity checks
- `manifest.json`: corpus counts, hashes, and schema version

## Ingestion

Embed `chunks.jsonl.text`. Use `entity_ids`, `page_id`, `document_id`, and `source_id` as graph joins. Ingest `entities.jsonl` as nodes and `relationships.jsonl` as edges. Keep `pages.jsonl` and `figures.jsonl` available to multimodal retrieval and citations. Every retrieval result can resolve to `filename#page=N` through its source and page records.

OCR is attempted for every page with fewer than {args.ocr_below_chars} native characters and for visual documents or pages that mention figures, maps, diagrams, or tables. Raw native and OCR text are retained separately; `selected_text` records which representation is used for retrieval.
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(validation, indent=2), flush=True)
    if validation["status"] != "pass":
        raise SystemExit(2)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-dir", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--instrument-records", type=Path)
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--ocr-below-chars", type=int, default=200)
    ap.add_argument("--overwrite", action="store_true")
    return ap.parse_args()


if __name__ == "__main__":
    build(parse_args())
