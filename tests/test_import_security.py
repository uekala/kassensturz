import io
import zipfile

import pytest

from kassensturz import importers


def _zip_with_xml_entries(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    return buf.getvalue()


def test_import_rejects_oversized_raw_file(monkeypatch):
    monkeypatch.setattr(importers, "MAX_IMPORT_BYTES", 4)
    with pytest.raises(ValueError, match="Importlimit"):
        importers.analyze(b"12345", "statement.csv")


def test_zip_import_rejects_too_many_entries(monkeypatch):
    monkeypatch.setattr(importers, "MAX_ZIP_ENTRIES", 1)
    data = _zip_with_xml_entries([("one.xml", b"<Document/>"), ("two.xml", b"<Document/>")])
    with pytest.raises(ValueError, match="Einträge"):
        importers.analyze(data, "statement.zip")


def test_zip_import_rejects_expanded_size_limit(monkeypatch):
    monkeypatch.setattr(importers, "MAX_ZIP_EXPANDED_BYTES", 10)
    data = _zip_with_xml_entries([("statement.xml", b"<Document>123456789</Document>")])
    with pytest.raises(ValueError, match="entpackte Gesamtgröße"):
        importers.analyze(data, "statement.zip")


def test_zip_import_rejects_oversized_xml_member(monkeypatch):
    monkeypatch.setattr(importers, "MAX_XML_FILE_BYTES", 10)
    data = _zip_with_xml_entries([("statement.xml", b"<Document>123456789</Document>")])
    with pytest.raises(ValueError, match="XML-Datei"):
        importers.analyze(data, "statement.zip")
