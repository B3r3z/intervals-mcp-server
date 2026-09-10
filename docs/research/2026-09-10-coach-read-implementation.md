# Usprawnienia odczytów coacha — implementacja i weryfikacja

Zaimplementowano zakres P1 z [specyfikacji](../specs/coach-live-read-improvements.md), wynikający z [audytu live](2026-09-10-live-coach-audit.md). Zmiany są lokalne w checkoutcie; zastane zmiany robocze zachowano. Nie wykonano commitu, push ani wdrożenia kontenera.

## Zachowanie po zmianie

| Obszar | Wynik |
|---|---|
| Streamy | Brak lub null opcjonalnego `data2` nie powoduje fałszywej niekompletności. Obecne tablice wtórne nadal podlegają kontroli długości. |
| `get_activity_data_quality` | Odczytuje wszystkie zwrócone próbki, liczy wartości skończone, null, wartości nieprzydatne do analizy numerycznej i zera. Raportuje wyrównanie tablic, przerwy, duplikaty i cofnięcia czasu oraz kroki różne od 1 s. Zachowuje niezależny wynik metadanych aktywności i dostępność feedbacku. |
| Krzywe zmęczenia | Każdy odrębny wariant jest pobierany osobno. Błąd opcjonalnego wariantu pozostawia poprawne krzywe. Brak powtórzenia selektora przez API pozostaje jawnym `not_echoed`, bez fałszywego alarmu o brakujących punktach. |
| Kontekst sesji | Jawne `paired_event_id=null` daje `ok/unpaired`. Opcjonalne sekcje `activities`, `contextual_events` i wellness używają wspólnego okna przed/po sesji, po 0–31 dni. Daty nie tworzą powiązania z planem. Domyślne sekcje pozostają bez dodatkowych odczytów historii. |
| Definicje danych | Kompaktowe custom items pokazują kod, deklarowane pole FIT, typ i jednostki. Dodano 9 definicji metryk, z odrębną nieznaną semantyką HRV aktywności. |
| `get_activity_power_hr` | Pobiera natywny wynik moc–tętno wraz z oknami, opóźnieniem HR i współczynnikami. Kompakt zachowuje do 120 wierszy serii i 8 krzywych, z limitem danych 32 KiB. Wersja pełna zachowuje cały obiekt JSON. |
| Rejestracja | Katalog obejmuje 34 narzędzia admin, 26 coach i 24 readonly. Opis efektów kontekstu uwzględnia pamięciowy snapshot historii. |

## Testy syntetyczne i kontrakt

- Pełny pytest: **569 passed, 1 skipped**, Python 3.12, 52,69 s. Pominięty test dowiązania symbolicznego zależy od możliwości środowiska Windows.
- Ruff: **passed**. Mypy: **passed**, 82 pliki źródłowe i testowe.
- OpenAPI: **23 wybrane operacje i SHA256 zgodne** z pobraną publiczną specyfikacją. Dodano kontrakt `getPowerVsHR`, `PowerVsHRPlot`, `Bucket` i `Curve`; pozostała semantyka wybranego API nie zmieniła się.
- Rzeczywisty proces MCP stdio: nowy scenariusz przechodzi od discovery przez streamy, jakość, częściowo niedostępne krzywe, kontekst do kompaktowej i pełnej analizy moc–tętno. Każda odpowiedź jest sprawdzana względem reklamowanego schematu i tekstowej reprezentacji JSON. Transport syntetyczny rejestruje wyłącznie GET w tym scenariuszu.
- Zaktualizowano istniejący scenariusz krzywych V1, aby upstream syntetyczny respektował pojedyncze selektory. Po końcowej korekcie lint tej fixture powtórzono jej scenariusz protokołu.
- `git diff --check`: **passed**. Zmiany w plikach z wcześniejszą pracą porównano również z kopią stanu sprzed tej implementacji.

Polecenia do odtworzenia kontroli:

```powershell
uv --cache-dir .uv-cache run --offline --no-sync pytest --basetemp=.runtime/pytest-coach-improvements-review --tb=short
uv --cache-dir .uv-cache run --offline --no-sync ruff check .
uv --cache-dir .uv-cache run --offline --no-sync mypy src tests
uv --cache-dir .uv-cache run --offline --no-sync python scripts/check_openapi_contract.py --spec .runtime/coach-read-improvements-20260910/openapi.json
```

## Powtórka live: trening z 5 września 2026

Przeprowadzono **13 wywołań MCP, 8 różnych narzędzi**, w tym powtórkę obu nowych odczytów po końcowych poprawkach walidacji. Wykonano **19 żądań GET: 17 × HTTP 200, 2 × HTTP 422**. Wszystkie 13 odpowiedzi przeszło walidację schematów i porównanie `structuredContent` z tekstowym JSON. Liczba żądań mutujących: **0**.

| Kontrola | Obserwacja live |
|---|---|
| Fragment streamów | `ok`, `aligned`, kompletne żądane 300 próbek. Wartości identyczne z odpowiednią częścią odpowiedzi API; null `data2` zachowany. |
| Jakość danych | 13 streamów po 15 016 próbek. 27 odstępów większych od 1 s; największy 430 s. Suma odstępów niepokrytych względem odniesienia 1 Hz wynosi 2189 s. Brak duplikatów i cofnięć czasu. Osobno zachowano 27 markerów zatrzymania rejestracji. |
| Krzywa normalna | `ok`, poprawne punkty mocy mimo braku echa selektora. |
| Normalna + kj0 + kj1 | `partial`; krzywa normalna i jej punkty pozostały zachowane, dwa warianty zwróciły odrębne HTTP 422 z instrukcją sprawdzenia ustawień i parametrów. Sam kod HTTP nie służy do przypisywania przyczyny. |
| Kontekst | Wszystkie 7 zamówionych sekcji ma `ok`; plan `unpaired`. Okno od 29 sierpnia do 7 września włącznie zawiera 10 rekordów wellness, 6 aktywności i 6 wydarzeń. Pominięcia pól w kompakcie pozostają jawne. |
| Moc–tętno | Natywne `decoupling=6.482107`, `hrLag=30`. Kompakt zawiera 120 z 227 wierszy i deklaruje pominięcie 107; pełny wynik jest identyczny z obiektem API. |
| Custom items | Kompakt udostępnia m.in. `TymeVentilation → tyme_minute_volume` i `TymeBreathRate → tyme_breath_rate`. Są to deklaracje pól, bez twierdzenia o obecności ich próbek. |

Surowe dane konta, log żądań bez nagłówków uwierzytelnienia, plany wywołań i automatyczne asercje pozostają w ignorowanym `.runtime/coach-read-improvements-20260910/`. Plik `verification.json` potwierdza liczniki i zachowanie danych źródłowych. Dane z wcześniejszego audytu nie zostały nadpisane.

## Granice wyniku

Weryfikacja live dotyczy wybranych odczytów tego checkoutu przez MCP stdio i jednej aktywności. Nie potwierdza zainstalowanego kontenera, rejestracji w GUI ani zapisów na konto; `live_verified=false` pozostaje w ogólnych capabilities.

Narzędzia zapewniają teraz czytelniejszą podstawę do analizy coacha. Nie tworzą brakującego feedbacku zawodnika ani próbek sensorów. Nie wdrożono dopasowania planowanych kroków do wykonania, pełnej ekstrakcji serii siłowych/FIT, narzędzi pogody i histogramów — są poza zakresem tej specyfikacji.

Lokalna specyfikacja jest gotowa. Automatyczna kontrola zatwierdzeń odrzuciła jej publikację jako issue w `B3r3z/intervals-mcp-server`, wskazując brak wyraźnej zgody na konkretny dokument i miejsce publikacji. Issue z etykietą `ready-for-agent` nie zostało utworzone; ponowienie wymaga zgody użytkownika. Dokument przeznaczony do issue nie zawiera danych treningu ani identyfikatorów zawodnika.
