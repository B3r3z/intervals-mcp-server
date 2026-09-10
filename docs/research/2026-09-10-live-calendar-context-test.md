# Odczyt wyścigów i urlopu — test live 10 września 2026

**Aktualizacja po teście:** błąd pomijania rozpoczętego wcześniej urlopu został naprawiony i ponownie sprawdzony live. [Raport poprawki i walidacji](2026-09-10-calendar-bug-fixes.md). Poniższy zapis zachowuje wyniki pierwotnego testu sprzed poprawki.

Test rzeczywistych narzędzi MCP `get_events` i `get_event_by_id` przez STDIO, w trybie readonly. Wykonano 6 wywołań MCP i 6 uwierzytelnionych GET, wszystkie HTTP 200. Schematy odpowiedzi i zgodność tekstu ze structuredContent przeszły. Bez zapisów na koncie i bez zmian kodu serwera.

## Widoczny urlop

- ID: `128691374`.
- Nazwa: `URLOP`.
- Kategoria: `HOLIDAY`.
- Opis: `Roztrenowanie po sezonie :D`.
- Początek: `2026-09-07T00:00:00`.
- Koniec: `2026-09-21T00:00:00` — obejmuje bieżący tydzień 7–13 września i następny 14–20 września.
- `training_availability=UNAVAILABLE`.
- `for_week=false`: jest to wielodniowy wpis urlopowy, a nie wyłącznie nazwa tygodnia.

To jawny kontekst ograniczający dostępność treningową. Brak zaplanowanych treningów nie oznacza w tym okresie wolnego miejsca na nowe jednostki.

## Przyszłe starty zapisane w kalendarzu

Przeszukano zakres od 1 sierpnia 2026 do 11 września 2027, z prawą granicą wyłączną. Wśród zwróconych rekordów są następujące przyszłe starty; nazwy i daty pochodzą z kalendarza użytkownika, nie z publicznych terminarzy organizatorów.

| Data | Nazwa w kalendarzu | Kategoria | Sport | Dystans źródłowy |
|---|---|---|---|---|
| 2026-10-03 | POZNAN FIVE | RACE_B | Run | null |
| 2026-10-18 | Wizz Air Romę Half Marathon 2026 | RACE_B | Run | null |
| 2027-04-10 | Mnich 2027 | RACE_B | Ride | null |
| 2027-09-04 | Tatra Race Road 2027 | RACE_A | Ride | 82000 m |

Widać także wcześniejszy wpis `Tatra Road Race` z 5 września 2026, kategorii `RACE_A`, z zapisanym dystansem 90000 m. Tej wartości planu nie należy utożsamiać z dystansem faktycznie nagranej aktywności.

## Potwierdzona luka przy wydarzeniach wielodniowych

| Zakres get_events, koniec wyłączny | Wynik |
|---|---|
| 2026-09-07 → 2026-09-14 | zwrócony URLOP |
| 2026-09-10 → 2026-09-14 | pusta lista, mimo trwającego urlopu |
| 2026-09-14 → 2026-09-21 | pusta lista, mimo trwającego urlopu |

W obu ostatnich przypadkach pustą listę zwróciło już API Intervals.icu. [get_events](../../src/intervals_mcp_server/tools/events.py) nie usuwa kategorii HOLIDAY ani nie filtruje lokalnie tych rekordów. Przekazuje daty oldest/newest i nie wykonuje dodatkowego wyszukiwania wydarzeń rozpoczętych wcześniej, które nadal obejmują analizowany okres.

Wniosek dla planowania: trzeba uwzględniać początek i koniec wydarzenia oraz dostępność treningową. Sam odczyt od dzisiaj albo tylko następnego tygodnia może dać niepełny kontekst. Szerszy zakres obejmujący 7 września ujawnił ten konkretny urlop; arbitralny stały lookback nie gwarantuje wykrycia wszystkich możliwych długich wydarzeń. Własny odczyt kontekstu powinien jawnie rozwiązywać nakładanie zakresów lub raportować granice przeszukania.

Prywatny dowód lokalny: `.runtime/calendar-context-live-20260910/verification.json`, odpowiedzi w `responses/` i źródłowy log `http.jsonl`. Wcześniejszy raport testu zapisu został doprecyzowany: pusta odpowiedź na zapytanie o 11 września nie oznaczała braku urlopu.
