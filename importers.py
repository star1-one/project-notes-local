"""Offline, bounded document text extraction for Project Desk.

Text, mail, DOCX and HWPX use only Python's standard library. PDF extraction
uses optional pypdf (in the bundled desktop Python) or a local pdftotext.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
MAX_ARCHIVE_BYTES = 60 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 2000
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".log"}


class ImportErrorUser(ValueError):
    """An actionable import error safe to display to the user."""


def _clean(text: str) -> str:
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    # XML/HTML can contain formatting whitespace, but paragraph boundaries matter.
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{4,}", "\n\n\n", text).strip()


def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        codecs = ("utf-16",)
    elif data.startswith(b"\xef\xbb\xbf"):
        codecs = ("utf-8-sig",)
    elif b"\x00" in data[:4096]:
        raise ImportErrorUser("텍스트 인코딩을 확인할 수 없습니다. UTF-8 텍스트로 저장한 뒤 다시 넣어 주세요.")
    else:
        codecs = ("utf-8", "cp949")
    for encoding in codecs:
        try:
            value = data.decode(encoding)
            if "\x00" in value:
                raise ImportErrorUser("텍스트 파일에 바이너리 데이터가 포함되어 있습니다.")
            return value
        except UnicodeDecodeError:
            continue
    raise ImportErrorUser("텍스트를 읽을 수 없습니다. UTF-8 또는 CP949 텍스트로 저장해 주세요.")


class _HTMLText(HTMLParser):
    BLOCKS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "blockquote", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if not self.hidden and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in self.BLOCKS:
            self.parts.append("\n")
        elif not self.hidden and tag in {"td", "th"}:
            self.parts.append("\t")

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)


def _html_text(value: str) -> str:
    parser = _HTMLText()
    parser.feed(value)
    return _clean("".join(parser.parts))


def _email_text(data: bytes) -> tuple[str, list[str]]:
    msg = BytesParser(policy=policy.default).parsebytes(data)
    headers = [f"{label}: {msg.get(field, '')}" for label, field in [("제목", "subject"), ("보낸 사람", "from"), ("받는 사람", "to"), ("날짜", "date")] if msg.get(field)]
    body = msg.get_body(preferencelist=("plain", "html"))
    if body is None:
        raise ImportErrorUser("메일에서 읽을 수 있는 본문을 찾지 못했습니다. 메일 본문을 직접 붙여 넣어 주세요.")
    try:
        content = body.get_content()
    except (LookupError, UnicodeError) as exc:
        raise ImportErrorUser("메일 본문 인코딩을 읽을 수 없습니다. 본문을 직접 붙여 넣어 주세요.") from exc
    if not isinstance(content, str):
        raise ImportErrorUser("메일 본문을 텍스트로 읽을 수 없습니다. 본문을 직접 붙여 넣어 주세요.")
    if body.get_content_type() == "text/html":
        content = _html_text(content)
    if not content.strip():
        raise ImportErrorUser("메일 본문이 비어 있습니다. 본문이 있는 메일을 넣어 주세요.")
    warnings = ["메일 첨부파일은 별도 자료로 추가해 주세요."] if any(msg.iter_attachments()) else []
    return "\n".join(headers) + "\n\n" + content, warnings


def _open_archive(data: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_ENTRIES or sum(item.file_size for item in entries) > MAX_ARCHIVE_BYTES:
            archive.close()
            raise ImportErrorUser("문서의 압축 해제 크기가 너무 큽니다. 필요한 부분을 텍스트나 PDF로 나눠 넣어 주세요.")
        if any(item.flag_bits & 1 for item in entries):
            archive.close()
            raise ImportErrorUser("암호가 걸린 문서는 읽을 수 없습니다. 암호를 해제한 사본을 넣어 주세요.")
        return archive
    except (zipfile.BadZipFile, OSError) as exc:
        raise ImportErrorUser("문서 파일이 손상되었거나 형식이 맞지 않습니다. 다시 저장한 뒤 넣어 주세요.") from exc


def _xml_root(data: bytes):
    # DTDs/entities are unnecessary for office documents. Reject them explicitly.
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ImportErrorUser("외부 엔터티를 포함한 문서는 지원하지 않습니다.")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ImportErrorUser("문서 본문 구조를 읽을 수 없습니다. 다시 저장한 뒤 넣어 주세요.") from exc


def _office_text(data: bytes, extension: str) -> tuple[str, list[str]]:
    with _open_archive(data) as archive:
        names = archive.namelist()
        if extension == ".docx":
            sections = ["word/document.xml"] if "word/document.xml" in names else []
        else:
            sections = sorted((n for n in names if re.fullmatch(r"Contents/section\d+\.xml", n)), key=lambda n: int(re.search(r"section(\d+)", n).group(1)))
        if not sections:
            raise ImportErrorUser("문서에서 본문을 찾지 못했습니다. DOCX/HWPX 형식으로 다시 저장해 주세요.")
        parts: list[str] = []

        def visit(node):
            tag = node.tag.rsplit("}", 1)[-1]
            if tag == "t":
                parts.append(node.text or "")
            elif tag in {"tab", "tabChar"}:
                parts.append("\t")
            elif tag in {"br", "lineBreak", "cr"}:
                parts.append("\n")
            for child in node:
                visit(child)
                # HWPX stores text following inline controls (lineBreak/tab)
                # in the control's tail, not in the enclosing t node's text.
                # Preserve that mixed-content order so dates and amounts after
                # a control cannot silently disappear during import.
                parts.append(child.tail or "")
            if tag in {"p", "tr"}:
                parts.append("\n")
            elif tag == "tc":
                parts.append("\t")

        try:
            for section in sections:
                visit(_xml_root(archive.read(section)))
                parts.append("\n")
        except (RuntimeError, zipfile.BadZipFile, OSError, RecursionError) as exc:
            raise ImportErrorUser("문서 본문을 읽지 못했습니다. 다시 저장한 파일을 넣어 주세요.") from exc
        warnings = []
        if any("/media/" in name or name.startswith("BinData/") for name in names):
            warnings.append("문서의 이미지 안 글자와 도표는 추출하지 않았습니다. 중요한 내용은 텍스트로 함께 넣어 주세요.")
        return "".join(parts), warnings


_PDF_WORKER = r'''
import io, json, sys
try:
    from pypdf import PdfReader
except ImportError:
    sys.exit(43)
try:
    reader = PdfReader(io.BytesIO(sys.stdin.buffer.read()))
    if reader.is_encrypted and not reader.decrypt(""):
        print(json.dumps({"error": "암호가 걸린 PDF입니다. 암호를 해제한 사본을 넣어 주세요."}))
        sys.exit(0)
    if len(reader.pages) > 2000:
        print(json.dumps({"error": "PDF 페이지가 너무 많습니다. 2,000쪽 이하로 나눠 넣어 주세요."}))
        sys.exit(0)
    parts, size = [], 0
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        size += len(text)
        if size > 2000000:
            print(json.dumps({"error": "추출한 텍스트가 너무 깁니다. 문서를 나눠 넣어 주세요."}))
            sys.exit(0)
        if text.strip():
            parts.append("[PDF %s쪽]\n%s" % (number, text))
    print(json.dumps({"text": "\n\n".join(parts)}, ensure_ascii=False))
except Exception:
    print(json.dumps({"error": "PDF를 읽지 못했습니다. 파일을 다시 저장하거나 텍스트를 직접 넣어 주세요."}))
'''


def _pdf_text(data: bytes) -> tuple[str, list[str]]:
    if not data.startswith(b"%PDF-"):
        raise ImportErrorUser("올바른 PDF 파일이 아닙니다.")
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
    candidates = [os.environ.get("PROJECT_DESK_PDF_PYTHON"), sys.executable, str(bundled)]
    for executable in dict.fromkeys(candidate for candidate in candidates if candidate):
        if not Path(executable).is_file():
            continue
        try:
            result = subprocess.run([executable, "-c", _PDF_WORKER], input=data, capture_output=True, timeout=45, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ImportErrorUser("PDF 읽기가 45초를 초과했습니다. 필요한 쪽만 나눠 넣어 주세요.") from exc
        except OSError:
            continue
        if result.returncode == 43:
            continue
        try:
            payload = json.loads(result.stdout)
        except (ValueError, UnicodeError) as exc:
            raise ImportErrorUser("PDF 추출을 완료하지 못했습니다. 문서를 나눠 다시 넣어 주세요.") from exc
        if payload.get("error"):
            raise ImportErrorUser(payload["error"])
        text = _clean(payload.get("text", ""))
        if not text:
            raise ImportErrorUser("PDF에서 텍스트를 찾지 못했습니다. 스캔 문서는 OCR 처리 후 넣거나 내용을 직접 붙여 넣어 주세요.")
        return text, ["PDF의 이미지 안 글자는 추출하지 않았습니다. 스캔 페이지에는 OCR이 필요합니다."]

    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        with tempfile.TemporaryDirectory(prefix="project-desk-pdf-") as folder:
            path = Path(folder) / "input.pdf"
            path.write_bytes(data)
            try:
                result = subprocess.run([pdftotext, "-layout", "-enc", "UTF-8", str(path), "-"], capture_output=True, timeout=45, check=False)
            except (subprocess.TimeoutExpired, OSError) as exc:
                raise ImportErrorUser("PDF를 읽지 못했습니다. 필요한 부분만 나눠 넣어 주세요.") from exc
            text = result.stdout.decode("utf-8", errors="replace")
            if result.returncode or not text.strip():
                raise ImportErrorUser("PDF에서 텍스트를 찾지 못했습니다. OCR 처리 후 넣거나 내용을 직접 붙여 넣어 주세요.")
            return text, ["PDF 이미지 안 글자는 별도의 OCR이 필요합니다."]
    raise ImportErrorUser("PDF 읽기에 pypdf가 필요합니다. 앱 폴더에서 python3 -m pip install -r requirements.txt 실행 후 다시 열거나 본문을 붙여 넣어 주세요.")


def extract_file(filename: str, data: bytes) -> tuple[str, list[str]]:
    """Extract a supported file without writing its contents outside temp storage."""
    if not isinstance(filename, str) or not filename.strip():
        raise ImportErrorUser("파일 이름이 필요합니다.")
    if not isinstance(data, bytes):
        raise ImportErrorUser("파일 데이터를 읽을 수 없습니다.")
    if len(data) > MAX_FILE_BYTES:
        raise ImportErrorUser("파일은 한 번에 20MB까지 넣을 수 있습니다. 문서를 나눠 넣어 주세요.")
    if not data:
        raise ImportErrorUser("파일이 비어 있습니다.")
    extension = Path(filename).suffix.lower()
    warnings: list[str] = []
    if extension in TEXT_EXTENSIONS:
        text = _decode(data)
    elif extension in {".html", ".htm"}:
        text = _html_text(_decode(data))
    elif extension == ".eml":
        text, warnings = _email_text(data)
    elif extension in {".docx", ".hwpx"}:
        text, warnings = _office_text(data, extension)
    elif extension == ".pdf":
        text, warnings = _pdf_text(data)
    elif extension == ".hwp":
        raise ImportErrorUser("HWP 파일은 한글에서 HWPX 또는 텍스트가 포함된 PDF로 저장한 뒤 넣어 주세요.")
    else:
        raise ImportErrorUser("지원하는 파일: TXT, MD, CSV, TSV, JSON, LOG, EML, HTML, DOCX, HWPX, PDF입니다.")
    text = _clean(text)
    if not text:
        raise ImportErrorUser("파일에서 읽을 수 있는 텍스트를 찾지 못했습니다. 본문을 직접 붙여 넣어 주세요.")
    if len(text) > MAX_TEXT_CHARS:
        raise ImportErrorUser("추출한 텍스트가 200만 자를 넘습니다. 문서를 나눠 넣어 주세요.")
    return text, warnings
