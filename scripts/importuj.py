"""Načíta verejné liturgické poriadky a vytvorí údaje pre statický web."""

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from lxml import html

SOURCE = "https://www.mojakomunita.sk/web/gkc-farnost-sambron/poriadok-bohosluzieb"
PATH = "/web/gkc-farnost-sambron/poriadok-bohosluzieb/-/blogs/"
OUTPUT = Path(__file__).resolve().parents[1] / "site" / "poriadky.json"
TOWNS = {"Š": "Šambron", "B": "Bajerovce", "H": "Hromoš"}
WEEKDAYS = "PONDELOK UTOROK STREDA ŠTVRTOK PIATOK SOBOTA NEDEĽA".split()
DAY = re.compile(rf"^({'|'.join(WEEKDAYS)})\s*(\d{{1,2}})\s*\.\s*(\d{{1,2}})\b", re.I)
PERIOD = re.compile(
    r"poriadok\s+od\s+(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(?:(\d{4})\s*\.?\s*)?"
    r"(?:do|[-–—])\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{4})\b",
    re.I,
)
CLOCK = r"(?<!\d)([01]?\d|2[0-3])\s*[.:]\s*([0-5]\d)(?!\d)"
EVENT = re.compile(r"(?<!\w)([ŠBH])\s*\.?\s*" + CLOCK, re.I)
NOTE = re.compile(r"=\s*([^=]+?)\s*=")
MAX_BYTES = 3_000_000


def fetch(url):
    request = Request(url, headers={"User-Agent": "SambronPoriadky/1.0 (public schedule reader)"})
    with urlopen(request, timeout=15) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("HTML prekročilo povolenú veľkosť.")
        charset = response.headers.get_content_charset()
        return html.fromstring(body, parser=html.HTMLParser(encoding=charset or "utf-8"))


def content(element):
    return " ".join(" ".join(element.itertext()).split())


def article_links(page):
    candidates = {}
    for anchor in page.xpath("//a[@href]"):
        link = urlsplit(urljoin(SOURCE, anchor.get("href")))
        if link.hostname not in {"www.mojakomunita.sk", "mojakomunita.sk"}:
            continue
        path = unquote(link.path).rstrip("/")
        if PATH not in path:
            continue
        slug = path.partition(PATH)[2]
        if re.fullmatch(r"liturgicky-[a-z0-9-]+|\d+", slug):
            candidates[slug] = SOURCE + "/-/blogs/" + slug
    return list(candidates.values())


def period_dates(page):
    match = PERIOD.search(content(page))
    if not match:
        raise ValueError("Nenašiel sa rozsah dátumov poriadku.")
    first_day, first_month, first_year, last_day, last_month, last_year = (
        int(value) if value else None for value in match.groups()
    )
    first_year = first_year or last_year - ((first_month, first_day) > (last_month, last_day))
    start = date(first_year, first_month, first_day)
    end = date(last_year, last_month, last_day)
    if not 0 <= (end - start).days <= 31:
        raise ValueError("Neplatný rozsah dátumov poriadku.")
    return start, end


def parse_article(page, url):
    start, end = period_dates(page)
    dates = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    by_day = {(item.day, item.month): item for item in dates}
    days = {}
    for row in page.xpath("//tr"):
        cells = [content(cell) for cell in row.xpath("./td|./th")]
        if not cells or not (day := DAY.match(cells[0])):
            continue
        weekday, number, month = day.groups()
        actual_date = by_day.get((int(number), int(month)))
        if actual_date is None:
            continue
        if weekday.upper() != WEEKDAYS[actual_date.weekday()] or len(cells) < 3:
            raise ValueError(f"Nerozpoznaný riadok pre {actual_date}.")
        matches = list(EVENT.finditer(cells[2]))
        if len(matches) != len(re.findall(CLOCK, cells[2])):
            raise ValueError(f"Nerozpoznané miesto termínu pre {actual_date}.")
        events = [
            {"time": f"{int(hour):02}:{minute}", "town": TOWNS[town.upper()]}
            for town, hour, minute in (match.groups() for match in matches)
        ]
        key = actual_date.isoformat()
        entry = days.setdefault(key, {"date": key, "feast": cells[1], "events": [], "notes": []})
        entry["events"].extend(event for event in events if event not in entry["events"])
        notes = NOTE.findall(" ".join(cells[3:]))
        entry["notes"].extend(note.strip() for note in notes if note.strip() not in entry["notes"])
    if not days or not any(entry["events"] for entry in days.values()):
        raise ValueError("Nenašli sa riadky s časmi a obcami.")
    for entry in days.values():
        entry["events"].sort(key=lambda event: event["time"])
    return {"start": start.isoformat(), "end": end.isoformat(), "source": url,
            "days": sorted(days.values(), key=lambda entry: entry["date"])}


def import_schedules(today):
    links = article_links(fetch(SOURCE))
    if not links:
        raise ValueError("Na farskej stránke sa nenašli odkazy na poriadky.")

    cutoff = (today - timedelta(days=28)).isoformat()
    previous = json.loads(OUTPUT.read_text(encoding="utf-8"))["schedules"]
    by_url = {item["source"]: item for item in previous if item["end"] >= cutoff}
    valid = 0
    for url in links[:8]:
        try:
            schedule = parse_article(fetch(url), url)
        except (ValueError, URLError, TimeoutError, html.etree.LxmlError) as error:
            print(f"{url}: {error}", file=sys.stderr)
            continue
        valid += 1
        if schedule["end"] >= cutoff:
            by_url[url] = schedule
        else:
            by_url.pop(url, None)

    if not valid:
        raise ValueError("Nepodarilo sa načítať žiadny platný poriadok.")
    if not any(item["end"] >= today.isoformat() for item in by_url.values()):
        print("Zdroj zatiaľ neobsahuje platný aktuálny ani budúci poriadok.", file=sys.stderr)

    schedules = sorted(by_url.values(), key=lambda item: (item["start"], item["source"]), reverse=True)
    result = json.dumps({"schedules": schedules}, ensure_ascii=False, indent=2) + "\n"
    if result != OUTPUT.read_text(encoding="utf-8"):
        temp = OUTPUT.with_suffix(".tmp")
        temp.write_text(result, encoding="utf-8")
        temp.replace(OUTPUT)
    print(f"Spracovaných príspevkov: {valid}. Uložených poriadkov: {len(schedules)}.")


if __name__ == "__main__":
    try:
        import_schedules(datetime.now(ZoneInfo("Europe/Bratislava")).date())
    except (ValueError, OSError, html.etree.LxmlError) as error:
        sys.exit(f"Import zlyhal: {error}")
