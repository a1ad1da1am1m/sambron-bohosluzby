"""Načíta verejné liturgické poriadky a vytvorí údaje pre statický web."""

import gzip
import json
import re
import sys
from datetime import date, datetime, timedelta
from io import BytesIO
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
NO_LITURGY = re.compile(r"\b(?:sv\.?\s*)?liturgia\s+nebude\b", re.I)
STANDALONE = re.compile(r"^(?:slávnostný\s+)?(?:spoveď|ruženec|večiereň|moleben|zraz)\b", re.I)
PRIVATE_REFERENCE = re.compile(r"\([ \t]*[rd][ \t]*\.[^)]*\)", re.I)
MAX_BYTES = 3_000_000


def fetch(url):
    request = Request(url, headers={"User-Agent": "SambronPoriadky/1.0 (public schedule reader)"})
    with urlopen(request, timeout=15) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("HTML prekročilo povolenú veľkosť.")
        if response.headers.get("Content-Encoding", "").lower() == "gzip" or body.startswith(b"\x1f\x8b"):
            with gzip.GzipFile(fileobj=BytesIO(body)) as compressed:
                body = compressed.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("Rozbalené HTML prekročilo povolenú veľkosť.")
        charset = response.headers.get_content_charset()
        return html.fromstring(
            body, parser=html.HTMLParser(encoding=charset or "utf-8"), base_url=response.url
        )


def content(element):
    return " ".join(" ".join(element.itertext()).split())


def article_links(page, schedules_only=True):
    candidates = {}
    for anchor in page.xpath("//a[@href]"):
        link = urlsplit(urljoin(SOURCE, anchor.get("href")))
        if link.hostname not in {"www.mojakomunita.sk", "mojakomunita.sk"}:
            continue
        path = unquote(link.path).rstrip("/")
        if PATH not in path:
            continue
        slug = path.partition(PATH)[2]
        if re.fullmatch(r"liturgicky-[a-z0-9-]+|\d+" if schedules_only else r"[\w-]+", slug) and slug not in {"rss", "edit", "new"}:
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


def table_rows(table):
    for row in table.xpath("./tr|./thead/tr|./tbody/tr|./tfoot/tr"):
        cells = row.xpath("./td|./th")
        if cells and (day := DAY.match(content(cells[0]))):
            weekday, number, month = day.groups()
            yield (weekday.upper(), int(number), int(month)), cells


def recover_week(declared_start, tables):
    """Prijme iba jediný úplný týždeň s dátumami a dňami z jednej tabuľky."""
    candidates = set()
    for offset in range(-14, 15):
        start = declared_start + timedelta(days=offset)
        if start.weekday() != 0:
            continue
        dates = [start + timedelta(days=day) for day in range(7)]
        expected = {(WEEKDAYS[day.weekday()], day.day, day.month) for day in dates}
        if any({label for label, _ in rows} == expected for rows in tables):
            candidates.add(start)
    return next(iter(candidates)) if len(candidates) == 1 else None


def parse_times(value, actual_date):
    towns = {match.end(): TOWNS[match[1].upper()] for match in EVENT.finditer(value)}
    events = []
    previous_end = 0
    for clock in re.finditer(CLOCK, value):
        town = towns.get(clock.end())
        if town is None and not re.fullmatch(r"[\s,;/]*", value[previous_end:clock.start()]):
            raise ValueError(f"Nerozpoznané miesto termínu pre {actual_date}.")
        hour, minute = clock.groups()
        events.append({"time": f"{int(hour):02}:{minute}", "town": town})
        previous_end = clock.end()
    return events


def comment_lines(cell):
    """Zachová riadky zo zdrojovej bunky vrátane zlomov uprostred odseku."""
    parts = []

    def walk(node):
        if node.tag == "br":
            parts.append("\n")
            return
        block = node.tag in {"p", "div", "li"}
        if block:
            parts.append("\n")
        parts.append(re.sub(r"\s+", " ", node.text or ""))
        for child in node:
            walk(child)
            parts.append(re.sub(r"\s+", " ", child.tail or ""))
        if block:
            parts.append("\n")

    walk(cell)
    for line in PRIVATE_REFERENCE.sub("", "".join(parts)).splitlines():
        line = " ".join(line.split())
        if line:
            yield line


def note_text(text):
    text = text.strip(" =")
    text = re.sub(r"^panych\.\s*", "Panychída ", text, flags=re.I)
    if re.fullmatch(r"M\s*Y\s*R\s*O\s*V\s*A\s*N\s*I\s*E", text, re.I):
        return "Myrovanie"
    if re.fullmatch(r"ODPUST\s*\.\s*SLÁVNOSŤ", text, re.I):
        return "Odpustová slávnosť"
    return text


def event_details(cells, events):
    groups = []
    pending = []
    loose = []
    for cell in cells:
        for line in comment_lines(cell):
            text = note_text(line)
            if not text or NO_LITURGY.fullmatch(text.rstrip("!.")):
                continue
            if text == "Odpustová slávnosť":
                pending.append(text)
            elif line.startswith(("+", "*")) or STANDALONE.match(text):
                if line.startswith(("+", "*")):
                    intention, _, note = text.partition("=")
                    intention = re.sub(r"\s+\d+(?=\s*(?:/|$))", "", intention.strip())
                    details = [intention]
                    if note.strip(" ="):
                        details.append(note_text(note))
                    label = None
                else:
                    details = [text]
                    label = text
                groups.append((label, pending + details))
                pending = []
            elif groups:
                groups[-1][1].append(text)
            else:
                loose.append(text)
    if len(groups) == len(events):
        for event, (label, details) in zip(events, groups):
            event["details"] = details
            if label:
                event["label"] = label
    else:
        loose.extend(detail for _, details in groups for detail in details)
    return loose + pending


def parse_article(page, url):
    start, end = period_dates(page)
    tables = [list(table_rows(table)) for table in page.xpath("//table")]
    rows = [row for table in tables for row in table]
    declared_start = start
    declared_dates = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    date_keys = {(day.day, day.month) for day in declared_dates}
    if (end - start).days == 6 and not any((number, month) in date_keys for (_, number, month), _ in rows):
        corrected = recover_week(start, tables)
        if corrected:
            start, end = corrected, corrected + timedelta(days=6)
    dates = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    by_day = {(item.day, item.month): item for item in dates}
    days = {}
    for (weekday, number, month), cells in rows:
        actual_date = by_day.get((number, month))
        if actual_date is None:
            continue
        if weekday != WEEKDAYS[actual_date.weekday()] or len(cells) < 3:
            raise ValueError(f"Nerozpoznaný riadok pre {actual_date}.")
        times = content(cells[2])
        events = parse_times(times, actual_date)
        key = actual_date.isoformat()
        entry = days.setdefault(key, {"date": key, "feast": content(cells[1]), "events": [], "notes": []})
        comments = " ".join(content(cell) for cell in cells[3:])
        if not events and NO_LITURGY.search(" ".join((times, comments))):
            entry["message"] = "Svätá liturgia nebude."
        notes = event_details(cells[3:], events)
        entry["events"].extend(event for event in events if event not in entry["events"])
        entry["notes"].extend(notes)
    if not any(entry["events"] or entry.get("message") for entry in days.values()):
        raise ValueError("Nenašli sa riadky s časmi a obcami.")
    for entry in days.values():
        entry["events"].sort(key=lambda event: event["time"])
    schedule = {"start": start.isoformat(), "end": end.isoformat(), "source": url,
                "days": sorted(days.values(), key=lambda entry: entry["date"])}
    if start != declared_start:
        schedule["dateNote"] = "Rozsah je určený podľa dátumov pri jednotlivých dňoch farskej tabuľky."
    return schedule


def class_nodes(page, name):
    return page.xpath('//*[contains(concat(" ", normalize-space(@class), " "), $name)]', name=" " + name + " ")


def article_body(page):
    bodies = class_nodes(page, "entry-body")
    return bodies[0] if bodies else page


def is_schedule(page, url):
    body = article_body(page)
    title = page.xpath("string(//title)")
    return bool(PERIOD.search(content(body)) or body.xpath(".//table") and
                any(DAY.match(content(cells[0])) for row in body.xpath(".//tr")
                    if (cells := row.xpath("./td|./th"))) or "liturgick" in title.lower() or "liturgicky-" in url.rsplit("/", 1)[-1])


def parse_announcement(page, url):
    bodies = class_nodes(page, "entry-body")
    if not bodies:
        raise ValueError("Nenašlo sa telo farského oznamu.")
    body = bodies[0]
    title = page.xpath("string(//title)").split(" - ")[0].split(" | ")[0].strip() or "Farský oznam"
    paragraphs = list(comment_lines(body))
    images, links = [], []
    for tag, target, attribute in [("img", images, "src"), ("a", links, "href")]:
        for node in body.xpath(".//" + tag + "[@" + attribute + "]"):
            href = urljoin(url, node.get(attribute))
            if urlsplit(href).scheme not in {"http", "https"}:
                continue
            entry = {"url": href, "alt" if tag == "img" else "title": node.get("alt", "") if tag == "img" else content(node)}
            if entry not in target:
                target.append(entry)
    if not paragraphs and not images and not links:
        raise ValueError("Farský oznam je prázdny.")
    dates = class_nodes(page, "entry-date")
    published = None
    if dates and (match := re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", content(dates[0]))):
        day, month, year = map(int, match.groups())
        published = date(year, month, day).isoformat()
    return {"title": title, "source": url, "published": published,
            "paragraphs": paragraphs, "images": images, "links": links}


def import_schedules(today):
    page = fetch(SOURCE)
    links = article_links(page, schedules_only=False)
    if not links:
        anchors = page.xpath("//a[@href]")
        print(
            f"Zdroj: {page.base_url or SOURCE}. Titulok: {page.xpath('string(//title)').strip()[:120]}. "
            f"Počet odkazov: {len(anchors)}.",
            file=sys.stderr,
        )
        for anchor in [item for item in anchors if re.search(r"blog|poriad|sambron", item.get("href"), re.I)][:12]:
            href = urlsplit(anchor.get("href"))
            print(f"Odkaz: {href.path[:200]} — {content(anchor)[:80]}", file=sys.stderr)
        raise ValueError("Na farskej stránke sa nenašli odkazy na poriadky.")

    cutoff = (today - timedelta(days=28)).isoformat()
    previous_data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    previous = previous_data["schedules"]
    notices = {item["source"]: item for item in previous_data.get("announcements", [])}
    by_url = {item["source"]: item for item in previous if item["end"] >= cutoff}
    valid = 0
    for url in links[:30]:
        try:
            article = fetch(url)
            if not is_schedule(article, url):
                notices[url] = parse_announcement(article, url)
                by_url.pop(url, None)
                valid += 1
                continue
            schedule = parse_article(article, url)
            notices.pop(url, None)
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
    announcements = sorted(notices.values(), key=lambda item: (item.get("published") or "", item["source"]), reverse=True)[:12]
    result = json.dumps({"schedules": schedules, "announcements": announcements}, ensure_ascii=False, indent=2) + "\n"
    if result != OUTPUT.read_text(encoding="utf-8"):
        temp = OUTPUT.with_suffix(".tmp")
        temp.write_text(result, encoding="utf-8")
        temp.replace(OUTPUT)
    print(f"Spracovaných príspevkov: {valid}. Uložených poriadkov: {len(schedules)}. Oznamov: {len(announcements)}.")


if __name__ == "__main__":
    try:
        import_schedules(datetime.now(ZoneInfo("Europe/Bratislava")).date())
    except (ValueError, OSError, html.etree.LxmlError) as error:
        sys.exit(f"Import zlyhal: {error}")
