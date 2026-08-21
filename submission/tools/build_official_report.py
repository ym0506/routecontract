#!/usr/bin/env python3
"""Build RouteContract's report from the organizer's retained DOCX template."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.parse
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image as PillowImage
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RELATIONSHIP_TYPE
from docx.shared import Inches, Pt, RGBColor
from docx.text.run import Run
from lxml import etree

try:
    from .report_ooxml import mark_data_rows_cannot_split
    from .report_content_contract import materialize_external_evidence
except ImportError:  # Direct script execution puts this directory on sys.path.
    from report_ooxml import mark_data_rows_cannot_split
    from report_content_contract import materialize_external_evidence


EXPECTED_TEMPLATE_SHA256 = (
    "937679bac40cbfaced3457530c232c9d190a74f6b5d67c58b4bc33014a579195"
)
FONT_NAME = "Malgun Gothic"
BODY_FONT_PT = 10
REPORT_IMAGE_WIDTH_INCHES = 4.15
# The organizer's supplemental guide caps the prioritized summary at ten rows.
# Compact nine-point cells keep that landscape table readable while the body
# remains the required 10 pt.
SBOM_FONT_PT = 9
SBOM_MAX_ROWS = 10
PLACEHOLDER_RE = re.compile(r"\[\[[^\]]+\]\]")
CORE_PROPERTY_NAMESPACES = {
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
}
PUBLIC_DOCUMENT_IDENTITY = "RouteContract project"
UPSTREAM_ISSUE_38456_URL = "https://github.com/apache/shardingsphere/issues/38456"
EXTERNAL_LINK_ALIASES = {
    "[결과 Issue]": "result_issue_url",
    "[활성화 기록]": "activation_record_url",
    "[모집 기록]": "recruitment_record_url",
    "[검증 프로토콜]": "protocol_issue_url",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument(
        "--assets-dir",
        type=Path,
        help="PNG directory; defaults to an assets directory beside --content",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--strict-final",
        action="store_true",
        help="refuse to build while any [[submission gate]] remains",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_content(path: Path, *, strict: bool) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        data = json.load(stream)
    required = {
        "metadata",
        "assets",
        "project_intro",
        "background",
        "environment",
        "architecture",
        "features",
        "effects",
        "other",
        "external_evidence",
        "sbom",
    }
    missing = sorted(required.difference(data))
    unexpected = sorted(set(data).difference(required))
    if missing or unexpected:
        raise ValueError(
            "content keys do not match schema; "
            f"missing={missing}, unexpected={unexpected}"
        )
    rows = data["sbom"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= SBOM_MAX_ROWS:
        raise ValueError(
            f"the official Attachment 1 must contain 1 to {SBOM_MAX_ROWS} prioritized rows"
        )
    expected_row_keys = {"name", "version", "license", "url", "purpose"}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or set(row) != expected_row_keys:
            raise ValueError(
                f"SBOM row {index} must contain exactly: "
                + ", ".join(sorted(expected_row_keys))
            )
        if any(not isinstance(row[key], str) or not row[key].strip() for key in row):
            raise ValueError(f"SBOM row {index} values must be non-empty strings")
    return materialize_external_evidence(data, allow_placeholders=not strict)


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def discovered_https_targets(data: dict[str, Any]) -> set[str]:
    targets: set[str] = set()
    for text in iter_strings(data):
        for raw in re.findall(r"https://\S+", text):
            target = raw.rstrip(".,;:!?)]}'\"")
            parsed = urllib.parse.urlparse(target)
            if parsed.scheme == "https" and parsed.netloc:
                targets.add(target)
    return targets


def validate_submission_gates(data: dict[str, Any], strict: bool) -> None:
    placeholders = sorted(
        {match.group(0) for text in iter_strings(data) for match in PLACEHOLDER_RE.finditer(text)}
    )
    if strict and placeholders:
        formatted = "\n".join(f"- {item}" for item in placeholders)
        raise ValueError(f"unresolved final-submission gates:\n{formatted}")


def resolve_assets(data: dict[str, Any], assets_dir: Path) -> dict[str, Path]:
    expected = {"architecture", "baseline_candidate"}
    specs = data["assets"]
    if set(specs) != expected:
        raise ValueError(f"assets must contain exactly: {', '.join(sorted(expected))}")
    root = assets_dir.resolve()
    resolved: dict[str, Path] = {}
    for key in sorted(expected):
        filename = Path(specs[key]["filename"])
        if filename.is_absolute() or ".." in filename.parts:
            raise ValueError(f"asset filename must stay under --assets-dir: {filename}")
        path = (root / filename).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise ValueError(f"asset escapes --assets-dir: {path}") from error
        if not path.is_file():
            raise FileNotFoundError(f"required report asset is missing: {path}")
        with PillowImage.open(path) as image:
            if image.format != "PNG" or image.size != (1200, 675):
                raise ValueError(
                    f"asset must be a QA-approved 1200x675 PNG: {path} "
                    f"(format={image.format}, size={image.size})"
                )
        resolved[key] = path
    return resolved


def table_text(table) -> str:
    return "\n".join(cell.text for row in table.rows for cell in row.cells)


def find_table(document: Document, predicate):
    for table in document.tables:
        if predicate(table):
            return table
    raise ValueError("required official-template table was not found")


def remove_element(element) -> None:
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def strip_guide_page(document: Document) -> None:
    guide = find_table(document, lambda table: "결과보고서 작성 안내" in table_text(table))
    remove_element(guide._tbl)


def strip_ai_attachment(document: Document) -> None:
    ai_title = find_table(
        document,
        lambda table: "AI 모델 활용 및 라이선스 기술 명세서" in table_text(table),
    )
    body = document.element.body
    children = list(body.iterchildren())
    ai_index = children.index(ai_title._tbl)

    start = ai_index
    while start > 0:
        previous = children[start - 1]
        if previous.tag == qn("w:p") and not "".join(previous.itertext()).strip():
            start -= 1
            continue
        break

    for element in children[start:]:
        if element.tag != qn("w:sectPr"):
            remove_element(element)


def set_run_font(run, size_pt: float, *, bold: bool | None = None) -> None:
    run.font.name = FONT_NAME
    run.font.size = Pt(size_pt)
    run.font.color.rgb = RGBColor(0, 0, 0)
    if bold is not None:
        run.bold = bold
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    for key in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{key}"), FONT_NAME)


def append_hyperlink(paragraph, display: str, target: str, size_pt: float) -> None:
    relationship_id = paragraph.part.relate_to(
        target, RELATIONSHIP_TYPE.HYPERLINK, is_external=True
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    run_element = OxmlElement("w:r")
    hyperlink.append(run_element)
    paragraph._p.append(hyperlink)
    run = Run(run_element, paragraph)
    run.add_text(display)
    set_run_font(run, size_pt, bold=False)
    run.font.color.rgb = RGBColor(5, 99, 193)
    run.underline = True


def append_text_with_hyperlinks(
    paragraph,
    text: str,
    size_pt: float,
    *,
    targets: Iterable[str] = (),
    aliases: dict[str, str] | None = None,
) -> None:
    candidates = [(target, target) for target in targets if target in text]
    candidates.append(("#38456", UPSTREAM_ISSUE_38456_URL))
    if aliases:
        candidates.extend(
            (display, target)
            for display, target in aliases.items()
            if display in text
        )
    matches: list[tuple[int, int, str, str]] = []
    for display, target in candidates:
        start = text.find(display)
        while start >= 0:
            matches.append((start, start + len(display), display, target))
            start = text.find(display, start + len(display))
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    cursor = 0
    for start, end, display, target in matches:
        if start < cursor:
            continue
        if start > cursor:
            run = paragraph.add_run(text[cursor:start])
            set_run_font(run, size_pt, bold=False)
        append_hyperlink(paragraph, display, target, size_pt)
        cursor = end
    if cursor < len(text):
        run = paragraph.add_run(text[cursor:])
        set_run_font(run, size_pt, bold=False)


def set_paragraph_rhythm(paragraph, *, alignment=None, after_pt: float = 1.5) -> None:
    paragraph.alignment = alignment
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(after_pt)
    fmt.line_spacing = 1.0
    fmt.keep_together = False
    fmt.keep_with_next = False
    fmt.widow_control = True


def clear_cell(cell) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    set_paragraph_rhythm(paragraph, after_pt=0)


def set_plain_cell(
    cell,
    text: str,
    *,
    size_pt: float = BODY_FONT_PT,
    bold: bool = False,
    alignment=WD_ALIGN_PARAGRAPH.LEFT,
    hyperlink_target: str | None = None,
) -> None:
    clear_cell(cell)
    paragraph = cell.paragraphs[0]
    set_paragraph_rhythm(paragraph, alignment=alignment, after_pt=0)
    if hyperlink_target is None:
        run = paragraph.add_run(text)
        set_run_font(run, size_pt, bold=bold)
    else:
        append_hyperlink(paragraph, text, hyperlink_target, size_pt)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def set_cell_margins(cell, *, top: int, start: int, bottom: int, end: int) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for name, width in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(width))
        node.set(qn("w:type"), "dxa")


def set_block_cell(
    cell,
    blocks: list[dict[str, str]],
    *,
    image_path: Path | None = None,
    image_caption: str | None = None,
    image_after_block: int | None = None,
    hyperlink_targets: Iterable[str] = (),
    hyperlink_aliases: dict[str, str] | None = None,
) -> None:
    clear_cell(cell)
    first_paragraph = True

    def next_paragraph():
        nonlocal first_paragraph
        paragraph = cell.paragraphs[0] if first_paragraph else cell.add_paragraph()
        first_paragraph = False
        return paragraph

    def append_image() -> None:
        if image_path is None or image_caption is None:
            return
        picture_paragraph = next_paragraph()
        set_paragraph_rhythm(
            picture_paragraph, alignment=WD_ALIGN_PARAGRAPH.CENTER, after_pt=1.0
        )
        picture_paragraph.paragraph_format.keep_with_next = True
        inline_shape = picture_paragraph.add_run().add_picture(
            str(image_path), width=Inches(REPORT_IMAGE_WIDTH_INCHES)
        )
        # python-docx does not expose picture alt text through its public API.
        # Set it on the drawing properties so the evidence figures remain
        # understandable to screen-reader users and survive deterministic rebuilds.
        inline_shape._inline.docPr.set("descr", image_caption)
        inline_shape._inline.docPr.set("title", image_path.stem)
        caption_paragraph = next_paragraph()
        set_paragraph_rhythm(
            caption_paragraph, alignment=WD_ALIGN_PARAGRAPH.CENTER, after_pt=2.0
        )
        caption_paragraph.paragraph_format.keep_together = True
        caption_run = caption_paragraph.add_run(image_caption)
        set_run_font(caption_run, BODY_FONT_PT, bold=False)
        caption_run.italic = True

    if image_path is not None and image_after_block is None:
        append_image()

    for index, block in enumerate(blocks):
        paragraph = next_paragraph()
        set_paragraph_rhythm(paragraph, after_pt=2.0 if index < len(blocks) - 1 else 0)
        lead = block.get("lead", "").strip()
        text = block.get("text", "").strip()
        if lead:
            lead_run = paragraph.add_run(f"{lead}: ")
            set_run_font(lead_run, BODY_FONT_PT, bold=True)
        append_text_with_hyperlinks(
            paragraph,
            text,
            BODY_FONT_PT,
            targets=hyperlink_targets,
            aliases=hyperlink_aliases,
        )
        if image_path is not None and image_after_block == index:
            append_image()
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP


def remove_fixed_row_heights(table) -> None:
    for row in table.rows:
        tr_pr = row._tr.get_or_add_trPr()
        for height in list(tr_pr.findall(qn("w:trHeight"))):
            tr_pr.remove(height)


def mark_repeat_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:tblHeader")) is None:
        tr_pr.append(OxmlElement("w:tblHeader"))


def fill_header_and_metadata(document: Document, data: dict[str, Any]) -> None:
    metadata = find_table(
        document,
        lambda table: len(table.rows) == 3 and table.cell(0, 0).text.strip() == "항    목",
    )
    values = data["metadata"]
    set_plain_cell(metadata.cell(1, 1), values["team_name"])
    set_plain_cell(metadata.cell(1, 3), values["team_size"], alignment=WD_ALIGN_PARAGRAPH.CENTER)
    set_plain_cell(metadata.cell(2, 1), values["division"], alignment=WD_ALIGN_PARAGRAPH.CENTER)
    set_plain_cell(metadata.cell(2, 3), values["task_type"], alignment=WD_ALIGN_PARAGRAPH.CENTER)


def fill_main_report(
    document: Document, data: dict[str, Any], assets: dict[str, Path]
) -> None:
    main = find_table(
        document,
        lambda table: "프로젝트 개요" in table_text(table) and "개발배경 및 목적" in table_text(table),
    )
    values = data["metadata"]
    hyperlink_targets = discovered_https_targets(data)
    evidence = data["external_evidence"]
    hyperlink_aliases = {
        display: evidence[key]
        for display, key in EXTERNAL_LINK_ALIASES.items()
        if isinstance(evidence.get(key), str)
        and evidence[key].startswith("https://")
    }
    set_plain_cell(main.cell(1, 1), values["project_name"], bold=True)
    set_plain_cell(
        main.cell(2, 1), values["repository_url"],
        hyperlink_target=values["repository_url"],
    )
    set_plain_cell(
        main.cell(3, 1), values["video_url"],
        hyperlink_target=values["video_url"],
    )
    set_block_cell(
        main.cell(4, 1), data["project_intro"], hyperlink_targets=hyperlink_targets
    )
    set_block_cell(
        main.cell(6, 1), data["background"], hyperlink_targets=hyperlink_targets
    )
    set_block_cell(
        main.cell(7, 1), data["environment"], hyperlink_targets=hyperlink_targets
    )
    set_block_cell(
        main.cell(8, 1),
        data["architecture"],
        image_path=assets["architecture"],
        image_caption=data["assets"]["architecture"]["caption"],
        hyperlink_targets=hyperlink_targets,
    )
    set_block_cell(
        main.cell(9, 1),
        data["features"],
        image_path=assets["baseline_candidate"],
        image_caption=data["assets"]["baseline_candidate"]["caption"],
        image_after_block=2,
        hyperlink_targets=hyperlink_targets,
    )
    set_block_cell(
        main.cell(10, 1), data["effects"], hyperlink_targets=hyperlink_targets
    )
    set_block_cell(
        main.cell(11, 1),
        data["other"],
        hyperlink_targets=hyperlink_targets,
        hyperlink_aliases=hyperlink_aliases,
    )
    remove_fixed_row_heights(main)


def copy_row(table, row) -> None:
    table._tbl.append(deepcopy(row._tr))


def fill_sbom(document: Document, rows: list[dict[str, str]]) -> None:
    sbom = find_table(
        document,
        lambda table: len(table.columns) == 6 and table.cell(0, 0).text.strip() == "번호",
    )
    while len(sbom.rows) < len(rows) + 1:
        copy_row(sbom, sbom.rows[-1])
    while len(sbom.rows) > len(rows) + 1:
        remove_element(sbom.rows[-1]._tr)

    mark_repeat_header(sbom.rows[0])
    keys = ("name", "version", "license", "url", "purpose")
    for index, item in enumerate(rows, start=1):
        set_plain_cell(
            sbom.cell(index, 0),
            str(index),
            size_pt=SBOM_FONT_PT,
            alignment=WD_ALIGN_PARAGRAPH.CENTER,
        )
        for column, key in enumerate(keys, start=1):
            alignment = WD_ALIGN_PARAGRAPH.LEFT
            if key in {"version", "license"}:
                alignment = WD_ALIGN_PARAGRAPH.CENTER
            set_plain_cell(
                sbom.cell(index, column),
                item[key],
                size_pt=SBOM_FONT_PT,
                alignment=alignment,
                hyperlink_target=item[key] if key == "url" else None,
            )
        for cell in sbom.rows[index].cells:
            set_cell_margins(cell, top=20, start=40, bottom=20, end=40)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.line_spacing = Pt(10.2)
    mark_data_rows_cannot_split(sbom.rows[1:])
    remove_fixed_row_heights(sbom)


def style_retained_paragraphs(document: Document) -> None:
    for paragraph in document.paragraphs:
        if "필요 시, 행을 추가" in paragraph.text:
            remove_element(paragraph._p)


def assert_geometry(document: Document) -> None:
    if len(document.sections) != 2:
        raise ValueError(f"expected 2 official sections, found {len(document.sections)}")
    portrait, landscape = document.sections
    actual = (
        round(portrait.page_width.inches, 2),
        round(portrait.page_height.inches, 2),
        round(portrait.left_margin.inches, 2),
        round(portrait.right_margin.inches, 2),
        round(portrait.top_margin.inches, 2),
        round(portrait.bottom_margin.inches, 2),
        round(landscape.page_width.inches, 2),
        round(landscape.page_height.inches, 2),
        round(landscape.left_margin.inches, 2),
        round(landscape.right_margin.inches, 2),
        round(landscape.top_margin.inches, 2),
        round(landscape.bottom_margin.inches, 2),
    )
    expected = (8.27, 11.69, 1.18, 1.18, 1.38, 1.18, 11.69, 8.27, 0.79, 0.79, 0.98, 0.98)
    if actual != expected:
        raise ValueError(f"official section geometry changed: {actual!r}")


def assert_output_scope(document: Document) -> None:
    all_text = "\n".join(
        [paragraph.text for paragraph in document.paragraphs]
        + [table_text(table) for table in document.tables]
    )
    forbidden = ("결과보고서 작성 안내", "AI 모델 활용 및 라이선스 기술 명세서")
    leaked = [text for text in forbidden if text in all_text]
    if leaked:
        raise ValueError(f"removed official sections leaked into output: {leaked}")
    if len(document.tables) != 5:
        raise ValueError(f"expected exactly 5 retained official tables, found {len(document.tables)}")
    if len(document.inline_shapes) != 2:
        raise ValueError(f"expected exactly 2 report images, found {len(document.inline_shapes)}")
    assert_geometry(document)


def sanitize_core_properties(source: bytes) -> bytes:
    """Remove organizer/person metadata while keeping a deterministic project identity."""
    root = etree.fromstring(source)
    creator = root.find("dc:creator", namespaces=CORE_PROPERTY_NAMESPACES)
    last_modified_by = root.find("cp:lastModifiedBy", namespaces=CORE_PROPERTY_NAMESPACES)
    revision = root.find("cp:revision", namespaces=CORE_PROPERTY_NAMESPACES)
    if creator is None or last_modified_by is None or revision is None:
        raise ValueError("official template core properties are missing required fields")
    creator.text = PUBLIC_DOCUMENT_IDENTITY
    last_modified_by.text = PUBLIC_DOCUMENT_IDENTITY
    revision.text = "1"
    for field in ("dcterms:created", "dcterms:modified"):
        element = root.find(field, namespaces=CORE_PROPERTY_NAMESPACES)
        if element is not None:
            root.remove(element)
    return etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True,
    )


def assert_sanitized_core_properties(output: Path) -> None:
    with ZipFile(output) as package:
        root = etree.fromstring(package.read("docProps/core.xml"))
    creator = root.findtext("dc:creator", namespaces=CORE_PROPERTY_NAMESPACES)
    last_modified_by = root.findtext("cp:lastModifiedBy", namespaces=CORE_PROPERTY_NAMESPACES)
    revision = root.findtext("cp:revision", namespaces=CORE_PROPERTY_NAMESPACES)
    created = root.find("dcterms:created", namespaces=CORE_PROPERTY_NAMESPACES)
    modified = root.find("dcterms:modified", namespaces=CORE_PROPERTY_NAMESPACES)
    if (creator, last_modified_by, revision) != (
        PUBLIC_DOCUMENT_IDENTITY,
        PUBLIC_DOCUMENT_IDENTITY,
        "1",
    ) or created is not None or modified is not None:
        raise ValueError("output DOCX core properties were not privacy-sanitized")


def restore_preserve_only_package_parts(template: Path, output: Path) -> None:
    """Preserve organizer parts except document/image relationships and media."""
    with tempfile.NamedTemporaryFile(
        prefix=f".{output.stem}-", suffix=".docx", dir=output.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
    try:
        with ZipFile(template) as reference, ZipFile(output) as generated, ZipFile(
            temporary, "w", compression=ZIP_DEFLATED
        ) as rebuilt:
            reference_names = set(reference.namelist())
            generated_names = set(generated.namelist())
            removed = reference_names - generated_names
            added = generated_names - reference_names
            unexpected_added = {name for name in added if not name.startswith("word/media/")}
            if removed or unexpected_added:
                raise ValueError(
                    "python-docx changed the official package part set: "
                    f"unexpected_added={sorted(unexpected_added)}, removed={sorted(removed)}"
                )
            editable = {
                "[Content_Types].xml",
                "word/document.xml",
                "word/_rels/document.xml.rels",
                "docProps/core.xml",
            }
            for item in generated.infolist():
                if item.filename in editable or item.filename.startswith("word/media/"):
                    # python-docx stamps rewritten package parts with the build
                    # time. Normalize those ZIP headers so identical inputs
                    # produce a byte-identical report across repeated builds.
                    item.date_time = (1980, 1, 1, 0, 0, 0)
                    content = generated.read(item.filename)
                    if item.filename == "docProps/core.xml":
                        content = sanitize_core_properties(content)
                    rebuilt.writestr(item, content)
                else:
                    reference_item = reference.getinfo(item.filename)
                    rebuilt.writestr(reference_item, reference.read(item.filename))
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> None:
    args = parse_args()
    template = args.template.resolve()
    content_path = args.content.resolve()
    assets_dir = (
        args.assets_dir.resolve() if args.assets_dir else (content_path.parent / "assets").resolve()
    )
    output = args.output.resolve()

    actual_hash = sha256(template)
    if actual_hash != EXPECTED_TEMPLATE_SHA256:
        raise ValueError(
            "official template SHA-256 mismatch: "
            f"expected {EXPECTED_TEMPLATE_SHA256}, got {actual_hash}"
        )

    data = load_content(content_path, strict=args.strict_final)
    validate_submission_gates(data, args.strict_final)
    assets = resolve_assets(data, assets_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output == template:
        raise ValueError("output must not overwrite the retained official template")
    shutil.copy2(template, output)

    document = Document(output)
    strip_guide_page(document)
    strip_ai_attachment(document)
    fill_header_and_metadata(document, data)
    fill_main_report(document, data, assets)
    fill_sbom(document, data["sbom"])
    style_retained_paragraphs(document)
    assert_output_scope(document)
    document.save(output)
    restore_preserve_only_package_parts(template, output)
    assert_sanitized_core_properties(output)

    verified = Document(output)
    assert_output_scope(verified)
    print(f"built={output}")
    print(f"sha256={sha256(output)}")


if __name__ == "__main__":
    main()
