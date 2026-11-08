import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from lxml import html

from scripts import importuj

ARTICLE = importuj.SOURCE + "/-/blogs/liturgicky-pori-457"


def page(markup):
    return html.fromstring(markup)


def article(period, rows):
    return page(f"<article><p>Liturgický poriadok {period}</p><table>{rows}</table></article>")


class ImportTest(unittest.TestCase):
    def test_discovers_unique_parish_posts(self):
        links = importuj.article_links(page(f"""
            <a href="{ARTICLE}?show=1">Liturgický poriadok</a>
            <a href="/en{importuj.PATH}liturgicky-pori-457">Čítaj ďalej</a>
            <a href="{importuj.PATH}57782828">Liturgický poriadok</a>
            <a href="{importuj.PATH}put-do-mariapocsi">Iný oznam</a>
            <a href="https://example.com{importuj.PATH}123">Iný zdroj</a>
        """))
        self.assertEqual(links, [ARTICLE, importuj.SOURCE + "/-/blogs/57782828"])

    def test_multiple_towns_and_notes(self):
        source = article("od 05.10. do 11.10.2026", """
            <tr><td>ŠTVRTOK&nbsp;08.10.</td><td>Sviatok</td>
            <td>H 09.00<br>Š 11.00<br>Š 17.30</td>
            <td>+ Úmysel<br>= spoveď chorých =<br>+ Druhý úmysel</td></tr>
            <tr><td>NEDEĽA 11.10.</td><td>Nedeľa</td>
            <td><p>H 07.45</p><p>B 09.00</p><p>Š 10.00</p><p>Š 10.30</p></td>
            <td>= slávnostný ruženec =</td></tr>
        """)
        data = importuj.parse_article(source, ARTICLE)
        thursday, sunday = data["days"]
        self.assertEqual(thursday["date"], "2026-10-08")
        self.assertEqual(thursday["events"][0], {"town": "Hromoš", "time": "09:00"})
        self.assertEqual(thursday["notes"], ["spoveď chorých"])
        self.assertEqual(len(sunday["events"]), 4)
        self.assertEqual(sunday["events"][1], {"town": "Bajerovce", "time": "09:00"})
        self.assertEqual(sunday["notes"], ["slávnostný ruženec"])

    def test_range_spans_new_year(self):
        source = article("od 28.12. do 03.01.2027",
                         "<tr><td>PIATOK 01.01.</td><td>Sviatok</td><td>Š 9:00</td></tr>")
        data = importuj.parse_article(source, ARTICLE)
        self.assertEqual(data["start"], "2026-12-28")
        self.assertEqual(data["days"][0]["date"], "2027-01-01")

    def test_unknown_place_is_not_silently_dropped(self):
        source = article("od 05.10. do 11.10.2026",
                         "<tr><td>ŠTVRTOK 08.10.</td><td>Sviatok</td><td>Š 09.00 X 12.00</td></tr>")
        with self.assertRaisesRegex(ValueError, "Nerozpoznané miesto"):
            importuj.parse_article(source, ARTICLE)

    def test_updates_same_url_and_keeps_data_on_source_failure(self):
        listing = page(f'<a href="{ARTICLE}">Liturgický poriadok</a>')
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "poriadky.json"
            output.write_text('{"schedules": []}', encoding="utf-8")
            with patch.object(importuj, "OUTPUT", output):
                for hour in (17, 18):
                    source = article("od 05.10. do 11.10.2026",
                                     f"<tr><td>ŠTVRTOK 08.10.</td><td>Sviatok</td><td>Š {hour}.30</td></tr>")
                    with patch.object(importuj, "fetch", side_effect=[listing, source]):
                        importuj.import_schedules(date(2026, 10, 8))
                    schedules = json.loads(output.read_text())["schedules"]
                    self.assertEqual(len(schedules), 1)
                    self.assertEqual(schedules[0]["days"][0]["events"][0]["time"], f"{hour}:30")
                last_good = output.read_bytes()
                with patch.object(importuj, "fetch", side_effect=[listing, URLError("výpadok")]):
                    with self.assertRaisesRegex(ValueError, "žiadny platný poriadok"):
                        importuj.import_schedules(date(2026, 10, 8))
                self.assertEqual(output.read_bytes(), last_good)


if __name__ == "__main__":
    unittest.main()
