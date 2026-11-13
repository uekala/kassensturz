"""Kategorien, eingebaute Regeln, Umbuchungserkennung."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .db import Database, now_iso
from .util import counterparty_key, norm

# (key, Name, Eltern-key, Art)
DEFAULT_CATEGORIES = [
    ("einnahmen", "Einnahmen", None, "income"),
    ("gehalt", "Gehalt", "einnahmen", "income"),
    ("erstattungen", "Erstattungen", "einnahmen", "income"),
    ("sonstige_einnahmen", "Sonstige Einnahmen", "einnahmen", "income"),
    ("wohnen", "Wohnen", None, "expense"),
    ("miete", "Miete & Nebenkosten", "wohnen", "expense"),
    ("energie", "Strom & Gas", "wohnen", "expense"),
    ("internet", "Internet & Telefon", "wohnen", "expense"),
    ("rundfunk", "Rundfunkbeitrag", "wohnen", "expense"),
    ("haushalt", "Haushalt & Einrichtung", "wohnen", "expense"),
    ("lebensmittel", "Lebensmittel & Drogerie", None, "expense"),
    ("supermarkt", "Supermarkt", "lebensmittel", "expense"),
    ("drogerie", "Drogerie", "lebensmittel", "expense"),
    ("mobilitaet", "Mobilität", None, "expense"),
    ("laden", "Laden & Tanken", "mobilitaet", "expense"),
    ("auto", "Auto", "mobilitaet", "expense"),
    ("oepnv", "Bahn & ÖPNV", "mobilitaet", "expense"),
    ("parken", "Parken & Maut", "mobilitaet", "expense"),
    ("versicherungen", "Versicherungen", None, "expense"),
    ("abos", "Abos & Medien", None, "expense"),
    ("streaming", "Streaming & Musik", "abos", "expense"),
    ("software", "Software & Cloud", "abos", "expense"),
    ("presse", "Zeitungen & Magazine", "abos", "expense"),
    ("shopping", "Shopping", None, "expense"),
    ("online", "Online-Shopping", "shopping", "expense"),
    ("kleidung", "Kleidung & Schuhe", "shopping", "expense"),
    ("elektronik", "Elektronik", "shopping", "expense"),
    ("freizeit", "Freizeit", None, "expense"),
    ("restaurant", "Restaurants & Lieferdienste", "freizeit", "expense"),
    ("hobby", "Hobby & Sport", "freizeit", "expense"),
    ("reisen", "Reisen", "freizeit", "expense"),
    ("gesundheit", "Gesundheit", None, "expense"),
    ("bildung", "Bildung", None, "expense"),
    ("finanzen", "Finanzen", None, "expense"),
    ("bargeld", "Bargeld", "finanzen", "expense"),
    ("gebuehren", "Gebühren & Zinsen", "finanzen", "expense"),
    ("steuern", "Steuern", "finanzen", "expense"),
    ("sparen", "Sparen & Investieren", "finanzen", "expense"),
    ("kredite", "Kredite & Raten", "finanzen", "expense"),
    ("spenden", "Spenden & Geschenke", None, "expense"),
    ("sonstiges", "Sonstiges", None, "expense"),
    ("umbuchung", "Umbuchung", None, "transfer"),
]

# (Kategorie-key, Vorzeichen, Suchbegriffe). Reihenfolge = Priorität.
BUILTIN_RULES: list[tuple[str, str, list[str]]] = [
    ("gehalt", "in", ["lohn", "gehalt", "bezuege", "besoldung", "entgelt", "rente", "salary", "payroll"]),
    ("erstattungen", "in", ["erstattung", "rueckerstattung", "refund", "rueckzahlung", "storno", "retoure", "rueckbuchung"]),
    ("auto", "out", ["kfz-steuer", "kfz steuer", "kraftfahrzeugsteuer", "atu", "pitstop", "reifen", "werkstatt", "adac", "tuev", "dekra", "autowaesche", "waschstrasse"]),
    ("laden", "out", ["supercharger", "tesla", "ionity", "ladestrom", "allego", "fastned", "aral pulse", "enbw mobility", "maingau", "elli", "plugsurfing", "chargepoint", "shell recharge", "ewe go", "electra", "aral", "shell", "esso", "jet tankstelle", "total energies", "totalenergies", "avia", "star tankstelle", "tankstelle", "agip", "orlen"]),
    ("oepnv", "out", ["db vertrieb", "deutsche bahn", "db fernverkehr", "deutschlandticket", "d-ticket", "flixbus", "flixtrain", "rheinbahn", "vrr", "swk mobil", "kvb", "bvg", "mvg", "hvv", "uber", "bolt", "free now", "freenow", "tier", "lime", "voi", "dott"]),
    ("parken", "out", ["parken", "parkhaus", "easypark", "parkster", "apcoa", "contipark", "park now", "parkandjoy", "mobilet", "maut", "toll"]),
    ("energie", "out", ["stadtwerke", "e.on", "eon energie", "rwe", "vattenfall", "enbw", "tibber", "lichtblick", "eprimo", "octopus energy", "yello", "naturstrom", "polarstern", "swk energie", "rheinenergie", "gasag", "entega"]),
    ("internet", "out", ["telekom", "vodafone", "telefonica", "o2", "1&1", "1und1", "congstar", "freenet", "pyur", "netcologne", "deutsche glasfaser", "fraenk", "drillisch", "mobilcom", "klarmobil", "winsim", "simyo", "ortel", "aldi talk", "lidl connect", "unitymedia", "m-net"]),
    ("rundfunk", "out", ["rundfunk", "beitragsservice", "ard zdf"]),
    ("miete", "out", ["miete", "kaltmiete", "warmmiete", "nebenkosten", "hausgeld", "wohnungsbau", "vonovia", "leg wohnen", "wohnungsgesellschaft", "grundsteuer"]),
    ("versicherungen", "out", ["versicherung", "allianz", "huk-coburg", "huk24", "huk coburg", "ergo", "axa", "generali", "devk", "signal iduna", "debeka", "provinzial", "r+v", "ruv", "zurich", "gothaer", "cosmosdirekt", "hansemerkur", "barmenia", "lvm", "wgv", "verti", "da direkt", "haftpflicht", "techniker krankenkasse", "aok", "barmer", "dak", "ikk", "bkk", "ottonova", "wuestenrot", "continentale", "nuernberger", "alte leipziger", "vhv", "arag", "roland rechtsschutz"]),
    ("streaming", "out", ["netflix", "spotify", "disney plus", "disney+", "disneyplus", "prime video", "amazon prime", "primevideo", "dazn", "sky deutschland", "wow tv", "rtl+", "rtl plus", "joyn", "youtube premium", "audible", "deezer", "tidal", "paramount", "apple music", "crunchyroll", "magentatv", "waipu"]),
    ("software", "out", ["google storage", "google one", "google *", "icloud", "apple.com/bill", "apple services", "microsoft", "adobe", "dropbox", "github", "openai", "chatgpt", "anthropic", "claude.ai", "proton", "1password", "bitwarden", "nordvpn", "mullvad", "jetbrains", "nabu casa", "hetzner", "ionos", "strato", "all-inkl", "netcup", "cloudflare", "notion", "canva", "playstation", "xbox", "nintendo", "steam", "steamgames"]),
    ("presse", "out", ["zeit verlag", "spiegel", "faz", "sueddeutsche", "rheinische post", "handelsblatt", "heise", "golem", "readly", "tagesspiegel", "welt plus", "bild plus", "westdeutsche zeitung"]),
    ("supermarkt", "out", ["rewe", "edeka", "e center", "aldi", "lidl", "kaufland", "netto", "penny", "globus", "tegut", "norma", "marktkauf", "nahkauf", "denns", "alnatura", "hit markt", "famila", "combi", "picnic", "flink", "knuspr", "getir", "metro", "baeckerei", "backwerk", "metzgerei", "kamps"]),
    ("drogerie", "out", ["dm-drogerie", "dm drogerie", "dm fil", "rossmann", "mueller handels", "budni", "douglas", "flaconi"]),
    ("restaurant", "out", ["lieferando", "wolt", "uber eats", "ubereats", "mcdonald", "burger king", "starbucks", "kfc", "subway", "vapiano", "dominos", "domino's", "pizza", "restaurant", "gaststaette", "cafe", "bistro", "imbiss", "doener", "sushi", "too good to go", "dean&david", "l'osteria", "losteria", "block house"]),
    ("hobby", "out", ["decathlon", "fitness", "mcfit", "fitx", "urban sports", "john reed", "clever fit", "kino", "cinemaxx", "uci kinowelt", "eventim", "ticketmaster", "thalia", "hugendubel", "bambu lab", "prusa", "conrad", "baumarkt-hobby", "lego", "intersport", "sportscheck", "bike", "fahrrad", "rose bikes", "bergfreunde", "globetrotter"]),
    ("reisen", "out", ["booking.com", "airbnb", "lufthansa", "eurowings", "ryanair", "condor", "tui", "expedia", "hotel", "hrs", "trivago", "easyjet", "wizz air", "holidaycheck", "check24 reise", "ferienwohnung", "jugendherberge", "sixt", "europcar", "hertz", "avis"]),
    ("kleidung", "out", ["h&m", "c&a", "primark", "zara", "deichmann", "snipes", "peek & cloppenburg", "p&c", "tk maxx", "uniqlo", "bonprix", "tchibo", "kik", "jack & jones", "s.oliver", "esprit", "nike", "adidas", "puma"]),
    ("elektronik", "out", ["mediamarkt", "media markt", "saturn", "cyberport", "notebooksbilliger", "alternate", "mindfactory", "reichelt", "berrybase", "apple store", "gravis", "caseking", "tink", "galaxus"]),
    ("online", "out", ["amazon", "amzn", "otto", "zalando", "ebay", "temu", "shein", "aliexpress", "etsy", "about you", "idealo", "kleinanzeigen", "vinted", "wish"]),
    ("haushalt", "out", ["ikea", "obi", "hornbach", "bauhaus", "toom", "hagebau", "poco", "xxxlutz", "roller", "action", "tedi", "depot", "jysk", "dehner", "home24", "westwing", "butlers", "nanu-nana", "kodi"]),
    ("gesundheit", "out", ["apotheke", "arzt", "zahnarzt", "praxis", "optiker", "fielmann", "apollo optik", "docmorris", "shop apotheke", "physiotherapie", "krankenhaus", "klinik", "labor", "medpex", "sanitaetshaus"]),
    ("bildung", "out", ["udemy", "coursera", "volkshochschule", "vhs", "schulgeld", "kita", "kindergarten", "studiengebuehr", "semesterbeitrag", "fernuni", "ihk", "linkedin learning", "skillshare"]),
    ("bargeld", "out", ["geldautomat", "bargeldauszahlung", "bargeld", "auszahlung gaa", "gaa", "atm", "cash withdrawal", "barauszahlung"]),
    ("steuern", "out", ["finanzamt", "bundeskasse", "steuerberater", "lohnsteuerhilfe", "zollamt"]),
    ("sparen", "out", ["trade republic", "scalable capital", "sparplan", "wertpapier", "flatex", "smartbroker", "bitpanda", "coinbase", "kraken", "consorsbank depot", "onvista", "justtrade", "finanzen.net zero", "bausparkasse", "bausparvertrag", "schwaebisch hall", "lbs"]),
    ("kredite", "out", ["darlehen", "kredit", "tilgung", "finanzierung", "santander consumer", "targobank", "creditplus", "auxmoney", "smava", "ratenkauf", "leasing"]),
    ("spenden", "out", ["spende", "unicef", "wwf", "aerzte ohne grenzen", "caritas", "diakonie", "gofundme", "betterplace", "sos-kinderdorf", "greenpeace", "nabu", "drk", "deutsches rotes kreuz"]),
    ("gebuehren", "out", ["entgelt", "entgeltabschluss", "kontofuehrung", "kontoentgelt", "gebuehr", "zinsen", "abschluss", "rechnungsabschluss", "jahresgebuehr", "kartenpreis", "auslandseinsatz", "fremdwaehrung"]),
]

TRANSFER_WORDS = re.compile(r"(?<![a-z])(umbuchung|eigenuebertrag|kontouebertrag|eigene konten|own account|transfer to own)")
PAYPAL_FUNDING = re.compile(r"bankgutschrift|bankkonto|abbuchung|einzahlung|aufladung|lastschrift.*paypal|top.?up|guthaben aufladen")
CARD_PAYMENT = re.compile(r"(?<![a-z])zahlung(?![a-z])|zahlung erhalten|zahlungseingang|besten dank|ausgleich|lastschrifteinzug|einzug|payment received|abrechnungsausgleich|ueberweisung erhalten|zahlung - danke")


def _compile(term: str) -> re.Pattern:
    t = norm(term)
    if t.endswith("*"):
        return re.compile(r"(?<![a-z0-9])" + re.escape(t[:-1].rstrip()))
    return re.compile(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])")


_BUILTIN_COMPILED = [(key, sign, [_compile(t) for t in terms]) for key, sign, terms in BUILTIN_RULES]


def ensure_categories(db: Database) -> None:
    existing = {r["builtin_key"] for r in db.query("SELECT builtin_key FROM categories WHERE builtin_key IS NOT NULL")}
    with db.tx():
        ids = {r["builtin_key"]: r["id"] for r in db.query("SELECT id, builtin_key FROM categories WHERE builtin_key IS NOT NULL")}
        for i, (key, name, parent, kind) in enumerate(DEFAULT_CATEGORIES):
            if key in existing:
                continue
            ids[key] = db.insert("categories", {
                "name": name, "parent_id": ids.get(parent) if parent else None,
                "kind": kind, "sort": i * 10, "builtin_key": key,
            })


@dataclass
class Context:
    cat_by_key: dict
    cat_kind: dict
    own_ibans: dict
    settlements: list
    account_kind: dict
    user_rules: list
    learned: dict


def build_context(db: Database) -> Context:
    cats = db.query("SELECT id, builtin_key, kind FROM categories")
    accounts = db.query("SELECT id, iban, kind, settlement_pattern FROM accounts WHERE archived = 0")
    own = {}
    for a in accounts:
        if a["iban"]:
            own[a["iban"].replace(" ", "").upper()] = a["id"]
    settlements = []
    for a in accounts:
        for p in (a["settlement_pattern"] or "").split(","):
            if p.strip():
                settlements.append((_compile(p.strip()), a["id"]))
    rules = []
    for r in db.query("SELECT * FROM rules WHERE enabled = 1 ORDER BY priority, id"):
        try:
            rx = re.compile(r["pattern"][3:], re.I) if r["pattern"].startswith("re:") else _compile(r["pattern"])
        except re.error:
            continue
        rules.append((r, rx))
    return Context(
        cat_by_key={c["builtin_key"]: c["id"] for c in cats if c["builtin_key"]},
        cat_kind={c["id"]: c["kind"] for c in cats},
        own_ibans=own,
        settlements=settlements,
        account_kind={a["id"]: a["kind"] for a in accounts},
        user_rules=rules,
        learned={(r["key"], r["sign"]): r["category_id"] for r in db.query("SELECT key, sign, category_id FROM learned_categories")},
    )


def _sign_ok(sign: str, amount: int) -> bool:
    return sign == "any" or (sign == "in" and amount > 0) or (sign == "out" and amount < 0)


def classify(tx: dict, ctx: Context) -> tuple[int | None, int, str | None]:
    """Gibt (Kategorie-ID, ist_Umbuchung, Regel-Referenz) zurück."""
    amount = tx["amount_cents"]
    cp, purpose, btext = norm(tx.get("counterparty")), norm(tx.get("purpose")), norm(tx.get("booking_text"))
    full = f"{cp} | {purpose} | {btext}"
    transfer_id = ctx.cat_by_key.get("umbuchung")

    for r, rx in ctx.user_rules:
        if not _sign_ok(r["sign"], amount):
            continue
        hay = {"counterparty": cp, "purpose": purpose, "iban": (tx.get("counterparty_iban") or "").lower()}.get(r["field"], full)
        if rx.search(hay):
            is_tr = 1 if (r["mark_transfer"] or ctx.cat_kind.get(r["category_id"]) == "transfer") else 0
            return (r["category_id"] or (transfer_id if is_tr else None), is_tr, f"user:{r['id']}")

    key = learn_key(tx)
    if key:
        learned = ctx.learned.get((key, _sign_of(amount)))
        if learned in ctx.cat_kind:
            return (learned, 1 if ctx.cat_kind[learned] == "transfer" else 0, "learned")

    iban = (tx.get("counterparty_iban") or "").replace(" ", "").upper()
    if iban and iban in ctx.own_ibans and ctx.own_ibans[iban] != tx["account_id"]:
        return (transfer_id, 1, "own-iban")
    for rx, acc_id in ctx.settlements:
        if acc_id != tx["account_id"] and (rx.search(cp) or rx.search(purpose)):
            return (transfer_id, 1, f"settlement:{acc_id}")
    kind = ctx.account_kind.get(tx["account_id"])
    if kind == "paypal" and not cp and PAYPAL_FUNDING.search(f"{btext} {purpose}"):
        return (transfer_id, 1, "paypal-funding")
    if kind == "kreditkarte" and amount > 0 and CARD_PAYMENT.search(full):
        return (transfer_id, 1, "card-payment")
    if TRANSFER_WORDS.search(f"{cp} | {purpose}") or btext.startswith("umbuchung"):
        return (transfer_id, 1, "transfer-word")

    for key, sign, patterns in _BUILTIN_COMPILED:
        if not _sign_ok(sign, amount):
            continue
        for rx in patterns:
            if rx.search(cp) or rx.search(purpose) or rx.search(btext):
                return (ctx.cat_by_key.get(key), 0, f"builtin:{key}")

    fallback = "sonstige_einnahmen" if amount > 0 else "sonstiges"
    return (ctx.cat_by_key.get(fallback), 0, None)


# Zahlungsdienste stehen bei vielen verschiedenen Händlern als Empfänger. Von ihnen
# lässt sich nicht auf eine Kategorie schließen.
GENERIC_PAYEES = ("paypal", "klarna", "sumup", "zettle", "izettle", "stripe", "adyen", "mollie", "unzer", "payone",
                  "amazon payments", "google pay", "apple pay")


def _sign_of(amount: int) -> str:
    return "in" if amount > 0 else "out"


def learn_key(tx: dict) -> str | None:
    """Woran Kassensturz einen Empfänger wiedererkennt; None, wenn er sich nicht eignet."""
    key = counterparty_key(tx.get("counterparty"))
    if len(key) < 3 or any(key == g or key.startswith(g + " ") for g in GENERIC_PAYEES):
        return None
    return key


def learn(db: Database, tx: dict, category_id: int) -> str | None:
    """Merkt sich die Kategorie für diesen Empfänger. Eine neue Korrektur ersetzt die alte."""
    key = learn_key(tx)
    if not key:
        return None
    label = " ".join((tx.get("counterparty") or "").split())[:60]
    db.execute(
        "INSERT INTO learned_categories(key, sign, label, category_id, updated) VALUES(?, ?, ?, ?, ?) "
        "ON CONFLICT(key, sign) DO UPDATE SET category_id = excluded.category_id, label = excluded.label, "
        "updated = excluded.updated",
        (key, _sign_of(tx["amount_cents"]), label, category_id, now_iso()),
    )
    return key


def recategorize(db: Database, tx_ids: list[int] | None = None) -> int:
    """Ordnet alle nicht manuell gesetzten Buchungen neu zu. Gibt Anzahl Änderungen zurück."""
    ctx = build_context(db)
    sql = "SELECT id, account_id, amount_cents, counterparty, counterparty_iban, purpose, booking_text, category_id, is_transfer, rule_ref FROM transactions WHERE category_locked = 0"
    params: tuple = ()
    if tx_ids is not None:
        if not tx_ids:
            return 0
        sql += f" AND id IN ({','.join('?' * len(tx_ids))})"
        params = tuple(tx_ids)
    changes = []
    for tx in db.query(sql, params):
        cat, is_tr, ref = classify(tx, ctx)
        if (cat, is_tr, ref) != (tx["category_id"], tx["is_transfer"], tx["rule_ref"]):
            changes.append((cat, is_tr, ref, tx["id"]))
    if changes:
        with db.tx():
            db.executemany("UPDATE transactions SET category_id = ?, is_transfer = ?, rule_ref = ? WHERE id = ?", changes)
    return len(changes)


def suggest_pattern(tx: dict) -> str:
    """Schlägt einen Suchbegriff für 'Regel aus dieser Buchung' vor."""
    cp = norm(tx.get("counterparty"))
    if cp:
        words = [w for w in re.split(r"[^a-z0-9&+.\-]+", cp) if len(w) > 1 and not w.isdigit()]
        return " ".join(words[:3])
    purpose = norm(tx.get("purpose"))
    words = [w for w in re.split(r"[^a-z0-9&+.\-]+", purpose) if len(w) > 2 and not any(ch.isdigit() for ch in w)]
    return " ".join(words[:2])
