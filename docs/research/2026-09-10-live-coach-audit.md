# Test live narzędzi Intervals.icu z perspektywy coacha

**Werdykt:** obecny zestaw pozwala przeprowadzić sensowną analizę kolarską: poznać obciążenie, odcinki wysiłku, historię, zadeklarowane odżywianie i reakcję po sesji. Największą przeszkodą jest interpretacja i organizacja odpowiedzi. Część stanów `partial` wynika z fałszywych alarmów lub braku opcjonalnej konfiguracji. Do pełnej oceny przyczyn trudności nadal potrzebny jest feedback zawodnika.

Test wykonano 10 września 2026 na rzeczywistym koncie. Nie zmieniano kalendarza, aktywności, komentarzy ani ustawień. Powstały lokalne artefakty i ten raport. Szczegóły możliwości API opisuje osobny [raport dokumentacyjny](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/docs/research/2026-09-10-intervals-api-coach-opportunities.md).

## Zakres i dowody

W tej sesji Codex nie miał bezpośrednio zarejestrowanych narzędzi Intervals. Uruchomiono bieżący checkout przez `mcp run src/intervals_mcp_server/server.py` i rzeczywisty klient MCP stdio, z `INTERVALS_ACCESS_MODE=readonly`. Serwer korzystał z istniejącej konfiguracji konta. Instrumentacja zapisywała odpowiedzi prawdziwego HTTP i blokowała metody inne niż odczyt; nie używano transportu mockującego odpowiedzi.

- **77 wywołań MCP, 22 różne narzędzia**, czyli wszystkie narzędzia odkryte w trybie `readonly`.
- Z tych wywołań wynikło **39 żądań GET do API: 38 × HTTP 200, 1 × HTTP 422**.
- Osobno sprawdzono 3 udokumentowane endpointy jako kandydatów do rozszerzenia MCP: wszystkie zwróciły HTTP 200. Łącznie **42 uwierzytelnione GET i zero zapisów na koncie**.
- Wszystkie 77 odpowiedzi spełniło odkryty `outputSchema`; tekstowa reprezentacja odpowiadała `structuredContent`. Nie było błędu transportu MCP.
- Statusy aplikacyjne: 23 `ok`, 50 `partial`, 4 `error`. To nie oznacza 54 nieudanych testów: 38 odpowiedzi `partial` stanowiło poprawne fragmenty eksportu z dalszymi bajtami do pobrania. Trzy `error` były oczekiwanymi próbami negatywnymi; jeden dotyczył nieustawionego progu kJ.
- Testowano też paginację trzech aktywności po jednym rekordzie, zgodny i niezgodny identyfikator snapshotu oraz pobieranie artefaktu po ponownym uruchomieniu procesu serwera.

Stan kodu: `HEAD 9f60ce0bbd8854682175732b04823dd344fc2b18` plus zastane zmiany robocze. Test nie edytował kodu produkcyjnego ani testów. Nie jest to potwierdzenie działania zainstalowanego kontenera ani bezpośredniej rejestracji narzędzi w GUI Codex. Nie uruchamiano pełnego pytest/ruff/mypy: zakres obejmował eksperyment live i dokumentację, bez zmian implementacji i bez commitu.

Dowody lokalne, wyłączone z Git przez istniejące `.runtime/`: [podsumowanie i hashe źródeł](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/audit-summary.json), [odkryte schematy MCP](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/discovery.json), [rejestr wywołań](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/cases.jsonl), [odpowiedzi HTTP](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/http.jsonl), [runner](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/runner.py). Nie zapisano klucza API ani nagłówków autoryzacji.

## Co coach może ustalić o 5 września

Tego dnia znaleziono trzy aktywności o tej samej nazwie. Do analizy wybrano najdłuższą, `i183591082`, rozpoczętą o 10:43:18 czasu lokalnego: „Kościelisko Kolarstwo szosowe”. Pozostałe trwały 15:25 i 5:28 ruchu. Kalendarz zawiera wydarzenie `RACE_A` „Tatra Road Race”, ale główny zapis ma `paired_event_id=null` i `race=false`. Wydarzenie jest istotnym kontekstem, a jego formalne powiązanie z aktywnością nie jest potwierdzone przez API.

| Obszar | Wynik live | Znaczenie w analizie |
| --- | --- | --- |
| Objętość | 80,684 km; 2083 m przewyższenia; ruch 4:09:43; całkowity czas 4:46:44 | Długa, górska jazda; trzeba rozróżniać czas ruchu, nagrania i całkowity. |
| Moc | Średnia aktywności 135 W; moc ważona 191 W; FTP przypisane aktywności 228 W; VI 1,415 | Średnia moc słabo oddaje wysiłki przy bardzo zmiennej jeździe. |
| Obciążenie | `icu_training_load=292`, `power_load=292`, `hr_load=287` z typem `HRSS`; `strain_score=326,56` | Różne miary są dostępne i powinny pozostać rozdzielone. Nie przemianowuję automatycznie ogólnego load na TSS ani SS. |
| Cały dzień | Suma load trzech zapisów: 308 | Jeden plik zaniżałby dzienny kontekst względem wszystkich zapisów. Suma odpowiada `ctlLoad` wellness tego dnia. |
| Intensywność | HR średnio 155, maks. 183 bpm; 1:11:01 w strefach mocy Z4–Z7 | Dane pokazują znaczny udział mocnych fragmentów mimo niskiej średniej mocy. |
| Najlepsze 5 min | 266 W na krzywej; best-efforts 266,33 W; statystyki odcinka 266 W i HR 175 bpm | Trzy odczyty są zgodne z uwzględnieniem zaokrąglenia. Odcinek `[350,650)` zaczyna się 5:50 po starcie. |
| Historia mocy | Poprzednie 28 dni: najlepsze 5 min 252 W, 10 min 240 W; w badanej jeździe 266 i 247 W | Można porównać wykonany wysiłek z historią. Sam rekord z tego zakresu nie dowodzi zmiany FTP ani VO₂max. |
| Feedback i jedzenie | `icu_rpe=9`, `feel=4`, 250 g węglowodanów; opis pusty, komentarze puste | Jest subiektywna trudność i ilość węglowodanów, ale brakuje opisu przebiegu, problemów i rozłożenia jedzenia. |
| Po wysiłku | HRV: 59 ms w dniu jazdy, 31 następnego dnia, 40 dzień później; średnia poprzednich 7 dni 62 ms | Reakcja po sesji jest widoczna. Nie ustala samodzielnie przyczyny zmiany HRV. |
| Sen i codzienna aktywność | Sleep score 72 → 36 → 64; 7 września 22 886 kroków | Coach ma kontekst poza samymi zarejestrowanymi treningami. |

Moja interpretacja trenerska: te dane wystarczają, aby rozpoznać duży koszt sesji, mocne wysiłki na początku i wyraźną zmianę wskaźników regeneracji po niej. Nie wystarczają, aby ustalić, czy problemem było tempo, żywienie, ból, warunki lub inna przyczyna. Nie oceniałbym realizacji celu wyścigu wyłącznie z mocy średniej, `compliance=0` ani etykiety interwału.

Obliczenia raportu są jawne: 250 g / 4:09:43 ruchu daje około 60,1 g/h; dzielenie przez 4:46:44 całkowitego czasu daje 52,3 g/h. To dwie podstawy czasowe tej samej deklaracji, a nie pomiar wchłaniania. Sumowano tylko rozłączne Z1–Z7; dodatkowego wpisu strefy `SS` nie dodawano ponownie. Wartość `carbs_used=527` jest oddzielnym wynikiem upstream, nie zmierzonym bilansem żywieniowym.

Źródła liczb: [szczegóły aktywności](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/responses/activity_details.json), [dane dnia](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/responses/activities_day.json), [wellness](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/responses/wellness_all.json), [krzywa aktywności](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/responses/activity_curve_default.json), [krzywa historyczna](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/responses/athlete_power_curve.json).

## Wyniki narzędzi

| Narzędzie lub grupa | Co sprawdzono i wynik |
| --- | --- |
| `get_capabilities` | 22 pozycje zgodne z discovery w `readonly`. Deklaracja `live_verified=false` pozostała bez zmian; ten audyt dotyczy konkretnych odczytów, nie gotowości zapisów. |
| `get_activities` | Dzień, historia 31 dni i paginacja. 3 i 23 rekordy; trzy strony dały te same ID bez duplikacji, jeden snapshot i koniec kursora. |
| `get_activity_details` | Pełne parametry, strefy, RPE, żywienie, urządzenie i pola custom; poprawna odpowiedź. |
| `get_activity_intervals` | Jeden odcinek całej jazdy, oznaczony `RECOVERY`; `icu_groups=null`. To faktyczny stan upstream, nie zgubienie interwałów przez MCP. |
| `get_activity_messages` | Pusta lista dla 5.09. Dodatkowa próba kontekstu z 3.09 odczytała istniejący komentarz wraz z jego ID. |
| `get_session_context` | Wszystkie sekcje w compact/full; działające szczegóły i wellness zachowane mimo błędu planu. Osobna aktywność z 3.09 miała prawidłowo odczytany powiązany plan. |
| `get_events`, `get_event_by_id` | Wydarzenie wyścigu, notatka o urlopie i plany z rozwiązaną strukturą. |
| `get_wellness_data` | 17 dni, wariant domyślny i `include_all_fields=true`; w tej próbce identyczne dane. |
| `get_sport_settings` | Compact/full; FTP i strefy dostępne, `after_kj0` i `after_kj1` jawnie puste. To ustawienia bieżące, oddzielone od przypisań historycznej aktywności. |
| `get_metric_definitions` | Katalog i selekcja nazw; 29 definicji. Jawne braki również dla kilku powszechnych pól, opisane niżej. Narzędzie lokalne. |
| `get_custom_items`, `get_custom_item_by_id` | Lista 61 elementów i pełne definicje trzech pól/strumieni. Dane działają, metadane bywają niepełne. |
| `get_athlete_power_curves` | Historyczny zakres, wszystkie siedem żądanych długości i ID źródłowych aktywności. |
| `get_activity_power_curves` | Zwykła krzywa ma punkty; wariant ze zmęczeniem zwraca 422 przy braku progów kJ. |
| `get_activity_best_efforts` | Trzy najlepsze 5-minutowe wysiłki z indeksami i średnią. |
| `get_activity_interval_stats` | Najlepsze 5 min i fragment z przerwami zapisu; prawidłowo rozróżnia indeksy próbek i sekundy. |
| `get_activity_streams` | Preview, zakres, zgodny snapshot, niezgodny snapshot i jawne nazwy custom. Dane dochodzą, ale klasyfikacja jakości ma wadę. |
| `export_activity_data`, `get_artifact_chunk` | 1 260 975 bajtów, 39 fragmentów. Każdy hash fragmentu, końcowy SHA-256, JSON i zgodność bajtowa z artefaktem potwierdzone. |
| `get_write_status`, `get_analysis_comment_status` | Tylko lokalny odczyt nieistniejącego UID z `reconcile=false`; oczekiwany brak rekordu. To nie test publikacji ani live reconciliation. |

Nie uruchamiano 10 narzędzi mutujących dostępnych w trybie admin. Nie tworzono testowego treningu ani komentarza. Żadnego wyniku odczytu nie należy traktować jako potwierdzenia bezpiecznego zapisu na konto.

## Najważniejsze problemy i braki

### 1. Fałszywy alarm jakości strumieni — pierwszy priorytet naprawy

Wszystkie siedem głównych tablic preview miało po **15 016 próbek**. Opcjonalne `data2` było `null`, co jest normalnym kształtem tych strumieni skalarnych. Mimo tego wynik zawierał `equal_source_lengths=false`, `quality=missing_arrays` i `UNEQUAL_STREAM_LENGTHS`. Pełny żądany zakres `[350,650)` dostał dodatkowo `MISSING_SAMPLE_INDICES`, choć główne tablice zawierały komplet 300 próbek.

To realna wada semantyki odpowiedzi: coach może niepotrzebnie odrzucić dobre dane. Trzeba oddzielić nieobecne opcjonalne `data2` od brakującego głównego sygnału. [Kod klasyfikacji](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/src/intervals_mcp_server/tools/activities.py:897), [dowód zakresu](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/responses/streams_range.json). Opcjonalność struktury potwierdza schema `ActivityStream` w [OpenAPI](https://intervals.icu/api/v1/docs).

Jednocześnie istnieją **rzeczywiste** cechy jakości wymagające podsumowania: oś czasu ma 27 odstępów dłuższych niż 1 s, największy 430 s; łącznie pomija 2189 sekund względem siatki 1 Hz. Aktywność ma również 27 `recording_stops`. To przerwy w zarejestrowanej osi, nie dowód zgubienia danych przez MCP. Kadencja ma 1738 nulli, oddech 31, moc i HR po zero nulli. Nie utożsamiam zer mocy z awarią czujnika.

### 2. Krzywe zmęczenia: brak konfiguracji blokuje także przydatny wynik

Żądanie `fatigue=[normal,kj0,kj1]` dało upstream 422: `Athlete has no kj0 defined`. Bieżące ustawienia potwierdziły `after_kj0=null` i `after_kj1=null`. Narzędzie przekazało ogólny opis HTTP 422, więc sam coach nie poznał konkretnej przyczyny bez dodatkowej diagnostyki.

Propozycja: sprawdzić dostępność selektorów lub pobierać je oddzielnie i zwracać per-wariant `available/not_configured/error`, zachowując zwykłą krzywą. Udokumentowany parametr listowy jest prawidłowy — problemem nie jest zapis listy. Nie trzeba ustawiać progów na koncie, aby wykonać analizę podstawową.

Dodatkowo działająca zwykła krzywa stale miała `FATIGUE_SELECTION_UNVERIFIED`, ponieważ odpowiedź nie powtarza pola `fatigue`. Należy osobno opisać kompletność punktów i potwierdzenie selektora; nie uznawać selekcji za zweryfikowaną tylko na podstawie `after_kj=0`. Szczegóły: [raport API](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/docs/research/2026-09-10-intervals-api-coach-opportunities.md).

### 3. Brak powiązanego planu jest zwykłym stanem domeny

`get_session_context` zwrócił dla 5.09 błąd sekcji planu `PAIRED_EVENT_NULL`, a dla całego kontekstu `partial`. Nie było błędu API: aktywność naprawdę nie ma przypisanego wydarzenia. Proponuję `availability=unpaired` zamiast błędu wykonania, z opcjonalną listą `contextual_events` z kalendarza. Wydarzenie wyścigu lub urlop pomaga w analizie, ale nie powinno być automatycznie uznane za powiązany plan.

Próba kontrolna z 3.09 potwierdziła, że ścieżka planu działa, gdy istnieje numeryczne powiązanie: odczytano plan 62 min z celami w W oraz wykonanie 35:07. API dostarcza materiał do porównania kroków, ale obecny zestaw nie daje jeszcze wygodnej tabeli „cel → wykonanie → różnica → pewność dopasowania”. `resolve=true` ma opisane znaczenie w [dokumentacji autora](https://forum.intervals.icu/t/downloading-planned-workouts-from-the-api/93737). Obecnie przechowywany plan nie musi być niezmienioną wersją z dnia wykonania.

### 4. Braki danych zawodnika, których nowy endpoint sam nie usunie

- **Feedback:** dla badanej jazdy brak opisu i komentarzy; wellness ma puste m.in. zmęczenie, bolesność, stres, uraz i uwagi. RPE 9 nie wyjaśnia, co ograniczało wykonanie.
- **Żywienie:** są gramy węglowodanów, brak rozłożenia w czasie, tolerancji i pełnego obrazu płynów. Nie można stwierdzić przyczyny trudności tylko z wyliczonego g/h.
- **Wentylacja Tymewear:** definicje `TymeVentilation` i `TymeBreathRate` istnieją na koncie, lecz nie zostały zwrócone dla tej aktywności także przy jawnym wskazaniu tych kodów. Jest natywny `respiration`; jego obecność nie dowodzi, że pochodzi z Tymewear. Dane nie pozwalają tutaj analizować VE/VT ani potwierdzać progów wentylacyjnych.
- **Podział jazdy:** upstream ma jeden interwał całej aktywności, `type=RECOVERY`, jedną lapę i `icu_intervals_edited=true`. To nie oznacza regeneracyjnego treningu. Potrzebne są statystyki wskazanych fragmentów lub jawnie wyliczony podział na wysiłki/podjazdy.
- **Siła:** w odczytanym zakresie nie było sesji siłowej do testu. Nie ma podstaw do deklaracji live, że odzyskujemy ćwiczenia, serie, powtórzenia i ciężary. Osobna próba rzeczywistej sesji/FIT pozostaje potrzebna.

### 5. Skrócone odpowiedzi i jednostki wymagają poprawy

Lista 23 aktywności zajęła **127,5 kB samego structured JSON**. Lista 61 custom items w trybie compact miała 38,5 kB, ale pomijała `content.code` i `fit_record_field`, potrzebne do ustalenia technicznych nazw czujników. Trzeba było otwierać pełne definicje po ID.

Kontekst sesji compact miał 13,3 kB wobec 16,2 kB full, czyli oszczędzał tylko około 18%. Same dane sekcji compact zajmowały 3,4 kB; reszta to obudowa, powtarzane pochodzenie danych i listy pominiętych pól. Przyda się selekcja pól/preset do analizy, z zachowaniem ostrzeżeń, pochodzenia i możliwości dokładnego odczytu. W domyślnych sekcjach kontekstu nie ma planu ani wellness, a wellness dodane jawnie obejmuje tylko dzień aktywności.

Streamy `respiration`, `temp`, `torque` i `hrv` miały `unit=null`. Katalog metryk nie rozpoznawał m.in. `decoupling`, `icu_intensity`, `icu_rpe`, `feel`, `icu_zone_times` oraz nazw custom. Proponuję uzupełnić znaczenie, skalę i jednostki natywnych pól oraz łączyć kody custom z ich deklaracjami. Szczególnie nie wolno utożsamiać strumienia `hrv` z dziennym wellness rMSSD bez definicji źródła.

## Co rozwinąłbym w następnej kolejności

| Priorytet | Zmiana | Uzasadnienie i podstawa |
| --- | --- | --- |
| P1 | Naprawić klasyfikację `data2`; zachować częściowy sukces krzywych; normalny stan braku planu | Konkretne przeszkody potwierdzone powyższymi próbami live. |
| P1 | `get_activity_data_quality` lub sekcja jakości w istniejącym kontekście | Pokrycie i nulle per sygnał, przerwy czasu, zapisane stop-y, korekty danych, dostępność odcinków, planu i feedbacku. Wszystkie potrzebne źródła już odczytujemy; obliczenia muszą mieć jawną metodę. |
| P1 | Rozszerzyć `get_session_context` o okno przed/po, wszystkie aktywności dnia, wydarzenia i selekcję pól | W jednej odpowiedzi połączyć 308 load dnia, trend HRV/snu i urlop. Nie dublować kalendarza ani sprowadzać regeneracji do jednej liczby readiness. |
| P1 | `get_activity_power_hr` | Nowy odczyt `/activity/{id}/power-vs-hr.json`; **sprawdzony live: 200**, 227 minutowych punktów, 3 krzywe, informacja o opóźnieniu HR i wyłączeniu rozgrzewki/schłodzenia. Najbardziej wartościowe rozszerzenie o istniejącą analizę upstream. |
| P2 | Porównanie kroków planu z wykonaniem | Złożyć istniejące resolved events, interwały i statystyki; pokazać niedopasowanie i niepewność. Nie wyprowadzać przyczyny skrócenia treningu bez rozmowy. |
| P2 | Pogoda fragmentu i histogramy | `/weather-summary` dla `[350,650)` oraz `/power-histogram?bucketSize=25` **sprawdzone live: 200**. Histogram to 20 przedziałów w 648 bajtach; pogoda pozwala analizować warunki konkretnego wysiłku. |
| P2 | Oryginalny FIT jako artefakt, potem próba ekstrakcji siły | API dokumentuje `/activity/{id}/file`. Obecny eksport obejmuje strumienie i interwały, nie oryginalny plik. Dostępność serii/powtórzeń trzeba potwierdzić na rzeczywistym nagraniu. |

Endpointy i parametry porównano z aktualnym [OpenAPI Intervals.icu](https://intervals.icu/api/v1/docs). Dowody trzech dodatkowych prób: [power-vs-HR](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/power_vs_hr-api.json), [pogoda fragmentu](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/weather_5min-api.json), [histogram](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/power_histogram-api.json).

Moje odczucie po pracy z zestawem: podstawowe odczyty są szybkie i dostarczają dużo przydatnych danych. Najwięcej wysiłku wymaga ustalenie, czy `partial` znaczy „normalna kontynuacja”, „brak pola na koncie”, „brak potwierdzenia selektora” czy „wadliwa odpowiedź”. Pierwszy etap rozwoju powinien uprościć tę interpretację i złożyć istniejące dane w użyteczny kontekst. Dopiero potem rozszerzałbym listę narzędzi.
