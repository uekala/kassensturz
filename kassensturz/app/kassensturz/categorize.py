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
    ("gehalt", "in", ["lohn", "gehalt", "bezuege", "besoldung", "entgelt", "rente", "salary", "payroll", "kindergeld", "familienkasse", "bundesagentur fuer arbeit", "elterngeld", "arbeitslosengeld", "buergergeld", "wohngeld", "versorgungsbezuege", "verguetung", "honorar", "krankengeld"]),
    ("erstattungen", "in", ["erstattung", "rueckerstattung", "refund", "rueckzahlung", "storno", "retoure", "rueckbuchung", "cashback", "steuererstattung", "gutschrift retoure", "ruecksendung"]),
    ("auto", "out", ["kfz-steuer", "kfz steuer", "kraftfahrzeugsteuer", "atu", "pitstop", "reifen", "werkstatt", "adac", "tuev", "dekra", "autowaesche", "waschstrasse", "autohaus", "carglass", "euromaster", "vergoelst", "autoteile", "kfzteile24", "waschpark", "mr. wash", "zulassungsstelle", "strassenverkehrsamt", "hauptuntersuchung", "kfz-werkstatt", "reifenservice", "autolackierer"]),
    ("laden", "out", ["supercharger", "tesla", "ionity", "ladestrom", "allego", "fastned", "aral pulse", "enbw mobility", "maingau", "elli", "plugsurfing", "chargepoint", "shell recharge", "ewe go", "electra", "aral", "shell", "esso", "jet tankstelle", "total energies", "totalenergies", "avia", "star tankstelle", "tankstelle", "agip", "orlen", "tank & rast", "hem tankstelle", "westfalen tank", "ladesaeule", "ladestation", "tesla charging", "eon drive", "e.on drive", "mer germany", "pfalzwerke", "lichtblick emobility", "kraftstoff"]),
    ("oepnv", "out", ["db vertrieb", "deutsche bahn", "db fernverkehr", "deutschlandticket", "d-ticket", "flixbus", "flixtrain", "rheinbahn", "vrr", "swk mobil", "kvb", "bvg", "mvg", "hvv", "uber", "bolt", "free now", "freenow", "tier", "lime", "voi", "dott", "bahn.de", "db bahn", "nextbike", "call a bike", "miles mobility", "share now", "sixt share", "taxi", "moia", "nahverkehr", "verkehrsbetriebe", "verkehrsverbund", "vrs", "fahrkarte", "ticket bahn"]),
    ("parken", "out", ["parken", "parkhaus", "easypark", "parkster", "apcoa", "contipark", "park now", "parkandjoy", "mobilet", "maut", "toll", "parkgebuehr", "parkautomat", "parkschein", "q-park", "parkraum"]),
    ("energie", "out", ["stadtwerke", "e.on", "eon energie", "rwe", "vattenfall", "enbw", "tibber", "lichtblick", "eprimo", "octopus energy", "yello", "naturstrom", "polarstern", "swk energie", "rheinenergie", "gasag", "entega", "fernwaerme", "enercity", "mainova", "n-ergie", "ewe vertrieb", "ostrom", "1komma5", "heizoel", "wasserwerk", "stadtentwaesserung", "abwasser", "abfallgebuehr", "muellabfuhr", "abschlag strom", "abschlag gas", "stromabschlag", "gasabschlag", "energieversorgung"]),
    ("internet", "out", ["telekom", "vodafone", "telefonica", "o2", "1&1", "1und1", "congstar", "freenet", "pyur", "netcologne", "deutsche glasfaser", "fraenk", "drillisch", "mobilcom", "klarmobil", "winsim", "simyo", "ortel", "aldi talk", "lidl connect", "unitymedia", "m-net", "sim.de", "blau.de", "blau mobilfunk", "otelo", "lebara", "lycamobile", "ay yildiz", "sipgate", "easybell", "ewe tel", "starlink", "handyvertrag", "mobilfunk", "festnetz"]),
    ("rundfunk", "out", ["rundfunk", "beitragsservice", "ard zdf"]),
    ("miete", "out", ["miete", "kaltmiete", "warmmiete", "nebenkosten", "hausgeld", "wohnungsbau", "vonovia", "leg wohnen", "wohnungsgesellschaft", "grundsteuer", "pacht", "wohnungsgenossenschaft", "wohnstaette", "hausverwaltung", "immobilienverwaltung", "wohnbau", "betriebskosten", "weg-verwaltung", "stellplatz", "garagenmiete"]),
    ("versicherungen", "out", ["versicherung", "allianz", "huk-coburg", "huk24", "huk coburg", "ergo", "axa", "generali", "devk", "signal iduna", "debeka", "provinzial", "r+v", "ruv", "zurich", "gothaer", "cosmosdirekt", "hansemerkur", "barmenia", "lvm", "wgv", "verti", "da direkt", "haftpflicht", "techniker krankenkasse", "aok", "barmer", "dak", "ikk", "bkk", "ottonova", "wuestenrot", "continentale", "nuernberger", "alte leipziger", "vhv", "arag", "roland rechtsschutz", "krankenkasse", "dak-gesundheit", "knappschaft", "hallesche", "wuerttembergische", "die bayerische", "advocard", "getsafe", "hausrat", "rechtsschutz", "lebensversicherung", "unfallversicherung", "kfz-versicherung", "zahnzusatz"]),
    ("streaming", "out", ["netflix", "spotify", "disney plus", "disney+", "disneyplus", "prime video", "amazon prime", "primevideo", "dazn", "sky deutschland", "wow tv", "rtl+", "rtl plus", "joyn", "youtube premium", "audible", "deezer", "tidal", "paramount", "apple music", "crunchyroll", "magentatv", "waipu", "apple tv", "magenta tv", "zattoo", "twitch", "nintendo", "playstation", "xbox", "steamgames", "steam purchase", "epic games", "blizzard", "kindle unlimited", "storytel", "bookbeat"]),
    ("software", "out", ["google storage", "google one", "google *", "icloud", "apple.com/bill", "apple services", "microsoft", "adobe", "dropbox", "github", "openai", "chatgpt", "anthropic", "claude.ai", "proton", "1password", "bitwarden", "nordvpn", "mullvad", "jetbrains", "nabu casa", "hetzner", "ionos", "strato", "all-inkl", "netcup", "cloudflare", "notion", "canva", "playstation", "xbox", "nintendo", "steam", "steamgames", "google workspace", "google cloud", "amazon web services", "digitalocean", "figma", "zoom.us", "atlassian", "tailscale", "shopify", "godaddy", "namecheap", "lastpass", "malwarebytes", "kaspersky", "midjourney", "perplexity"]),
    ("presse", "out", ["zeit verlag", "spiegel", "faz", "sueddeutsche", "rheinische post", "handelsblatt", "heise", "golem", "readly", "tagesspiegel", "welt plus", "bild plus", "westdeutsche zeitung"]),
    ("supermarkt", "out", ["rewe", "edeka", "e center", "aldi", "lidl", "kaufland", "netto", "penny", "globus", "tegut", "norma", "marktkauf", "nahkauf", "denns", "alnatura", "hit markt", "famila", "combi", "picnic", "flink", "knuspr", "getir", "metro", "baeckerei", "backwerk", "metzgerei", "kamps", "trinkgut", "getraenkemarkt", "getraenke hoffmann", "backhaus", "back-factory", "fleischerei", "wochenmarkt", "biomarkt", "bio company", "reformhaus", "feinkost", "hofladen", "hellofresh", "bofrost", "eismann", "asia markt", "supermarkt", "lebensmittel"]),
    ("drogerie", "out", ["dm-drogerie", "dm drogerie", "dm fil", "rossmann", "mueller handels", "budni", "douglas", "flaconi", "dm drogeriemarkt", "dm-drogeriemarkt", "drogerie", "parfuemerie", "friseur", "frisoer", "barbershop", "kosmetikstudio", "nagelstudio"]),
    ("restaurant", "out", ["lieferando", "wolt", "uber eats", "ubereats", "mcdonald", "burger king", "starbucks", "kfc", "subway", "vapiano", "dominos", "domino's", "pizza", "restaurant", "gaststaette", "cafe", "bistro", "imbiss", "doener", "sushi", "too good to go", "dean&david", "l'osteria", "losteria", "block house", "mcdonalds", "nordsee", "hans im glueck", "peter pane", "five guys", "dunkin", "pizzeria", "trattoria", "ristorante", "kebab", "kebap", "eiscafe", "eisdiele", "brauhaus", "kneipe", "kantine", "mensa", "lieferservice", "steakhouse", "burgerme", "baeckerei cafe"]),
    ("hobby", "out", ["decathlon", "fitness", "mcfit", "fitx", "urban sports", "john reed", "clever fit", "kino", "cinemaxx", "uci kinowelt", "eventim", "ticketmaster", "thalia", "hugendubel", "bambu lab", "prusa", "conrad", "baumarkt-hobby", "lego", "intersport", "sportscheck", "bike", "fahrrad", "rose bikes", "bergfreunde", "globetrotter", "fitnessstudio", "schwimmbad", "sauna", "therme", "zoo", "museum", "theater", "konzert", "bowling", "kletterhalle", "sportverein", "vereinsbeitrag", "mitgliedsbeitrag", "tanzschule", "musikschule", "thomann", "spielwaren", "smyths", "bambulab", "3djake", "filament", "angelsport", "fahrrad xxl"]),
    ("reisen", "out", ["booking.com", "airbnb", "lufthansa", "eurowings", "ryanair", "condor", "tui", "expedia", "hotel", "hrs", "trivago", "easyjet", "wizz air", "holidaycheck", "check24 reise", "ferienwohnung", "jugendherberge", "sixt", "europcar", "hertz", "avis", "flughafen", "airport", "airline", "turkish airlines", "pegasus", "sunexpress", "klm", "air france", "british airways", "vueling", "hostel", "motel one", "ibis", "mercure", "hilton", "marriott", "campingplatz", "faehre", "reisebuero", "getyourguide", "omio", "trainline", "kreuzfahrt", "enterprise rent", "mietwagen"]),
    ("kleidung", "out", ["h&m", "c&a", "primark", "zara", "deichmann", "snipes", "peek & cloppenburg", "p&c", "tk maxx", "uniqlo", "bonprix", "tchibo", "kik", "jack & jones", "s.oliver", "esprit", "nike", "adidas", "puma", "new yorker", "vero moda", "bershka", "pull&bear", "tom tailor", "gerry weber", "takko", "ernstings", "ernsting's family", "hunkemoeller", "calzedonia", "foot locker", "jd sports", "asos", "breuninger", "galeria", "karstadt", "kaufhof", "goertz", "levis", "hugo boss", "calvin klein", "tommy hilfiger", "lacoste", "juwelier", "pandora", "swarovski", "accessoires", "schuhhaus"]),
    ("elektronik", "out", ["mediamarkt", "media markt", "saturn", "cyberport", "notebooksbilliger", "alternate", "mindfactory", "reichelt", "berrybase", "apple store", "gravis", "caseking", "tink", "galaxus", "euronics", "medimax", "coolblue", "computeruniverse", "pollin", "voelkner", "arlt", "bechtle", "ubiquiti", "shelly", "handyshop"]),
    ("online", "out", ["amazon", "amzn", "otto", "zalando", "ebay", "temu", "shein", "aliexpress", "etsy", "about you", "idealo", "kleinanzeigen", "vinted", "wish", "amazon.de", "amzn mktp", "amazon marketplace", "alibaba", "banggood", "joom", "qvc", "baur", "mytoys", "babymarkt"]),
    ("haushalt", "out", ["ikea", "obi", "hornbach", "bauhaus", "toom", "hagebau", "poco", "xxxlutz", "roller", "action", "tedi", "depot", "jysk", "dehner", "home24", "westwing", "butlers", "nanu-nana", "kodi", "baumarkt", "moebel", "hoeffner", "segmueller", "moemax", "daenisches bettenlager", "kuechenstudio", "wmf", "gartencenter", "pflanzen koelle", "floristik", "blumenhaus", "schluesseldienst", "waescherei", "malerbetrieb", "sanitaer", "elektriker", "schornsteinfeger", "woolworth", "euroshop", "thomas philipps", "maec geiz", "fressnapf", "zooplus", "futterhaus", "tierarzt", "tierbedarf"]),
    ("gesundheit", "out", ["apotheke", "arzt", "zahnarzt", "praxis", "optiker", "fielmann", "apollo optik", "docmorris", "shop apotheke", "physiotherapie", "krankenhaus", "klinik", "labor", "medpex", "sanitaetshaus", "aerztin", "zahnaerztin", "kieferorthopaedie", "hautarzt", "orthopaedie", "heilpraktiker", "osteopathie", "psychotherapie", "logopaedie", "ergotherapie", "hoergeraete", "amplifon", "mister spex", "sanicare", "aponeo", "aerztliche verrechnungsstelle", "pvs", "zuzahlung", "massagepraxis", "impfung"]),
    ("bildung", "out", ["udemy", "coursera", "volkshochschule", "vhs", "schulgeld", "kita", "kindergarten", "studiengebuehr", "semesterbeitrag", "fernuni", "ihk", "linkedin learning", "skillshare", "nachhilfe", "studienkreis", "schuelerhilfe", "universitaet", "hochschule", "fahrschule", "buecherei", "bibliothek", "babbel", "duolingo", "weiterbildung", "pruefungsgebuehr", "klassenfahrt", "offene ganztagsschule", "elternbeitrag", "tagespflege", "schulbuch"]),
    ("bargeld", "out", ["geldautomat", "bargeldauszahlung", "bargeld", "auszahlung gaa", "gaa", "atm", "cash withdrawal", "barauszahlung", "bargeldausz", "geldautomaten"]),
    ("steuern", "out", ["finanzamt", "bundeskasse", "steuerberater", "lohnsteuerhilfe", "zollamt", "steuerverwaltung", "landeshauptkasse", "hauptzollamt", "einkommensteuer", "est-vorauszahlung", "umsatzsteuer", "taxfix", "wiso steuer", "smartsteuer", "stadtkasse", "kreiskasse", "bussgeld", "verwarngeld", "ordnungsamt", "gebuehrenbescheid"]),
    ("sparen", "out", ["trade republic", "scalable capital", "sparplan", "wertpapier", "flatex", "smartbroker", "bitpanda", "coinbase", "kraken", "consorsbank depot", "onvista", "justtrade", "finanzen.net zero", "bausparkasse", "bausparvertrag", "schwaebisch hall", "lbs", "etf", "union investment", "deka", "dws", "fondsdepot", "fnz bank", "ebase", "growney", "quirion", "weltsparen", "raisin", "vermoegenswirksame", "riester", "ruerup", "binance", "bison app"]),
    ("kredite", "out", ["darlehen", "kredit", "tilgung", "finanzierung", "santander consumer", "targobank", "creditplus", "auxmoney", "smava", "ratenkauf", "leasing", "ratenzahlung", "consors finanz", "easycredit", "teambank", "bmw bank", "mercedes-benz bank", "volkswagen bank", "vw leasing", "tesla financial", "ikano bank", "kreditrate"]),
    ("spenden", "out", ["spende", "unicef", "wwf", "aerzte ohne grenzen", "caritas", "diakonie", "gofundme", "betterplace", "sos-kinderdorf", "greenpeace", "nabu", "drk", "deutsches rotes kreuz", "spendenkonto", "aktion deutschland hilft", "misereor", "brot fuer die welt", "tierschutz", "tierheim", "wikimedia", "patreon", "ko-fi", "moschee", "ditib", "zakat", "sadaka", "kirchengemeinde", "fleurop"]),
    ("gebuehren", "out", ["entgelt", "entgeltabschluss", "kontofuehrung", "kontoentgelt", "gebuehr", "zinsen", "abschluss", "rechnungsabschluss", "jahresgebuehr", "kartenpreis", "auslandseinsatz", "fremdwaehrung", "kontofuehrungsgebuehr", "sollzinsen", "ueberziehungszinsen", "dispozinsen", "mahngebuehr", "notar", "rechtsanwalt", "inkasso", "schufa", "buergeramt", "einwohnermeldeamt"]),
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

    for key in learn_keys(tx):
        if key.startswith("iban:") and key[5:] in ctx.own_ibans:
            continue  # eigene Konten sind Umbuchungen, keine gelernte Kategorie
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


def _is_generic(key: str) -> bool:
    return any(key == g or key.startswith(g + " ") for g in GENERIC_PAYEES)


# „Ihr Einkauf bei …“ steht bei PayPal und anderen Zahlungsdiensten im Verwendungszweck.
_MERCHANT_IN_PURPOSE = (
    re.compile(r"pp\.\d+\.pp\s*\.?\s*([^,;|]{3,60}?)\s*,?\s*ihr einkauf"),
    re.compile(r"ihr einkauf bei\s+([^,;|]{3,60})"),
    re.compile(r"(?:einkauf|zahlung|bestellung) bei\s+([^,;|]{3,60})"),
)


def merchant_behind(tx: dict) -> str | None:
    """Der eigentliche Händler, wenn als Empfänger nur ein Zahlungsdienst steht."""
    name = tx.get("counterparty") or ""
    if "*" in name:  # „SumUp *Cafe Beispiel“
        key = counterparty_key(name.split("*", 1)[1])
        if len(key) >= 3:
            return key
    purpose = norm(tx.get("purpose"))
    for rx in _MERCHANT_IN_PURPOSE:
        m = rx.search(purpose)
        if m:
            key = counterparty_key(m.group(1))
            if len(key) >= 3 and not _is_generic(key):
                return key
    return None


def learn_keys(tx: dict) -> list[str]:
    """Woran Kassensturz eine Gegenstelle wiedererkennt, das Genaueste zuerst.

    Name des Empfängers, dann Gläubiger-ID und IBAN: Viele Firmen buchen unter
    wechselnden Namen ab, aber immer von derselben Kennung. Steht nur ein
    Zahlungsdienst als Empfänger da, zählt der Händler dahinter; Kennung und IBAN
    des Dienstes sagen nichts über die Kategorie.
    """
    key = counterparty_key(tx.get("counterparty"))
    if _is_generic(key):
        merchant = merchant_behind(tx)
        return [f"via:{merchant}"] if merchant else []
    keys = [key] if len(key) >= 3 else []
    creditor = re.sub(r"[^a-z0-9]", "", norm(tx.get("creditor_id")))
    if len(creditor) >= 8:
        keys.append(f"cid:{creditor}")
    iban = re.sub(r"[^A-Z0-9]", "", (tx.get("counterparty_iban") or "").upper())
    if len(iban) >= 15:
        keys.append(f"iban:{iban}")
    return keys


def learn_key(tx: dict) -> str | None:
    """Der wichtigste Schlüssel einer Buchung; None, wenn sie sich nicht zum Lernen eignet."""
    keys = learn_keys(tx)
    return keys[0] if keys else None


def learn(db: Database, tx: dict, category_id: int) -> str | None:
    """Merkt sich die Kategorie für diese Gegenstelle. Eine neue Korrektur ersetzt die alte."""
    if tx.get("id") and ("creditor_id" not in tx or "counterparty_iban" not in tx):
        stored = db.one("SELECT counterparty_iban, creditor_id FROM transactions WHERE id = ?", (tx["id"],)) or {}
        tx = {**stored, **tx}
    keys = learn_keys(tx)
    if not keys:
        return None
    label = " ".join((tx.get("counterparty") or "").split())[:60]
    if keys[0].startswith("via:"):
        label = f"{label}: {keys[0][4:]}"[:60]
    sign = _sign_of(tx["amount_cents"])
    parent = None
    for key in keys:
        db.execute(
            "INSERT INTO learned_categories(key, sign, label, category_id, updated, parent_id) VALUES(?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(key, sign) DO UPDATE SET category_id = excluded.category_id, label = excluded.label, "
            "updated = excluded.updated, parent_id = excluded.parent_id",
            (key, sign, label, category_id, now_iso(), parent),
        )
        if parent is None:
            # Kennung und IBAN hängen am Namen: Wer den Namen vergisst, vergisst sie mit.
            parent = db.scalar("SELECT id FROM learned_categories WHERE key = ? AND sign = ?", (key, sign))
    return keys[0]


def forget(db: Database, learned_id: int) -> None:
    db.execute("DELETE FROM learned_categories WHERE id = ? OR parent_id = ?", (learned_id, learned_id))


# Wörter, die in vielen Namen stehen und nichts über die Kategorie sagen.
_COMMON_WORDS = frozenset((
    "gmbh", "und", "der", "die", "das", "fuer", "von", "bei", "mit", "shop", "store", "markt", "center", "service",
    "handel", "handels", "gesellschaft", "verwaltung", "gruppe", "international", "zentrale", "filiale", "karte",
    "kartenzahlung", "lastschrift", "ueberweisung", "dauerauftrag", "rechnung", "kunde", "kundennummer", "danke",
))
SUGGEST_MIN_PAYEES = 3
SUGGEST_PURITY = 0.9


def _words(key: str) -> set[str]:
    return {w for w in key.split() if len(w) >= 5 and w not in _COMMON_WORDS}


def suggestions(db: Database, txs: list[dict]) -> dict[int, int]:
    """Vorschläge für Buchungen ohne richtige Kategorie, aus dem eigenen Bestand.

    Ein Wort im Namen gilt als Hinweis, wenn es bei mindestens drei verschiedenen
    Empfängern vorkommt und fast immer zur selben Kategorie gehört – etwa
    „Physiotherapie“ oder „Pizzeria“. Ortsnamen und Nachnamen fallen dabei heraus,
    weil sie über die Kategorien streuen. Gibt {Buchungs-ID: Kategorie-ID} zurück.
    """
    if not txs:
        return {}
    fallback = {r["id"] for r in db.query("SELECT id FROM categories WHERE builtin_key IN ('sonstiges', 'sonstige_einnahmen')")}
    seen: dict[tuple[str, str], dict[int, set[str]]] = {}
    for row in db.query("SELECT counterparty, amount_cents, category_id FROM transactions "
                        "WHERE is_transfer = 0 AND category_id IS NOT NULL AND counterparty IS NOT NULL"):
        if row["category_id"] in fallback:
            continue
        key = counterparty_key(row["counterparty"])
        if _is_generic(key):
            continue
        sign = _sign_of(row["amount_cents"])
        for word in _words(key):
            seen.setdefault((word, sign), {}).setdefault(row["category_id"], set()).add(key)
    telling: dict[tuple[str, str], tuple[int, int]] = {}
    for token, by_category in seen.items():
        total = sum(len(payees) for payees in by_category.values())
        category, payees = max(by_category.items(), key=lambda item: len(item[1]))
        if len(payees) >= SUGGEST_MIN_PAYEES and len(payees) / total >= SUGGEST_PURITY:
            telling[token] = (category, len(payees))
    out = {}
    for tx in txs:
        key = counterparty_key(tx.get("counterparty"))
        if _is_generic(key):
            key = merchant_behind(tx) or ""
        sign = _sign_of(tx["amount_cents"])
        hits = [telling[(w, sign)] for w in _words(key) if (w, sign) in telling]
        if hits:
            out[tx["id"]] = max(hits, key=lambda hit: hit[1])[0]
    return out


# Steigt, wenn sich Wörterbuch oder Erkennung ändern. Dann wird der Bestand einmal neu zugeordnet.
RULES_VERSION = 2
RULES_VERSION_KEY = "rules_version"


def upgrade(db: Database) -> int:
    """Wendet eine neue Fassung der Regeln einmal auf den Bestand an. Von Hand Gesetztes bleibt."""
    if db.get_setting(RULES_VERSION_KEY) == RULES_VERSION:
        return 0
    changed = recategorize(db)
    db.set_setting(RULES_VERSION_KEY, RULES_VERSION)
    return changed


def recategorize(db: Database, tx_ids: list[int] | None = None) -> int:
    """Ordnet alle nicht manuell gesetzten Buchungen neu zu. Gibt Anzahl Änderungen zurück."""
    ctx = build_context(db)
    sql = ("SELECT id, account_id, amount_cents, counterparty, counterparty_iban, creditor_id, purpose, booking_text, "
           "category_id, is_transfer, rule_ref FROM transactions WHERE category_locked = 0")
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
