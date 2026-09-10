# Intervals.icu API: dane dla coacha i priorytety usprawnień

Stan sprawdzony 10 września 2026. Zakres: analiza oficjalnego API i bieżącego kodu MCP; wyniki konta są przekazane przez autora [raportu live](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/docs/research/2026-09-10-live-coach-audit.md). Badanie dokumentacji wykonało wyłącznie publiczne GET, bez danych uwierzytelniających i bez zmian konta. Obecność endpointu lub pola w schemacie nie dowodzi obecności danych w konkretnej aktywności.

## Co już mamy

Obecny checkout udostępnia szczegóły aktywności, interwały, komentarze, streamy z pobieraniem fragmentów i eksportem, wellness, wydarzenia, ustawienia sportów, definicje metryk, custom items, krzywe mocy, statystyki wskazanego fragmentu i najlepsze wysiłki. `get_session_context` łączy szczegóły, interwały, plan, komentarze i wellness; sekcje planu i wellness trzeba zamówić. Nie są to propozycje nowych narzędzi. Źródło: [deklaracje narzędzi](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/src/intervals_mcp_server/tools/__init__.py), [kompozycja kontekstu](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/src/intervals_mcp_server/tools/session_context.py:1255), [analityka fragmentów](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/src/intervals_mcp_server/tools/analytics.py:223).

Największą wartość widzę teraz w usunięciu przeszkód interpretacyjnych i skróceniu drogi od danych do odpowiedzi coacha. Poniższe priorytety są oceną autora tego badania, a nie zaleceniem producenta API.

## P1: problemy ujawnione przez test konta

### Opcjonalne `data2` nie powinno oznaczać uszkodzonego streamu

W równoległym teście live zgłoszono siedem zgodnych głównych tablic `data`, po 15 016 próbek, przy `data2=null`, lecz MCP informował o brakujących tablicach i nierównych długościach. To trzeba rozdzielić: poprawne wyrównanie głównych tablic, dostępność opcjonalnych tablic pomocniczych oraz rzeczywista jakość osi czasu. Schemat `ActivityStream` opisuje `data`, `data2`, `valueTypeIsArray` i `allNull`, bez wymaganego `data2`. Wniosek projektowy: nullem w opcjonalnym polu nie uzasadniać `UNEQUAL_STREAM_LENGTHS`. [Aktualny OpenAPI, schema ActivityStream](https://intervals.icu/api/v1/docs)

### Brak konfiguracji krzywej po zmęczeniu nie powinien usuwać zwykłej krzywej

Test live zgłosił HTTP 422 z komunikatem `Athlete has no kj0 defined` dla `fatigue=normal,kj0,kj1`. To informacja o niedostępnej konfiguracji, a nie dowód braku mocy w treningu.

| Wariant API | Parametr |
| --- | --- |
| `GET /api/v1/activity/{id}/power-curves.json` | `types=watts&fatigue=normal,kj0,kj1` — wiele krzywych |
| `GET /api/v1/activity/{id}/power-curve.json` | pojedyncze `fatigue=kj0` lub `kj1`; dla zwykłej krzywej pominąć |

Oba warianty są udokumentowane. `SportSettings` ma `after_kj0` i `after_kj1`; `PowerCurve` ma `after_kj`. Obecny MCP wysyła listę do prawidłowego, mnogiego endpointu. [OpenAPI](https://intervals.icu/api/v1/docs), [wywołanie MCP](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/src/intervals_mcp_server/tools/power_curves.py:616)

Proponuję wynik per selektor: `normal=available`, `kj0=not_configured`, zamiast utraty całego wyniku. Odczyt ustawień może uprzedzić błąd; kontrolowane osobne GET pozwolą zachować działający wariant. Nie ustawiałbym progów zawodnikowi podczas diagnostyki. Nie należy też wyprowadzać tożsamości selektora z samej liczby `after_kj`.

Zwykła krzywa w teście zadziałała, ale pozostała `partial`, ponieważ odpowiedź nie powtórzyła selektora `fatigue`. Użyteczniej rozdzielić „punkty mocy dostępne” i „selekcja niepotwierdzona przez odpowiedź”. Brak echa parametru nie oznacza automatycznie niekompletnych punktów; nadal nie daje prawa do oznaczenia selekcji jako zweryfikowanej.

Samo `/streams` bez rozszerzenia działało w teście live. Początkowa hipoteza problemu routingu została odrzucona po uzyskaniu właściwego komunikatu HTTP 422; nie jest zgłoszeniem błędu.

## P1: ergonomia rzeczywistej analizy

### Porównanie planu z wykonaniem jako kolejny poziom istniejącego kontekstu

API kalendarza pozwala pobrać `workout_doc.steps`; `resolve=true` dodaje cele `_power`, `_hr`, `_pace` w W, bpm i m/s. Struktura obejmuje powtórzenia, rampy, kroki zagnieżdżone i zakończenie przyciskiem LAP. Jest to już obsługiwane w `get_events` i sekcji planu `get_session_context`. [Opis autora API](https://forum.intervals.icu/t/downloading-planned-workouts-from-the-api/93737), [kod kalendarza](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/src/intervals_mcp_server/tools/events.py:411)

Proponuję opcjonalne zestawienie: krok planu → interwał wykonany → cel → wynik → odstępstwo → pewność dopasowania. Zachować osobno brak planu, niejednoznaczne dopasowanie i brak pomiaru. Sam jeden wynik `compliance` nie odpowie coachowi, którą część treningu wykonano dobrze.

Nie ma tu podstaw do traktowania obecnie odczytanego planu jako niezmiennej wersji z dnia wykonania. Bieżący kod już ostrzega o tej różnicy i oddziela historyczne progi aktywności od progów zapisanych w planie. Ewentualny nowy kalkulator powinien odziedziczyć te ograniczenia. [Kontrakt kontekstu](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/src/intervals_mcp_server/tools/session_context.py:1273)

W teście niezwiązana aktywność otrzymała `PAIRED_EVENT_NULL`. Proponuję normalny stan `unpaired` oraz opcjonalne `contextual_events`: wyścig lub notatka z tego samego dnia może być istotnym kontekstem, lecz wspólna data nie dowodzi powiązania wykonania z planem. Pobranie takiego kontekstu nie powinno tworzyć lub zmieniać pary w kalendarzu.

### Zwięzła odpowiedź „jakie dane mam i czego brakuje?”

Proponuję sekcję jakości zawierającą liczbę poprawnych próbek, pokrycie czasu, luki, zgodność osi, źródło mocy oraz dostępność feedbacku i planu. Potrzebne odczyty już istnieją. Podsumowanie powinno wskazywać dokładny dalszy odczyt, zamiast zmuszać coacha do przeglądania tysięcy punktów.

Custom streams mogą pochodzić z pól FIT lub obliczeń JavaScript, są konfigurowane na poziomie zawodnika i mogą zależeć od innych streamów. Sama nazwa metryki nie wystarcza do interpretacji. [Dokumentacja autora](https://forum.intervals.icu/t/custom-activity-streams/44237)

Wykorzystałbym istniejące `get_custom_items` i `get_custom_item_by_id` do powiązania metryki z deklaracją jednostki, źródłem i definicją. Brak deklaracji ma pozostać jawny. Nie należy utożsamiać wentylacji, szacowanego VO₂max i pomiaru VO₂ ani SS i TSS na podstawie podobnych nazw. Definicje MCP już rozdzielają część tych pojęć. [Definicje metryk](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/src/intervals_mcp_server/tools/metrics.py), [metadane custom items](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/src/intervals_mcp_server/tools/custom_items.py:140)

Praktyczny problem z testu: lista compact zawierała 61 rekordów, lecz pomijała `content.code` i `fit_record_field`, potrzebne do znalezienia właściwych identyfikatorów. Próby `TymeVentilation` i `TymeBreathRate` nie dały streamów, podczas gdy natywny `respiration` był dostępny. Proponuję zachować techniczny kod, pole FIT i jednostkę w compact oraz łączyć definicje z faktycznie zwróconymi streamami dla jednej aktywności. Nie rozstrzygać braku czujnika na podstawie nieskutecznego żądania odgadniętej nazwy.

Dla `respiration`, `temp`, `torque` i `hrv` test zgłosił `unit=null`. To osobna luka słownika MCP do weryfikacji względem źródła: nazwa i wartość nie wystarczają, zwłaszcza przy różnych formach HRV. Rozszerzenie słownika jednostek jest mniejszym i bardziej przydatnym zadaniem niż dodanie kolejnego ogólnego endpointu.

## Najbardziej użyteczne nowe odczyty

Poniższe endpointy są obecne w publicznym OpenAPI pobranym podczas badania; ich przydatność w kolumnie obok jest oceną projektową. Główny audyt live dodatkowo sprawdził na koncie `power-vs-hr.json`, `weather-summary` i `power-histogram` — wyniki znajdują się pod tabelą. Pozostałych propozycji z tabeli nie sprawdzono na koncie w tym audycie. [Specyfikacja API](https://intervals.icu/api/v1/docs)

| Priorytet | Kandydat i endpoint GET | Korzyść dla coacha i ograniczenie |
| --- | --- | --- |
| P1 | `get_activity_power_hr`: `/api/v1/activity/{id}/power-vs-hr.json` | Natywna analiza zależności mocy i HR bez samodzielnego odtwarzania algorytmu; wymaga obu sygnałów. |
| P2 | `get_athlete_power_hr`: `/api/v1/athlete/{id}/power-hr-curve?start=...&end=...&type=Ride` | Porównanie z historią po filtrach aktywności; rezultat wymaga oceny ilości i porównywalności danych. |
| P2 | `get_activity_weather`: `/api/v1/activity/{id}/weather-summary?start_index=...&end_index=...` | Kontekst warunków dla jazdy outdoor lub fragmentu. Nie zastępuje informacji o chłodzeniu na trenażerze. |
| P2 | `get_fitness_model_events`: `/api/v1/athlete/{id}/fitness-model-events` | Wyjaśnienie zmian modelu CTL/ATL razem z już odczytywanym wellness; przydatne podczas audytu ciągłości historii. |
| P2 | `get_activity_histograms`: `/api/v1/activity/{id}/power-histogram?bucketSize=25`, `/hr-histogram?bucketSize=5`, `/pace-histogram` | Rozkład intensywności przy małym transferze. Część pytań pokrywają już czasy w strefach. |
| P3 | Krzywe tempa: `/api/v1/athlete/{id}/activity-pace-curves.json?oldest=...&newest=...&type=Run&distances=1000,5000&gap=true` | Uzupełnienie, jeśli analiza biegu wymaga własnej historii tempa; dla coacha kolarskiego niższy priorytet. |

### Potwierdzenie trzech propozycji w głównym audycie live

Poniższe trzy bezpośrednie, uwierzytelnione GET wykonał autor głównego audytu, osobno od 77 wywołań MCP. Agent prowadzący niniejsze badanie dokumentacji nie wykonywał tych żądań; uzupełnienie korzysta z przekazanych wyników i lokalnych dowodów. Wszystkie próbki dotyczą aktywności `i183591082` z 5 września. [Rejestr prób API](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/api-opportunity-probes.json)

| Odczyt | Potwierdzony wynik | Dowód |
| --- | --- | --- |
| `power-vs-hr.json` | HTTP 200, 18 588 bajtów; 227 minutowych elementów `series`, 3 `curves`, `bucketSize=60`, `hrLag=30`, `warmup=1200`, `cooldown=600`, `decoupling=6.482107`. | [Odpowiedź API](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/power_vs_hr-api.json) |
| `weather-summary?start_index=350&end_index=650` | HTTP 200, 1504 bajty; `whole_activity=false`, `start_secs=350`, `end_secs=650`, `moving_time=300`. API zwróciło podsumowanie wybranego fragmentu. | [Odpowiedź API](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/weather_5min-api.json) |
| `power-histogram?bucketSize=25` | HTTP 200, 648 bajtów; 20 przedziałów. | [Odpowiedź API](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/.runtime/live-coach-20260910/power_histogram-api.json) |

Wzmacnia to rekomendację natywnego power-vs-HR: dla analizowanego treningu istnieje konkretny, dostępny wynik, a histogram dostarcza małą odpowiedź. Potwierdzenie dotyczy tych parametrów i tej aktywności; nie stanowi testu jeszcze nieistniejących narzędzi MCP ani gwarancji dostępności danych dla wszystkich treningów. Nie potwierdza też `hr-histogram` i `pace-histogram` przez analogię do histogramu mocy.

W szczególności power-vs-HR ma sens jako natywny odczyt: autor opisuje minutowe fragmenty z korektą opóźnienia HR, a krzywą historyczną jako agregację uwzględniającą ilość danych. Nie traktowałbym jej jako testu progowego ani automatycznego wyroku o poprawie formy. [Wyjaśnienie algorytmu przez autora](https://forum.intervals.icu/t/new-compare-page-with-power-vs-hr-chart/1730/67), [ilość danych w koszykach](https://forum.intervals.icu/t/power-vs-heart-rate-data-source/37088)

## Siła: potrzebne dane i realistyczna ścieżka

`kg_lifted`, czas, HR, RPE i opis pomagają zobaczyć sesję siłową w tygodniu. Dla oceny progresji ćwiczenia potrzebuję jednak nazw ćwiczeń, serii, powtórzeń, ciężaru, przerw oraz feedbacku dotyczącego zapasu i wykonania. W przejrzanym publicznym OpenAPI nie znalazłem osobnego, opisanego modelu pełnego dziennika ćwiczeń/serii. To ograniczenie przejrzanej dokumentacji, nie dowód, że żaden taki rekord nigdy nie występuje w pliku lub polu custom. [OpenAPI](https://intervals.icu/api/v1/docs)

Kandydat P2 to pobranie oryginalnego pliku przez `GET /api/v1/activity/{id}/file` jako artefaktu i opcjonalny odczyt danych siłowych, jeżeli rzeczywiście znajdują się w FIT. Osobny `/fit-file` tworzy plik wygenerowany przez Intervals.icu; do badania informacji zachowanych przez urządzenie preferuję oryginał. Obecny `export_activity_data` zapisuje streamy i interwały, a nie oryginalny FIT. [Oficjalny cookbook](https://forum.intervals.icu/t/intervals-icu-api-integration-cookbook/80090), [obecny eksport](C:/Users/BartoszBerezowski/Documents/intervals-mcp-server/src/intervals_mcp_server/tools/activities.py:64)

Garmin opisuje, że zawartość Activity FIT zależy od urządzenia, sportu i użytych funkcji; plik może też zawierać kroki wykonanego treningu i ich indeksy w LAP. Najpierw warto sprawdzić przykładowy plik, dopiero potem projektować ekstrakcję. [Dekodowanie aktywności](https://developer.garmin.com/fit/cookbook/decoding-activity-files/), [struktura Activity FIT](https://developer.garmin.com/fit/file-types/activity/)

Nie zakładać, że oryginalny plik zawiera poprawki wprowadzone później w Garmin Connect: autor Intervals.icu wyjaśnia, że reprocess używa pliku już otrzymanego, bez ponownego pobierania takich zmian. [Wyjaśnienie autora dotyczące ciężaru](https://forum.intervals.icu/t/weight-lifted-field-doesnt-update-when-reprocess-original-file/53390)

## Granice wnioskowania i kolejność dalszej pracy

1. Najpierw naprawić fałszywe ostrzeżenie wyrównania oraz obsługę częściowo niedostępnych krzywych i potwierdzić oba scenariusze live.
2. Następnie poprawić krótkie zestawienie wykonania, braków danych i kontekstu tygodnia za pomocą obecnych narzędzi.
3. Dodać natywne power-vs-HR, jeżeli analiza powtarzalnych jazd rzeczywiście z niego skorzysta.
4. Sprawdzić jeden oryginalny FIT sesji siłowej przed obietnicą automatycznego dziennika serii.

Feedback, ból, jakość snu czy odżywianie mogą być obsługiwane przez API, a mimo to nie być wprowadzone na koncie. W takim przypadku potrzebna jest rozmowa lub poprawienie dopływu danych. Sam nowy endpoint nie wypełni braków. Puste wyniki nie dowodzą też kompletności historii; autor dokumentuje ograniczenia dostępu do aktywności pochodzących ze Stravy. [API i integracja](https://intervals.icu/api/v1/docs), [cookbook autora](https://forum.intervals.icu/t/intervals-icu-api-integration-cookbook/80090)
