# Test live zapisu planowanej jednostki

**Aktualizacja po teście:** naprawiono porównywanie zagnieżdżonych celów i odczyt trwającego urlopu. [Raport poprawki i walidacji](2026-09-10-calendar-bug-fixes.md). Poprawiony weryfikator sprawdzono na zachowanym odczycie live i lokalnie zmienionej kopii; nie wykonywano kolejnej mutacji treningu. Poniższy zapis zachowuje wyniki pierwotnego testu sprzed poprawki.

Test wykonany 10 września 2026 na koncie Intervals.icu użytkownika, zgodnie z jego prośbą. Narzędzia wywołano przez rzeczywiste MCP `ClientSession` po STDIO, uruchamiając bieżący checkout w trybie `coach`. Dane uwierzytelniające pochodziły z konfiguracji serwera; log nie zawiera nagłówków autoryzacji. Zachowano wspólny katalog operacji `.runtime/operations`.

## Wynik

**Zapis, niezależny odczyt, ponowne wywołanie tej samej operacji i usunięcie wpisu testowego zadziałały.** Test ujawnił jednocześnie lukę w automatycznym porównywaniu zagnieżdżonych celów treningu; opis poniżej. Kod serwera nie był zmieniany w ramach tego testu.

Utworzono jedną jednostkę `WORKOUT / Ride` na **11 września 2026**, pod nazwą `TEST MCP - zapis jednostki 20 min`, z opisem jednoznacznie wskazującym test techniczny i zakaz realizacji. Narzędzie przyjmuje lokalną datę; zapisany `start_date_local` wynosił `2026-09-11T00:00:00`.

| Krok | Czas | Cel |
|---|---:|---:|
| 1 | 5 min | 50% FTP |
| 2 | 10 min | 65% FTP |
| 3 | 5 min | 45% FTP |

`apply_workout_changes` zwróciło `confirmed` i **event ID `135238673`**. Osobny proces MCP ponownie pobrał ten konkretny wpis przez `get_event_by_id`; sprawdzono dokładny opis, datę, sport, kategorię, `external_id`, wszystkie wartości i jednostki celów mocy, długości kroków oraz łączny czas **1200 s**. Intervals sam obliczył obciążenie **11**; czas i obciążenie nie były ręcznie przesyłanymi polami pochodnymi.

## Przebieg i dowody

1. `get_capabilities` potwierdziło dostępność bezpiecznego zapisu w trybie `coach`; zapytanie `get_events` ograniczone do 11 września zwróciło pustą listę. Późniejszy [test kontekstu kalendarza](2026-09-10-live-calendar-context-test.md) wykazał, że trwał wtedy urlop rozpoczęty 7 września, pominięty przez wąski zakres API. Pusta lista nie oznaczała braku trwających wydarzeń.
2. Jedno `apply_workout_changes(create)` wykonało GET dnia, pojedynczy POST z `upsertOnUid=false` oraz niezależny GET ID otrzymanego z POST.
3. Po restarcie procesu `get_event_by_id` i `get_write_status(reconcile=true)` potwierdziły odczyt. Lista kalendarza zawierała dokładnie jeden wpis z testowym `external_id`.
4. Ponowne wywołanie identycznego `decision_uid`, `operation_uid`, `session_uid` i payloadu zwróciło ten sam wynik z dziennika operacji. Nie wysłano kolejnego POST.
5. Usunięto wyłącznie testowy ID, podając ten sam `session_uid`, nowy identyfikator operacji i fingerprint pełnego eventu z niezależnego odczytu. Narzędzie ponownie odczytało wpis i sprawdziło fingerprint przed DELETE.
6. Po usunięciu GET ID zwrócił 404, zapytanie o ten sam dzień ponownie zwróciło pustą listę, a `get_write_status` operacji delete potwierdziło brak wpisu także po kolejnym restarcie procesu. Usunięcie dotyczyło wyłącznie testowego ID; nie zmieniono trwającego urlopu.

Łącznie: **11 wywołań MCP, 13 GET, 1 POST i 1 DELETE**. Odpowiedzi miały HTTP 200 lub oczekiwane 404 podczas kontroli usunięcia. Wszystkie odpowiedzi MCP przeszły walidację reklamowanego schematu, a tekst JSON był zgodny ze `structuredContent`. Lokalna osłona HTTP dopuszczała tylko kalendarz tego konta, jeden POST o dokładnie przygotowanej treści oraz jeden DELETE konkretnego ID otrzymanego z utworzenia. Próby mutacji zapisywano przed wysłaniem, aby wykluczyć ponowienie po niepewnej odpowiedzi.

Prywatne dowody znajdują się w `.runtime/calendar-write-live-20260910/`: `case.json`, `responses/`, `http.jsonl`, `verification.json`, `verification-gap.json` oraz plany poszczególnych faz. Dziennik operacji zachowano poza katalogiem testowego raportu, w normalnym współdzielonym katalogu serwera.

## Luka w automatycznej weryfikacji

W [writes.py](../../src/intervals_mcp_server/tools/writes.py) funkcja `_step_differences` stosuje tę samą listę dozwolonych nazw pól rekurencyjnie do całego kroku i do obiektów `power`, `hr`, `pace` itp. Lista zawiera `power`, ale nie zawiera jego zagnieżdżonych pól `value`, `units`, `start`, `end` i `target`. W konsekwencji różne wartości lub jednostki celu mogą nie zostać wykryte.

Zapisany odczyt live skopiowano wyłącznie w pamięci procesu lokalnego i zmieniono cel pierwszego kroku z `50 %ftp` na `999 w`, pozostawiając pozostałe dane bez zmian. `_verification` zwróciło nadal `confirmed` oraz pustą listę różnic. **Nie wysyłano tej zmiany do API.** Reprodukcja jest zapisana w `verification-gap.json`.

W tym konkretnym teście cele zapisane na koncie były poprawne — potwierdziło to dodatkowe dokładne porównanie całych `workout_doc.steps` z intencją, niezależne od wadliwej funkcji. Automatyczny status `confirmed` samodzielnie nie daje jednak pełnej gwarancji zgodności celów treningu.

Zalecana poprawka: osobne porównanie pól kroku i obiektu celu, wraz z testami zmiany liczby, jednostki, zakresu i celu strefowego dla mocy, tętna i tempa. Warto również wymieniać faktycznie sprawdzone cele i czas w `checked_fields`.

Zakres dowodu live obejmuje pojedynczy prosty zapis strukturalny, powtórzenie operacji po restarcie i usunięcie. Nie testowano aktualizacji istniejącej jednostki, konfliktów z równoległym autorem, grup powtórzeń ani treningu siłowego. Nie zmieniano globalnych deklaracji `live_verified` na podstawie tego jednego przypadku.
