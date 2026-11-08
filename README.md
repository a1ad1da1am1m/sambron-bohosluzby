# Poriadok bohoslužieb · Farnosť Šambron

Prehľad pre Šambron, Bajerovce a Hromoš. Zdrojom je [farská stránka na Moja Komunita](https://www.mojakomunita.sk/web/gkc-farnost-sambron/poriadok-bohosluzieb). Stránka ukazuje dnešné časy, najbližší termín a jednotlivé poriadky s odkazom na originál. Úmysly a liturgické poznámky sa priraďujú k času, keď majú v zdroji zodpovedajúce bloky v rovnakom poradí. Pri nejednoznačnom zápise ostanú pri dni. Úmysly aj údaje o darcoch vrátane pôvodných skratiek a čísel sa zachovávajú podľa farského originálu. Viacriadkové údaje v zátvorkách sa spájajú do jedného riadka. Samostatné farské oznamy sú pod rozpisom s dátumom zverejnenia, textom, obrázkami, prílohami a odkazom na originál.

## Spustenie na GitHube

1. Vytvor verejný repozitár `sambron-bohosluzby`. Nahraj celý obsah tohto priečinka do predvolenej vetvy vrátane `.github/workflows/poriadky.yml`. Pri nahrávaní cez Git sa priečinok `.github` prenesie spolu s ostatnými súbormi.
2. V repozitári otvor **Settings → Pages → Build and deployment → Source** a vyber **GitHub Actions**.
3. Otvor **Actions → Aktualizácia liturgických poriadkov → Run workflow**. Po úspešnom behu nájdeš URL v úlohe **publish** alebo v **Settings → Pages**. Na používateľskom účte má typicky tvar `https://TVOJ-UCET.github.io/sambron-bohosluzby/`.
4. Ak beh hlási problém s importom, otvor krok **Načítať farské poriadky**. Výpis rozlíši problém s prístupom k zdroju, chýbajúce odkazy a nerozpoznané riadky. Pri chybe importu prehľad používa naposledy uložené údaje, ak existujú.

Workflow kontroluje zdroj každé dve hodiny o 17. minúte. Počíta s možnými opravami pod rovnakou URL. Pri zmene spracovaných údajov uloží nový JSON aj do repozitára. Ak verejný repozitár zostane 60 dní bez aktivity, GitHub môže naplánované spúšťanie vypnúť. Opätovne ho zapneš v záložke Actions.

## Lokálne overenie

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests
python scripts/importuj.py
python -m http.server 8000 --directory site
```

Prehľad otvor na <http://localhost:8000>. Čerstvý projekt má prázdny JSON a poriadky sa doplnia pri úspešnom importe. Testy používajú malé ukážky štruktúry príspevkov a dajú sa spustiť bez prístupu k farskému webu.

## Kontrola formátov

Workflow **Kontrola formátov farských poriadkov** preverí až 30 najnovších príspevkov (poriadky aj oznamy) zo zoznamu a vypíše spracované termíny aj odchýlky bez zmeny verejného JSON. Spustiť ho možno ručne v záložke Actions alebo príkazom `python scripts/audituj.py`. Pri rozpore s nadpisom sa použijú dátumy z tabuľky, ak tvoria jediný úplný týždeň v okolí uvedených dátumov. Čas bez označenej obce sa zobrazí pri všetkých obciach s vysvetlením.

Hlavička používa fotografiu šambronskej cerkvi dodanú pre tento web. V pätičke je odkaz na [záznam snímky na Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Cerkovsambron.png).

## Farské oznamy

Import rozlišuje rozpis podľa jeho názvu a obsahu tabuľky. Poškodený poriadok sa nevydáva za oznam. Text oznamov sa načíta iba z tela článku, bez navigácie či komentárov, a vykresľuje cez `textContent`. Odkazy a obrázky pripúšťajú iba HTTP(S). Obrázkové plagáty sa zobrazujú ako obrázky s odkazom na otvorenie; ich text sa neprepisuje pomocou OCR.

JSON obsahuje polia `schedules` a `announcements`. Import kontroluje prvých 30 jedinečných odkazov na zdrojovej stránke, uchováva najviac 12 oznamov, opravy páruje podľa URL a pri zlyhaní konkrétneho článku zachová poslednú uloženú verziu. Oznamy staršie ako 45 dní sú označené ako staršie a predvolene zbalené. Neznámy dátum sa neodhaduje a taký oznam zostane tiež zbalený. Dátum zverejnenia neurčuje platnosť; formulácie ako „zajtra“ zostávajú v pôvodnom znení. Príspevky hlbšie v archíve za prvou stránkou sa automaticky nedohľadávajú.
