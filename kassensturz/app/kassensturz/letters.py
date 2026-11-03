"""Kündigungsschreiben aus Vertragsdaten."""
from __future__ import annotations

from datetime import date
from urllib.parse import quote

from .db import Database


def _fmt(d: str | None) -> str:
    if not d:
        return ""
    try:
        return date.fromisoformat(d).strftime("%d.%m.%Y")
    except ValueError:
        return d


def build_letter(db: Database, contract: dict, mode: str = "ordentlich", on_date: str | None = None) -> dict:
    profile = db.get_setting("profile", {}) or {}
    name = profile.get("name") or "Vorname Nachname"
    street = profile.get("street") or "Straße Hausnummer"
    city = profile.get("city") or "PLZ Ort"
    place = (profile.get("city") or "").split(" ", 1)[-1] if profile.get("city") else "Ort"

    provider = contract.get("name") or contract.get("counterparty") or "Anbieter"
    address = (contract.get("provider_address") or "").strip()
    ref = contract.get("customer_no")
    mandate = db.scalar("SELECT mandate_ref FROM transactions WHERE contract_key = ? AND mandate_ref IS NOT NULL "
                        "ORDER BY booking_date DESC LIMIT 1", (contract["key"],))
    ref_text = f" (Kunden-/Vertragsnummer {ref})" if ref else ""

    if mode == "termin" and on_date:
        core = (f"hiermit kündige ich meinen Vertrag{ref_text} zum {_fmt(on_date)}, "
                "hilfsweise zum nächstmöglichen Zeitpunkt.")
    elif mode == "sonder":
        core = (f"hiermit kündige ich meinen Vertrag{ref_text} außerordentlich zum Zeitpunkt, an dem die angekündigte "
                "Preiserhöhung wirksam werden soll. Der Preiserhöhung widerspreche ich. Hilfsweise kündige ich "
                "fristgerecht zum nächstmöglichen Zeitpunkt.")
    else:
        core = f"hiermit kündige ich meinen Vertrag{ref_text} fristgerecht zum nächstmöglichen Zeitpunkt."

    lines = [
        "Sehr geehrte Damen und Herren,",
        "",
        core,
        "",
        "Bitte bestätigen Sie mir den Eingang der Kündigung und nennen Sie mir das Datum, zu dem der Vertrag endet.",
    ]
    if mandate:
        lines += ["", f"Das SEPA-Lastschriftmandat mit der Mandatsreferenz {mandate} widerrufe ich zum Vertragsende."]
    lines += ["", "Mit freundlichen Grüßen", "", name]
    body = "\n".join(lines)
    subject = f"Kündigung{(' ' + ref) if ref else ''} – {name}"

    letter = "\n".join([
        name, street, city, "",
        provider, *([address] if address else []), "",
        f"{place}, {date.today().strftime('%d.%m.%Y')}", "",
        f"Kündigung meines Vertrags{(' Nr. ' + ref) if ref else ''}", "",
        body,
    ])
    mailto = None
    if contract.get("provider_email"):
        mailto = f"mailto:{contract['provider_email']}?subject={quote(subject)}&body={quote(body)}"
    return {"subject": subject, "body": body, "letter": letter, "mailto": mailto, "profile_complete": bool(profile.get("name"))}
