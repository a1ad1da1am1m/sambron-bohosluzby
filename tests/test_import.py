import gzip
import json
import tempfile
import unittest
from datetime import date
from email.message import Message
from io import BytesIO
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
    def test_fetch_decodes_gzip_without_content_encoding(self):
        response = BytesIO(gzip.compress("<title>Poriadok Šambron</title>".encode()))
        response.headers = Message()
        response.url = importuj.SOURCE
        with patch.object(importuj, "urlopen", return_value=response):
            source = importuj.fetch(importuj.SOURCE)
        self.assertEqual(source.xpath("string(//title)"), "Poriadok Šambron")

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
        self.assertEqual(thursday["events"][0], {"town": "Hromoš", "time": "09:00", "details": ["+ Úmysel"]})
        self.assertEqual(thursday["events"][1]["label"], "spoveď chorých")
        self.assertEqual(thursday["notes"], [])
        self.assertEqual(len(sunday["events"]), 4)
        self.assertEqual(sunday["events"][1], {"town": "Bajerovce", "time": "09:00"})
        self.assertEqual(sunday["notes"], ["slávnostný ruženec"])

    def test_intentions_and_remarks_follow_their_source_times(self):
        source = article("od 02.11. do 08.11.2026", """
            <tr><td>PONDELOK 02.11.</td><td>Pamiatka zosnulých</td>
            <td><p>H 15.45</p><p>Š 17.30</p></td>
            <td><p>+ naši zosnulí = <em>HRAMOTY</em></p><p>= panych.na cintoríne =</p>
            <p>+ duše v očistci</p><p>= panych.pri cerkvi =</p></td></tr>
            <tr><td>STREDA 04.11.</td><td>Sviatok</td><td>B 15.15<br>B 15.45<br>Š 17.30</td>
            <td><p><i>= spoveď pred odpustom</i><br>+ Ján, Juraj, ...</p><p>(d.A. Príkladová 41)</p>
            <p>+ Michal 23</p></td></tr>
            <tr><td>NEDEĽA 08.11.</td><td>Nedeľa</td><td>H 08.00<br>Š 09.00<br>B 10.30</td>
            <td><p>* Juraj s rod.<br>(r.Príkladova 75)<br>= myrovanie =<br>* veriaci farnosti /csl./
            <br>= myrovanie =<br><u>ODPUST.SLÁVNOSŤ</u><br>* rod. Príkladova 23</p>
            <p>= myrovanie + sprievod =</p></td></tr>
        """)
        monday, wednesday, sunday = importuj.parse_article(source, ARTICLE)["days"]
        self.assertEqual([e["details"] for e in monday["events"]], [
            ["+ naši zosnulí", "HRAMOTY", "Panychída na cintoríne"],
            ["+ duše v očistci", "Panychída pri cerkvi"],
        ])
        self.assertEqual(wednesday["events"][0]["label"], "spoveď pred odpustom")
        self.assertEqual(wednesday["events"][1]["details"], ["+ Ján, Juraj, ..."])
        self.assertEqual(wednesday["events"][2]["details"], ["+ Michal"])
        self.assertEqual(sunday["events"][2]["details"],
                         ["Odpustová slávnosť", "* rod. Príkladova", "myrovanie + sprievod"])
        self.assertEqual(sunday["notes"], [])

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

    def test_time_without_town_keeps_its_place_unknown(self):
        source = article("od 10.08. do 16.08.2026",
                         "<tr><td>SOBOTA 15.08.</td><td>Sviatok</td><td>H 08.00 B 09.15 Š 10.30<br>13.30</td></tr>")
        data = importuj.parse_article(source, ARTICLE)
        self.assertEqual(data["days"][0]["events"][-1], {"time": "13:30", "town": None})

    def test_complete_week_can_correct_mistyped_header(self):
        rows = [
            "<tr><td>PONDELOK 27.07.</td><td></td><td>Š 17.30</td></tr>",
            "<tr><td>UTOROK 28.07.</td><td></td><td>H 15.45</td></tr>",
            "<tr><td>STREDA 29.07.</td><td></td><td>Š 07.00</td></tr>",
            "<tr><td>ŠTVRTOK 30.07.</td><td></td><td></td><td>SV.LITURGIA<br>NEBUDE!</td></tr>",
            "<tr><td>PIATOK 31.07.</td><td></td><td>Š 17.30</td></tr>",
            "<tr><td>SOBOTA 01.08.</td><td></td><td>Š 07.00</td></tr>",
            "<tr><td>NEDEĽA 02.08.</td><td></td><td>H 08.00</td></tr>",
        ]
        source = article("od 20.07. do 26.07.2026", "".join(rows))
        data = importuj.parse_article(source, ARTICLE)
        self.assertEqual((data["start"], data["end"]), ("2026-07-27", "2026-08-02"))
        self.assertIn("dateNote", data)
        self.assertEqual(data["days"][3]["message"], "Svätá liturgia nebude.")
        with self.assertRaises(ValueError):
            importuj.parse_article(article("od 20.07. do 26.07.2026", "".join(rows[:-1])), ARTICLE)

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
