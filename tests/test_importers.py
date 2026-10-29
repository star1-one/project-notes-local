import io
import json
import unittest
import zipfile
from email.message import EmailMessage
from unittest import mock

import importers


def archive(entries):
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as document:
        for filename, value in entries.items():
            document.writestr(filename, value)
    return result.getvalue()


class ImporterTests(unittest.TestCase):
    def test_korean_encodings_are_lossless(self):
        content = "과제 1 협약 변경\n제출 기한: 10월 30일"
        for encoding in ("utf-8-sig", "utf-16", "cp949"):
            with self.subTest(encoding=encoding):
                self.assertEqual(importers.extract_file("사업계획서.TXT", content.encode(encoding))[0], content)

    def test_wrong_type_binary_and_empty_not_silently_accepted(self):
        for name, data in [("empty.txt", b""), ("script.exe", b"MZ"), ("binary.txt", b"abc\x00xyz"), ("bad.txt", b"\xff\xff")]:
            with self.subTest(name=name), self.assertRaises(importers.ImportErrorUser):
                importers.extract_file(name, data)

    def test_size_limits(self):
        with mock.patch.object(importers, "MAX_FILE_BYTES", 3), self.assertRaises(importers.ImportErrorUser):
            importers.extract_file("test.txt", b"1234")
        with mock.patch.object(importers, "MAX_TEXT_CHARS", 3), self.assertRaises(importers.ImportErrorUser):
            importers.extract_file("test.txt", b"1234")

    def test_html_script_style_not_imported(self):
        text, _ = importers.extract_file("mail.html", "<style>hidden</style><p>첫 문단</p><script>bad()</script><p>둘째 &amp; 셋째</p>".encode())
        self.assertEqual(text, "첫 문단\n\n둘째 & 셋째")

    def test_docx_paragraphs_and_tables(self):
        xml = '<w:document xmlns:w="urn:word"><w:body><w:p><w:r><w:t>과제 문서</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>예산</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>100만원</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'
        text, _ = importers.extract_file("plan.docx", archive({"word/document.xml": xml}))
        self.assertIn("과제 문서\n", text)
        self.assertIn("예산", text)
        self.assertIn("100만원", text)

    def test_hwpx_sections_numeric_order(self):
        def xml(value):
            return '<hs:sec xmlns:hs="urn:sec" xmlns:hp="urn:p"><hp:p><hp:run><hp:t>' + value + '</hp:t></hp:run></hp:p></hs:sec>'
        text, warnings = importers.extract_file("plan.hwpx", archive({"Contents/section10.xml": xml("열"), "Contents/section2.xml": xml("둘"), "Contents/section0.xml": xml("처음"), "BinData/image.png": b"fake"}))
        self.assertLess(text.index("처음"), text.index("둘"))
        self.assertLess(text.index("둘"), text.index("열"))
        self.assertTrue(warnings)

    def test_hwpx_text_after_inline_controls_is_preserved_in_order(self):
        xml = '<hs:sec xmlns:hs="urn:sec" xmlns:hp="urn:p"><hp:p><hp:run><hp:t>접수<hp:lineBreak/>마감 11월 3일<hp:tab/>오후 6시<hp:lineBreak/>문의 담당자</hp:t></hp:run></hp:p></hs:sec>'
        text, _ = importers.extract_file("접수.hwpx", archive({"Contents/section0.xml": xml}))
        self.assertEqual(text, "접수\n마감 11월 3일\t오후 6시\n문의 담당자")

    def test_zip_entry_and_uncompressed_limits(self):
        data = archive({"word/document.xml": "<root/>", "padding": "a" * 100})
        with mock.patch.object(importers, "MAX_ARCHIVE_BYTES", 99), self.assertRaises(importers.ImportErrorUser):
            importers.extract_file("plan.docx", data)
        with mock.patch.object(importers, "MAX_ARCHIVE_ENTRIES", 1), self.assertRaises(importers.ImportErrorUser):
            importers.extract_file("plan.docx", data)

    def test_xml_entities_and_invalid_archives_rejected(self):
        with self.assertRaises(importers.ImportErrorUser):
            importers.extract_file("bad.docx", b"not zip")
        data = archive({"word/document.xml": '<!DOCTYPE x [<!ENTITY x "boom">]><x>&x;</x>'})
        with self.assertRaises(importers.ImportErrorUser):
            importers.extract_file("bad.docx", data)

    def test_email_preserves_headers_and_prefers_plain(self):
        msg = EmailMessage()
        msg["Subject"] = "과제 2 제출 요청"
        msg["From"] = "sender@example.com"
        msg["Date"] = "Fri, 30 Oct 2026 09:00:00 +0900"
        msg.set_content("사업계획서 보내 주세요.")
        msg.add_alternative("<p>다른 HTML 본문</p>", subtype="html")
        msg.add_attachment(b"attachment", maintype="application", subtype="octet-stream", filename="data.bin")
        text, warnings = importers.extract_file("request.eml", msg.as_bytes())
        self.assertIn("과제 2 제출 요청", text)
        self.assertIn("sender@example.com", text)
        self.assertIn("사업계획서 보내 주세요.", text)
        self.assertNotIn("다른 HTML 본문", text)
        self.assertTrue(warnings)

    def test_email_html_fallback(self):
        msg = EmailMessage()
        msg.set_content("<p>답장 요청</p>", subtype="html")
        self.assertEqual(importers.extract_file("request.eml", msg.as_bytes())[0], "답장 요청")

    def test_hwp_explains_conversion(self):
        with self.assertRaisesRegex(importers.ImportErrorUser, "HWPX"):
            importers.extract_file("계획.hwp", b"hwp")

    def test_pdf_rejects_invalid_and_scan(self):
        with self.assertRaises(importers.ImportErrorUser):
            importers.extract_file("bad.pdf", b"not pdf")
        result = mock.Mock(returncode=0, stdout=json.dumps({"text": ""}).encode())
        with mock.patch("importers.subprocess.run", return_value=result), self.assertRaisesRegex(importers.ImportErrorUser, "OCR"):
            importers.extract_file("scan.pdf", b"%PDF-1.7\n")

    def test_pdf_worker_result_keeps_page_provenance(self):
        result = mock.Mock(returncode=0, stdout=json.dumps({"text": "[PDF 1쪽]\n협약 변경"}).encode())
        with mock.patch("importers.subprocess.run", return_value=result):
            self.assertEqual(importers.extract_file("plan.pdf", b"%PDF-1.7\n")[0], "[PDF 1쪽]\n협약 변경")

    def test_pdf_timeout_is_actionable(self):
        import subprocess
        with mock.patch("importers.subprocess.run", side_effect=subprocess.TimeoutExpired("python", 45)), self.assertRaisesRegex(importers.ImportErrorUser, "45초"):
            importers.extract_file("plan.pdf", b"%PDF-1.7\n")


if __name__ == "__main__":
    unittest.main()
