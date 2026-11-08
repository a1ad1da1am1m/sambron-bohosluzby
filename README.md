# Poriadok bohoslužieb · Farnosť Šambron

Prehľad pre Šambron, Bajerovce a Hromoš. Zdrojom je [farská stránka na Moja Komunita](https://www.mojakomunita.sk/web/gkc-farnost-sambron/poriadok-bohosluzieb). Stránka ukazuje dnešné časy, najbližší termín a jednotlivé poriadky s odkazom na originál. Pri vybraných poznámkach sa zachováva priradenie k dňu. Úmysly a úplné oznamy sú vo farskom origináli.

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
