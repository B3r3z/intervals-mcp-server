# Tymewear: znaczenie VT, VE i BR w narzędziach MCP

Sprawdzenie dokumentacji: **10 września 2026**. Zakres: publiczna dokumentacja producenta i wypowiedzi autora importera Intervals.icu. Użytkownik potwierdził, że omawiane streamy VT pochodzą z Tymewear. To potwierdzenie dotyczy jego danych; sama nazwa natywnego streamu nie identyfikuje producenta w każdej aktywności.

## Ustalenie do zastosowania w narzędziach

**VT oznacza tutaj tidal volume, czyli objętość pojedynczego oddechu. Wartości Tymewear należy zachować w skali źródłowej, bez automatycznej konwersji na litry.** Autor Intervals.icu 26 sierpnia 2025 wycofał przeliczanie VT przez 100 i ogłosił powrót do surowych wartości Tymewear z jednostką `i.u.`. Jego wyjaśnienie mówi, że relacja do litrów zależy od zawodnika. Jest to bezpośrednie źródło o zachowaniu importera; przytoczona tam korespondencja nie jest osobną publiczną specyfikacją producenta. [Intervals.icu, posty 10–11](https://forum.intervals.icu/t/tymewear-an-interactive-activity-chart/90911/10)

| Sygnał | Znaczenie według producenta | Interpretacja jednostki w MCP |
|---|---|---|
| BR / breathing rate | Liczba oddechów na minutę | `breaths/min`; źródłową deklarację custom streamu zachować osobno. |
| VT / tidal volume | Objętość przypadająca na oddech | Dla potwierdzonego źródła Tymewear: źródłowe jednostki objętości, w opisie importera `i.u.`. Bez założenia `L/br`, `mL/br` albo `cL/br`. |
| VE / minute ventilation | Objętość wentylacji na minutę | Producent używa etykiety `vol/min`; nie utożsamiać jej automatycznie z `L/min`. |

Definicje BR, VT i VE podaje [FAQ Tymewear](https://www.tymewear.com/pages/faq). Etykieta wyświetlanej VE `vol/min` występuje na stronie [Why Tymewear](https://www.tymewear.com/pages/why-tymewear). Zastrzeżenie dotyczące litrów dla VT pochodzi z powyższego opisu importera.

## Pola eksportu i nazwy w Intervals.icu

Producent dokumentuje eksport FIT oraz CSV z dashboardu. Dla integracji FIT wymienia trzy pola: `tyme_breath_rate`, `tyme_tidal_volume` i `tyme_minute_volume`. Nie podaje w tym przewodniku tabeli kodowania, jednostek FIT, wartości `scale`/`offset` ani współczynnika kalibracji do litrów. [Tymewear Software](https://www.tymewear.com/blogs/connectivity/software)

| Pole FIT Tymewear | Natywny stream Intervals.icu | Znaczenie |
|---|---|---|
| `tyme_breath_rate` | `respiration` | BR |
| `tyme_tidal_volume` | `tidal_volume` | VT, objętość na oddech |
| `tyme_minute_volume` | `tidal_volume_min` | VE, wentylacja minutowa |

Mapowanie BR i VE opisał autor Intervals.icu w [poście 2 z 18 lutego 2025](https://forum.intervals.icu/t/tymewear-an-interactive-activity-chart/90911/2), a import pola VT w [poście 13 z 16 kwietnia 2023](https://forum.intervals.icu/t/importing-fit-with-tymewear-data-fields/26456/13). Nazwa `tidal_volume_min` jest identyfikatorem wentylacji minutowej, nie minimum objętości pojedynczego oddechu.

W starszych postach można znaleźć etykiety w litrach i propozycję dzielenia przez 100. Nie należy kopiować tych instrukcji bez późniejszej korekty: autor jawnie wycofał tę zmianę. [Intervals.icu, historia korekty](https://forum.intervals.icu/t/tymewear-an-interactive-activity-chart/90911/11)

W odczycie sesji z 3 września 2026 zachowanym lokalnie w `.runtime/live-session-20260903/` próbka z czasu 600 s zawiera `tidal_volume=186.0`, `TymeBreathRate=40.8` i `TymeVentilation=76.0`. Ten przykład pochodzi z wcześniejszego testu live w tej rozmowie, nie z publikacji producenta. Podobieństwo `186 / 100 * 40.8` do 76 nie ustala fizycznej kalibracji. W ramach tej kwerendy nie pobierano oryginalnego FIT ani nie weryfikowano jego deskryptorów pól.

## VT a progi VT1 i VT2

Nie należy tworzyć aliasu, który utożsamia próbkę `tidal_volume` z progiem VT1 lub VT2. FAQ definiuje VT jako wielkość oddechu, natomiast osobny przewodnik producenta opisuje VT1 i VT2 jako pierwszy i drugi próg wentylacyjny. Są to różne pojęcia i różne rodzaje danych. [FAQ Tymewear](https://www.tymewear.com/pages/faq), [Ventilatory Thresholds](https://www.tymewear.com/pages/ventilatory-thresholds)

Na stronie integracji Software widnieje niejednoznaczne rozwinięcie skrótu VT jako „Ventilatory Threshold”. Jest to niespójne z opisem sygnałów w FAQ i nazwą pola `tyme_tidal_volume`; opis MCP powinien korzystać z jednoznacznej nazwy **tidal volume**, a niespójność dokumentacji pozostawić odnotowaną. [Tymewear Software](https://www.tymewear.com/blogs/connectivity/software)

## Konsekwencje dla analizy trenerskiej

Producent przedstawia zależność fizjologiczną `VE = BR × VT`. Nie jest to specyfikacja arytmetyki dla dowolnych surowych liczb z eksportu: zgodność skali, zakresu uśredniania i czasu należy ustalić przed takim porównaniem. Pierwsze zdanie pochodzi z [How to use breathing in training](https://www.tymewear.com/pages/how-to-use-breathing-in-training); wymaganie zgodnych skal jest wnioskiem implementacyjnym z nieudokumentowanego kodowania eksportu i historii importera.

Wewnętrzna walidacja producenta z 30 kwietnia 2026 opisuje pomiar ruchów oddechowych przez VitalPro z próbkowaniem sensora 25 Hz, odrzucanie części oddechów w obliczaniu BR i średnią z trzech oddechów dla VE. Raportuje błąd BR i korelację VE z Cosmed K5. Nie publikuje współczynnika kalibracji `tyme_tidal_volume` do litrów. **Wniosek dla MCP:** próbki API są oryginalnymi wartościami otrzymanymi z API, ale nie muszą być nieprzetworzonym sygnałem sensora. [Tymewear Internal Validation Study](https://www.tymewear.com/blogs/validation-studies/tymewear-internal-validation-study-of-breathing-metrics)

Producent zaleca stałą pozycję czujnika i to samo zapięcie paska, aby zachować napięcie. Zaleca także takie ułożenie względem szelek kolarskich, żeby nie ograniczały pracy czujnika i nie zmieniały odczytów wentylacji. **Wniosek trenerski:** przy porównywaniu VT/VE między sesjami warto znać dopasowanie paska i pozycję czujnika; kompletne próbki same nie potwierdzają porównywalnych warunków. [Breathing Sensor Help](https://www.tymewear.com/blogs/frequently-asked-questions/breathing-sensor)

## Zalecany kontrakt opisów

Poniższe punkty są decyzjami projektowymi opartymi na ustaleniach powyżej:

- Opis BR/VT/VE i pola FIT umieścić w katalogu metryk oraz dołączyć wskazówkę interpretacyjną do odczytów streamów i statystyk interwałów.
- Rozróżniać źródłową deklarację `unit`/`units` od opisu udokumentowanej skali producenta. Zachować deklaracje custom fields, nawet jeżeli zawierają `L/br` lub `L/min`; sam zapis takiej etykiety nie potwierdza kalibracji.
- Zachować próbki, zera, wartości `null` i precyzję odpowiedzi API. Nie dzielić VT przez 100, nie obliczać litrów i nie „naprawiać” VE na podstawie iloczynu surowych streamów.
- Informację o Tymewear przypisywać warunkowo na podstawie potwierdzenia źródła, metadanych importu lub rozpoznanego pola FIT. Natywne `respiration` nie stanowi samodzielnego dowodu pochodzenia z Tymewear.
- Nie wyprowadzać progów VT1/VT2, VO2, VCO2 ani RER z samej nazwy lub obecności tych trzech streamów. Oddzielna analiza wymaga odpowiedniego protokołu i danych.

Pozostają niewyjaśnione: pełny publiczny kontrakt skali i kodowania FIT zależny od wersji oprogramowania; kalibracja objętości do litrów dla konkretnego zawodnika; dokładny etap wygładzania każdej ścieżki eksportu. Opisy narzędzi powinny ujawniać te granice, zamiast zastępować je przypuszczeniem.

## Wdrożenie i sprawdzenie

Wdrożono lokalnie 10 września 2026:

- `get_metric_definitions` opisuje VT, VE i BR, natywne pola, średnie interwałów, pola FIT oraz aliasy custom. Katalog zawiera 40 definicji; nie rozpoznaje VT1/VT2 jako aliasów objętości oddechu.
- `get_activity_streams`, `get_activity_interval_stats` i `get_activity_data_quality` dołączają warunkową dokumentację w `provenance.respiratory_interpretation`. Dokumentacja pozostaje poza danymi upstream; jawnie zaznacza brak automatycznej weryfikacji producenta i brak konwersji.
- Uzupełniono opisy odkrywane przez MCP również dla `get_activity_details`, `get_activity_intervals` i `export_activity_data`, a także README. Opisy nie zmieniają konfiguracji konta ani deklaracji jednostek custom fields.

Dowód implementacyjny: [wspólne definicje](../../src/intervals_mcp_server/respiratory.py), [testy kontraktu](../../tests/test_respiratory_contract.py). Dziesięć nowych przypadków sprawdza zachowanie wartości 186, zer, null, data2, deklarowanych jednostek, nieznanych pól i średnich interwałów oraz warunkowość interpretacji. Pełny pytest przeszedł: **579 zaliczonych, 1 pominięty**. Ruff i mypy przeszły; po końcowej korekcie konstrukcji metadanych ponownie przeszły 23 przypadki streamów i protokołu. Pomiar rozmiaru odpowiedzi syntetycznej uwzględnia teraz dokumentację istniejącego w fixture streamu `TymeBreathRate`; liczba wywołań i żądań HTTP nie wzrosła.

Końcowy test świeżego procesu MCP przez STDIO: **5 wywołań narzędzi, 5 uwierzytelnionych GET, wszystkie HTTP 200, bez zapisów na koncie**. Schematy odpowiedzi i zgodność tekstu z `structuredContent` przeszły. Porównanie odpowiedzi MCP z przechwyconym JSON API potwierdziło identyczne próbki zakresu 590–610 oraz cały obiekt statystyk interwału 439–669 aktywności `i182955288`. Odczyt custom items pozostał `partial` z istniejącym ostrzeżeniem `DECLARED_METADATA_INCOMPLETE`; etykiety `MeanVT=L/br` i `MeanVE=L/min` pozostały źródłowymi deklaracjami. Prywatny dowód lokalny: `.runtime/tymewear-vt-docs-final-20260910/verification.json` oraz odpowiedzi i log GET w tym samym katalogu. To weryfikacja odczytu z bieżącego checkoutu, nie publikacja ani potwierdzenie kalibracji urządzenia.
