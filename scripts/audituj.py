"""Skontroluje najnovšie poriadky zo zdroja bez zápisu verejných dát."""

from collections import Counter
from datetime import date
import re
import sys

from importuj import CLOCK, DAY, SOURCE, article_links, content, fetch, parse_article


def main():
    listing = fetch(SOURCE)
    for a in listing.xpath('//a[@href]'):
        href = a.get('href', '')
        if '/-/blogs/' in href and 'liturgicky-' not in href:
            print('OTHER LINK', href, content(a)[:120])
    notice = fetch(SOURCE + '/-/blogs/dolezity-oznam')
    for node in notice.xpath('//*[@class]'):
        if any(word in node.get('class', '') for word in ['entry-', 'publish', 'asset-']):
            print('NOTICE NODE', node.tag, node.get('class'), content(node)[:5000])
    urls = article_links(listing)[:20]
    if not urls:
        sys.exit("Na farskej stránke sa nenašli odkazy na poriadky.")
    totals = Counter()
    for url in urls:
        slug = url.rsplit("/", 1)[-1]
        try:
            page = fetch(url)
        except OSError as error:
            print(f"CHYBA {slug}: {error}")
            totals["chyby"] += 1
            continue
        try:
            schedule = parse_article(page, url)
        except ValueError as error:
            print(f"CHYBA {slug}: {error}")
            for row in page.xpath("//tr"):
                cells = [content(cell) for cell in row.xpath("./td|./th")]
                if len(cells) >= 3 and DAY.match(cells[0]):
                    print(f"  Riadok {cells[0]}: {cells[2][:110]}")
            totals["chyby"] += 1
            continue
        start = date.fromisoformat(schedule["start"])
        end = date.fromisoformat(schedule["end"])
        missing = (end - start).days + 1 - len(schedule["days"])
        events = sum(len(day["events"]) for day in schedule["days"])
        rows_without_times = sum(not day["events"] for day in schedule["days"])
        print(f"OK {slug} {start} až {end}: {len(schedule['days'])} dní, {events} termínov, "
              f"{missing} dní bez riadka, {rows_without_times} riadkov bez termínu.")
        if schedule.get("dateNote"):
            print("  Rozsah určený podľa dátumov v tabuľke.")
            totals["opravené rozsahy"] += 1
        totals["termíny bez obce"] += sum(
            event["town"] is None for day in schedule["days"] for event in day["events"]
        )
        for row in page.xpath("//tr"):
            cells = [content(cell) for cell in row.xpath("./td|./th")]
            if len(cells) < 3 or not DAY.match(cells[0]):
                continue
            if not re.search(CLOCK, cells[2]) and cells[2]:
                # Vypíšu sa iba tvary, ktoré opisujú čas alebo miesto.
                print(f"  Časový stĺpec {cells[0]}: {cells[2][:75]}")
            if len(cells) > 3 and re.search(r"\b(spoveď|ruženec|moleben|večiereň|sprievod|panychída|myrovanie)\b", cells[3], re.I):
                totals["poznámky k dňom"] += 1
        totals["poriadky"] += 1
        totals["termíny"] += events
        totals["dni bez riadka"] += missing
    print(f"Výsledok kontroly: {dict(totals)}")
    if totals["chyby"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
