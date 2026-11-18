"""Die Oberfläche besteht aus ES-Modulen. Was ein Modul importiert, muss ein anderes exportieren."""
import re
from pathlib import Path

from kassensturz import options

STATIC = Path(__file__).resolve().parent.parent / "kassensturz" / "app" / "kassensturz" / "static"
IMPORT = re.compile(r'^import \{ ([^}]+) \} from "(\./[^"]+)";$', re.M)
EXPORT = re.compile(r"^export (?:async\s+)?(?:function\*?\s+([\w$]+)|(?:const|let|class)\s+([\w$]+))", re.M)


def test_every_import_is_exported_and_every_module_is_used():
    files = [STATIC / "app.js", *sorted((STATIC / "js").glob("*.js"))]
    exports = {f: {a or b for a, b in EXPORT.findall(f.read_text(encoding="utf-8"))} for f in files}
    reached = {STATIC / "app.js"}
    for f in files:
        for names, target in IMPORT.findall(f.read_text(encoding="utf-8")):
            path = (f.parent / target).resolve()
            assert path in exports, f"{f.name} importiert {target}, das gibt es nicht"
            missing = {n.strip() for n in names.split(",")} - exports[path]
            assert not missing, f"{f.name} importiert {missing} aus {target}, dort nicht exportiert"
            reached.add(path)
    assert reached == set(files), "Module, die niemand lädt"
    assert "app.js" in (STATIC / "index.html").read_text(encoding="utf-8")


def test_page_carries_the_current_version_and_static_files_are_revalidated(client):
    page = client.get("/")
    assert page.status_code == 200 and f"app.js?v={options.VERSION}" in page.text and f"app.css?v={options.VERSION}" in page.text
    for path in ("/static/app.js", "/static/js/core.js", "/static/app.css"):
        got = client.get(path)
        assert got.status_code == 200 and got.headers["cache-control"] == "no-cache", path
