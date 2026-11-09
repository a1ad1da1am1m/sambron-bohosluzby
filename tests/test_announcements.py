import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from lxml import html
from scripts import importuj

URL = importuj.SOURCE + '/-/blogs/dolezity-oznam'
NOTICE = '''<html><head><title>Dôležitý oznam - Poriadok bohoslužieb</title></head><body>
<div class="entry-body"><p>FARSKÝ OZNAM:</p><p>Zajtra je sviatok.<br>Liturgia o 09.00.</p>
<img src="/documents/plagat.jpg" alt="Plagát"><a href="/documents/oznam.pdf">Podrobnosti</a>
<a href="javascript:alert(1)">Nebezpečný odkaz</a></div>
<div class="entry-footer"><div class="entry-date">28.8.2026 14:23</div></div>
<aside>Liturgický poriadok od 02.11. do 08.11.2026</aside></body></html>'''

class AnnouncementsTest(unittest.TestCase):
    def test_links_include_notices_but_not_rss_external_or_duplicates(self):
        listing = html.fromstring(f'<div><a href="{URL}">Oznam</a><a href="{URL}#comments">Komentáre</a>'
                                  f'<a href="{importuj.SOURCE}/-/blogs/rss">RSS</a>'
                                  '<a href="https://example.org/web/gkc-farnost-sambron/poriadok-bohosluzieb/-/blogs/fake">Fake</a></div>')
        self.assertEqual(importuj.article_links(listing, False), [URL])
        self.assertEqual(importuj.article_links(listing), [])

    def test_notice_uses_article_body_not_sidebar_and_keeps_media(self):
        page = html.fromstring(NOTICE)
        self.assertFalse(importuj.is_schedule(page, URL))
        data = importuj.parse_announcement(page, URL)
        self.assertEqual(data['title'], 'Dôležitý oznam')
        self.assertEqual(data['published'], '2026-08-28')
        self.assertIn('Liturgia o 09.00.', data['paragraphs'])
        self.assertNotIn('Liturgický poriadok', ' '.join(data['paragraphs']))
        self.assertEqual(data['images'][0]['url'], 'https://www.mojakomunita.sk/documents/plagat.jpg')
        self.assertEqual(len(data['links']), 1)

    def test_image_only_notice_and_missing_date(self):
        data = importuj.parse_announcement(html.fromstring('<div class="entry-body"><img src="/poster.png"></div>'), URL)
        self.assertIsNone(data['published'])
        self.assertEqual(data['paragraphs'], [])
        self.assertEqual(len(data['images']), 1)

    def test_notice_only_update_preserves_schedules_and_failed_notices(self):
        other = URL + '-2'
        listing = html.fromstring(f'<div><a href="{URL}">Oznam</a><a href="{other}">Iný oznam</a></div>')
        previous = {'schedules': [{'source': 'old', 'start':'2026-11-02','end':'2026-11-08','days':[]}],
                    'announcements': [{'source':other,'published':'2026-08-01','title':'Uložený oznam'}]}
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'poriadky.json'
            output.write_text(json.dumps(previous))
            with patch.object(importuj, 'OUTPUT', output), patch.object(importuj, 'fetch', side_effect=[listing,html.fromstring(NOTICE),URLError('offline')]):
                importuj.import_schedules(date(2026,11,8))
            data = json.loads(output.read_text())
            self.assertTrue(data['partialCheck'])
            self.assertIn('lastCheckedAt', data)
            self.assertEqual(data['schedules'], previous['schedules'])
            self.assertEqual(len(data['announcements']), 2)
            self.assertEqual(data['announcements'][0]['source'], URL)

    def test_broken_schedule_is_not_mislabeled_as_notice(self):
        page = html.fromstring('<title>Liturgický poriadok</title><div class="entry-body">Nečitateľná tabuľka</div>')
        self.assertTrue(importuj.is_schedule(page, URL))
        with self.assertRaises(ValueError):
            importuj.parse_article(page, URL)

if __name__ == '__main__':
    unittest.main()
