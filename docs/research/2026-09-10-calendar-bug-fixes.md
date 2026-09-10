# Naprawa weryfikacji celów treningu i odczytu trwających wydarzeń

Oba błędy z testów live zostały naprawione w lokalnym kodzie serwera. Końcowa walidacja: **650 passed, 1 skipped**, Ruff bez błędów, mypy bez błędów w 87 plikach. Dodano 71 przypadków regresyjnych: 40 dla weryfikacji celów i 31 dla nakładania się wydarzeń. Niezależny przegląd części kalendarzowej zakończono bez otwartych uwag.

## Weryfikacja zapisanego treningu

Wcześniej porównywanie `power`, `hr`, `pace` i `cadence` używało listy pól kroku treningowego także wewnątrz obiektu celu. Pomijało przez to wartości i jednostki. Teraz obiekt celu ma osobne porównanie `value`, `start`, `end`, `units` i `target`, również w zagnieżdżonych powtórzeniach. Zmiana wartości, jednostki, zakresu lub sposobu uśredniania zwraca `mismatch` ze ścieżką konkretnego pola. Liczby `50` i `50.0` pozostają równoważne; wartości logiczne nie zastępują liczb. Dodatkowe metadane wyliczone przez API nie są traktowane jako zalecona intensywność. `checked_fields` wskazuje sprawdzone kroki i czas całkowity, jeżeli ten etap porównania został wykonany.

Ponownie uruchomiono aktualny weryfikator na zachowanym odczycie rzeczywistego wpisu testowego `135238673`: oryginał daje `confirmed`. Kopia z celem pierwszego kroku zmienionym z `50 %ftp` na `999 w` daje teraz `mismatch` dla `workout_doc.steps[0].power.units` i `workout_doc.steps[0].power.value`. Była to lokalna reprodukcja na zapisanym odczycie, bez nowego zapisu do API i bez modyfikowania dziennika. Wpis testowy usunięto w ramach wcześniejszego testu. Testy regresyjne obejmują też trwały wynik operacji, powtórne wywołanie bez ponownej mutacji i ponowny odczyt podczas uzgadniania stanu.

Kod: [writes.py](../../src/intervals_mcp_server/tools/writes.py). Testy: [test_workout_target_verification.py](../../tests/test_workout_target_verification.py). Dowód lokalny: `.runtime/two-bugs-fix-20260910/verification-gap-fixed.json`.

## Trwające wydarzenia w kontekście kalendarza

`get_events` domyślnie zwraca wydarzenia nakładające się na żądane okno, także rozpoczęte wcześniej. Dotyczy to wszystkich kategorii, w tym `HOLIDAY`, `NOTE`, wyścigów i treningów. Parametr `include_overlapping=false` zachowuje wybór API według daty początku; jest używany przy rozwiązywaniu wcześniej zidentyfikowanego treningu po jego ID i dokładnym dniu rozpoczęcia. Sekcja `contextual_events` w `get_session_context` dziedziczy domyślne nakładanie dat i metadane wyboru.

Publiczne [OpenAPI Intervals.icu](https://intervals.icu/api/v1/docs), odczytane 10 września 2026, nie udostępnia parametru nakładania wydarzeń. Pominięte `oldest` oznacza dzisiejszy dzień w strefie zawodnika; pominięte `limit` oznacza wszystkie zwrócone wydarzenia. MCP wysyła więc jawne `oldest=0001-01-01` — dolną granicę obsługiwanego typu daty — oraz żądane `newest`, bez limitu i bez filtra kategorii, a następnie sprawdza nakładanie lokalnie. API zaakceptowało tę granicę w osobnym odczycie próbnym oraz we właściwych testach MCP. Nie stosujemy arbitralnego okna 30 lub 365 dni, które mogłoby ponownie ukryć dłuższy wpis.

Koniec wydarzenia jest wyłączny, zgodnie z [wyjaśnieniem autora API](https://forum.intervals.icu/t/api-access-to-intervals-icu/609/334); `newest` API jest natomiast datą włącznie, zgodnie z [wyjaśnieniem zakresu dat](https://forum.intervals.icu/t/api-access-to-intervals-icu/609/462). Wydarzenie kończące się 21 września o północy nie obejmuje 21 września. Zdarzenie o zerowej długości jest wybierane według początku. Brakujące lub niepoprawne granice uniemożliwiające ustalenie nakładania zachowują kandydata jako nierozstrzygniętego, z `partial` i `EVENT_OVERLAP_UNRESOLVED`. Nieudokumentowane pole `date` nie zastępuje `start_date_local`. Wybrane rekordy zachowują źródłowe pola, zera, wartości null i duplikaty.

Metadane ujawniają żądane okno, `query.upstream_oldest`, liczbę kandydatów, dopasowań, odrzuceń i nierozstrzygnięte rekordy. Kompletność źródła pozostaje niepotwierdzona. Kosztem poprawki jest pobranie wcześniejszych wpisów: na tym koncie odczyty września pobierały 132 kandydatów, a dla bieżącego i przyszłego tygodnia zwracały po jednym. Konta z długą historią mogą wymagać większego transferu; filtr nie ukrywa tego kosztu ani nie ucina historii przed sprawdzeniem dat końca.

Kod: [calendar_events.py](../../src/intervals_mcp_server/calendar_events.py), [events.py](../../src/intervals_mcp_server/tools/events.py), [session_context.py](../../src/intervals_mcp_server/tools/session_context.py). Testy: [test_event_overlap_contract.py](../../tests/test_event_overlap_contract.py).

## Wyniki ponownego testu live

Wykonano **10 wywołań MCP i 11 GET, wszystkie HTTP 200**, przez STDIO uruchamiające aktualny checkout. Osłona HTTP dopuszczała wyłącznie odczyty z Intervals.icu. Wszystkie odpowiedzi przeszły reklamowany schemat MCP; tekst JSON był zgodny ze `structuredContent`. Dodatkowy bezpośredni GET sprawdzający minimalną datę nie jest uwzględniony w tych licznikach. Nie wykonano mutacji na koncie.

| Zapytanie, koniec zakresu wyłączny | Potwierdzony wynik |
| --- | --- |
| 10–14 września | `URLOP`, ID `128691374` |
| 14–21 września | Ten sam `URLOP` |
| 21–22 września | Brak zakończonego urlopu |
| 10–14 września, `include_overlapping=false` | Pusta lista, odtwarzająca wcześniejsze zachowanie API |
| 1 października–1 listopada | Dwa wpisy o wyścigach, ID `129552063` i `129552188` |
| Kontekst aktywności z 3 września, kolejne 14 dni | Treningi, wyścig i urlop wraz z metadanymi nakładania oraz parametrem kontynuacji |

Urlop odczytano także niezależnie po ID i porównano cały obiekt z wynikiem listy: początek `2026-09-07T00:00:00`, koniec `2026-09-21T00:00:00`, `training_availability=UNAVAILABLE`. To okres **7–20 września**. Na danych live nie było nierozstrzygniętych granic; takie przypadki sprawdzają testy syntetyczne.

Prywatne dowody: `.runtime/two-bugs-live-20260910/verification.json`, `responses/`, `http.jsonl`, `discovery.json`; osobna próba daty: `.runtime/two-bugs-fix-20260910/min-date-probe.json`. Raport weryfikacji zawiera skróty SHA-256 sprawdzanych plików źródłowych. Test dotyczy lokalnego checkoutu i wskazanych scenariuszy; nie zmienia ogólnego `live_verified=false` w katalogu możliwości. Działający wcześniej proces serwera musi zostać uruchomiony ponownie, aby załadować nowy kod i schemat parametru.

Polecenia kontroli końcowej: `uv --cache-dir .uv-cache run --offline --no-sync pytest --basetemp=.runtime/pytest-two-bugs-reviewed -q -o addopts=''`, `uv --cache-dir .uv-cache run --offline --no-sync ruff check .`, `uv --cache-dir .uv-cache run --offline --no-sync mypy src tests`.
