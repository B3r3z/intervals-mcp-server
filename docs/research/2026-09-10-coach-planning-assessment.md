# Ocena narzędzi i danych z perspektywy coacha wytrzymałościowego

## Werdykt

Zestaw jest mocną podstawą do analizy wykonanych treningów kolarskich. Zapewnia dobry materiał do budowy kontekstu obciążenia, ale sam MCP nie dostarcza kompletnego kontekstu zawodnika potrzebnego do wyboru celu i dawki kolejnej jednostki. Największą wartość przyniesie połączenie danych treningowych z profilem, rozmową, historią zaleceń i obserwowaną reakcją na wcześniejsze obciążenia.

Ocena dotyczy obecnego lokalnego MCP oraz odczytanych danych konta. Nie jest audytem osobnej pamięci/profilu coacha w innym projekcie, diagnozą medyczną ani nowym planem treningowym. Oceny poniżej są jakościową oceną trenerską, nie wynikiem benchmarku.

| Zadanie coacha | Ocena | Uzasadnienie i warunek użycia |
|---|---|---|
| Odtworzenie przebiegu sesji kolarskiej | Mocne | Szczegóły, zapisane interwały, próbki, źródła i kontrola jakości pozwalają sprawdzić przebieg. Nazwa sesji i oznaczenie WORK/RECOVERY nie wystarczają do określenia bodźca. |
| Ocena kosztu treningu i ostatnich tygodni | Dobre podstawy | Historia wszystkich dostępnych sportów, czas, load, strefy i wellness są dostępne. Trzeba obsłużyć strony, krótkie dodatkowe nagrania i zachować rozróżnienie miar obciążenia. |
| Ocena odpowiedzi i regeneracji | Warunkowa | Są regularne dane snu, HRV i spoczynkowego HR. Ograniczeniem jest feedback, metoda pomiaru, osobisty punkt odniesienia i kontekst pozatreningowy. |
| Ocena realizacji planu | Częściowa | Można odczytać powiązany plan i wykonanie. Brakuje automatycznego dopasowania kroków z pewnością dopasowania i gwarantowanej historycznej wersji planu. |
| Zaplanowanie kolejnego tygodnia | Możliwe po uzupełnieniu kontekstu | Odczyty zapewniają znaczną część faktów, ale potrzebne są cel bloku, czas, ograniczenia, priorytety i aktualne informacje od zawodnika. |
| Progresja bloku/sezonu | Sam MCP niewystarczający | Historia treningów i krzywe mocy są przydatne; nie przechowują pełnego uzasadnienia bloku, kryteriów progresji ani historii tolerancji konkretnego bodźca. |
| Dostarczenie planu do kalendarza | Zabezpieczenia techniczne obecne | Safe writes mają dziennik, kontrolę tożsamości i odczyt po zapisie. Testy odczytów nie potwierdzają działania zapisów live ani jakości sportowej planu. |

## Podstawa oceny

W tej ocenie odświeżono live pięć narzędzi: capabilities, historię aktywności, wellness, kalendarz i ustawienia rowerowe. Wykonano cztery GET do Intervals.icu, wszystkie HTTP 200. Wszystkie pięć odpowiedzi spełniło reklamowany schemat MCP i zgadzało się z tekstowym JSON. Nie wykonywano zapisów na konto.

Zakres historii i wellness: **13 sierpnia–9 września 2026**, 28 zakończonych dni, strefa Europe/Warsaw. Kalendarz przyszły: **10–23 września włącznie**. Dodatkowo wykorzystano zapisane wcześniej w tej rozmowie wyniki live dla 3 i 5 września oraz odczyt kodu interfejsów. Nie powtarzano wszystkich odczytów tych dwóch sesji.

| Dostępność w odświeżonym oknie | Wynik |
|---|---|
| Aktywności | 18 rekordów: 12 Ride, 4 VirtualRide, 2 Run; brak następnej strony |
| Czas i ogólne obciążenie | Wartości obecne w 18/18 rekordów |
| RPE i feel | Każde pole obecne w 6/18 rekordów |
| Węglowodany spożyte | Wartość obecna w 3/18 rekordów |
| HRV, restingHR, sleepSecs, sleepScore | Każde pole obecne w 28/28 rekordów wellness |
| Fatigue, soreness, stress, mood, motivation, injury, comments | Brak wartości we wszystkich 28 rekordach wellness |
| Bieżące ustawienia rowerowe | FTP i indoor FTP 228 W, W′ 16 000 J, Pmax 900 W, LTHR 172 bpm |
| Progi krzywych zmęczenia kj0/kj1 | Oba nieustawione |
| Przyszły kalendarz | API zwróciło zero wydarzeń dla badanego zakresu |

To pokrycie pól w odpowiedzi API, a nie potwierdzenie poprawności protokołu pomiarowego lub kompletności całej aktywności życiowej. Osiemnaście rekordów nie musi oznaczać osiemnastu odrębnych jednostek: występują też krótkie zapisy tego samego dnia. Nie wymagałbym osobnego RPE dla każdego pliku. Pusty przyszły kalendarz nie oznacza nieograniczonej dostępności czasowej. Puste pola objawów nie oznaczają ich nieobecności. Komentarzy wszystkich 18 aktywności nie odczytywano; pokrycie RPE nie jest miarą pełnej dostępności feedbacku.

Dowody tej kontroli: ignorowany katalog `.runtime/coach-context-assessment-20260910/`, w tym `responses/`, `http.jsonl` i `verification.json`. Metody i dane wcześniejszych prób znajdują się w [audycie live](2026-09-10-live-coach-audit.md), [raporcie implementacji](2026-09-10-coach-read-implementation.md) i `.runtime/live-session-20260903/responses/`.

## Co narzędzia wnoszą do decyzji

`get_session_context`, `get_activity_intervals` i `get_activity_streams` pozwalają przejść od podsumowania do konkretnego fragmentu. `get_activity_interval_stats`, `get_activity_power_hr`, krzywe mocy i best efforts pozwalają sprawdzić odpowiedź przy określonym bodźcu. `get_activity_data_quality` pomaga ocenić, czy dane nadają się do takiej analizy. Jawne braki, null, zero, pominięcia w kompakcie i niezależne błędy źródeł ograniczają ryzyko dopowiadania faktów.

`get_activities`, `get_wellness_data`, `get_events` i `get_sport_settings` dostarczają większość obserwowalnego kontekstu ostatnich tygodni oraz kalendarza. Rozróżnienie bieżących progów i progów przypisanych aktywności jest wartościowe. Nadal trzeba ustalić, skąd pochodzą progi, kiedy oceniano ich adekwatność i do jakiego zastosowania są przyjęte. Data edycji ustawień nie jest datą testu fizjologicznego.

Łączny koszt dnia trzeba odróżnić od kosztu jednej aktywności: 5 września główna jazda ma load 292, a trzy zapisy dnia łącznie 308 według tego pola. Nie należy do tego dodawać Strain Score tej samej jazdy, HRSS ani czasu w strefie Sweet Spot jako kolejnych niezależnych obciążeń. Dane innych sportów pomagają uwzględnić dodatkową pracę; wspólny load nie opisuje wszystkich różnic między rodzajami wysiłku.

## Najważniejsze ograniczenia decyzyjne

### 1. Brakuje regularnie utrwalanego wyjaśnienia od zawodnika

3 września aktualnie zapisany plan ma 62 min, a aktywność trwa 35:07. Są trzy oznaczone odcinki WORK, lecz brak RPE, feel i opisu przyczyny odstępstwa; dostępny komentarz jest technicznym testem integracji. Mogę zauważyć różnicę i sprawdzić przebieg, ale nie ustalić, czy ograniczeniem był czas, zmęczenie, dolegliwość, celowa zmiana czy inny powód.

Od tej odpowiedzi zależy następna decyzja: skrócenie z powodu czasu i skrócenie z powodu problemu z tolerowaniem wysiłku nie uzasadniają takiej samej adaptacji. Potrzebny jest krótki zapis: trudność sesji, co ograniczało, powód zmian, ewentualne dolegliwości i aktualne ograniczenia następnych dni. Może pochodzić z rozmowy i trwałej pamięci; nie wymaga osobnego API, jeśli obecny zapis działa. Badania wspierają uwzględnianie miar subiektywnego samopoczucia w monitorowaniu odpowiedzi na obciążenie. [Saw i wsp., przegląd 56 badań](https://pubmed.ncbi.nlm.nih.gov/26423706/).

### 2. Profil i zamiar treningowy muszą być osobną, trwałą częścią kontekstu

Do doboru treningu potrzebne są cel i jego termin, priorytety, doświadczenie, dostępny czas, preferencje i ograniczenia, sprzęt, intencja bieżącego bloku oraz historia decyzji. MCP może znaleźć część informacji w wydarzeniach, opisach i wellness, ale nie składa ich w aktualny profil z pochodzeniem i datą ważności. Nie należy wnioskować tych elementów z samego tytułu jazdy.

Podział odpowiedzialności może być prosty: Intervals dostarcza aktualny kalendarz i zapis aktywności; pamięć coacha przechowuje profil, feedback, uzasadnienia, pytania otwarte i historyczne zalecenia. Nie ma potrzeby tworzenia drugiego szczegółowego kalendarza.

### 3. Gotowy wskaźnik wymaga sprawdzenia zastosowania

3 września analiza całej jazdy zwraca decoupling 5,819%, HR lag 37 s oraz warmup/cooldown równe zero. Pierwszy WORK trwa 230 s i ma decoupling 5,918%. Są to różne zakresy i nie należy zakładać identycznego algorytmu. Autor Intervals opisuje analizę całej jazdy z korektą opóźnienia HR i filtrowaniem fragmentów, natomiast interwału — jako porównanie relacji średniej mocy do HR w jego połowach. [Opis różnicy przez autora](https://forum.intervals.icu/t/negative-aerobic-decoupling/328).

Wskaźnik z krótkiego odcinka ze wzrostem HR nie wystarcza do decyzji o bazie tlenowej, progu lub zmianie intensywności. Wybrałbym odpowiedni, porównywalny fragment, uwzględnił czas, stabilność mocy, rozgrzewkę i warunki. Autor API również wskazuje ograniczenia krótkich interwałów związane z HR lag. [Obliczenia i ograniczenia interwałów](https://forum.intervals.icu/t/aerobic-decoupling-calculation-question/1823).

Podobnie dzienne HRV powinno być odnoszone do własnej historii i warunków pomiaru oraz zestawiane z innymi obserwacjami. W świeżym odczycie po 5 września widać HRV 31 → 40 → 54 → 62 ms w dniach 6–9 września, zmianę snu i spoczynkowego HR. To materiał do oceny odpowiedzi, a nie samodzielny dowód gotowości do określonej sesji. Badania HRV-guided training wskazują znaczenie metodologii i ograniczoną pewność przewagi w wynikach sportowych. [Przegląd metodologiczny i metaanaliza](https://pubmed.ncbi.nlm.nih.gov/34639599/).

### 4. Jakość danych powinna zależeć od typu sygnału i pytania

W zapisie 3 września moc i HR mają po 2108 kompletnych próbek. Stream `hrv` zawiera zagnieżdżone listy; obecny raport oznacza 2105 pozycji jako nieprzydatne do skalarnej analizy numerycznej. Nie dowodzi to awarii czujnika. Potrzebne jest jawne rozróżnienie nieobsługiwanego kształtu, brakującej próbki, wartości nieważnej i artefaktu pomiarowego.

W polach oddechowych występuje `MeanVT=156,41` z deklaracją custom `L/br`, podczas gdy źródłowy `tidal_volume` nie podaje jednostki. `TymeVentilation` ma deklarację `vol/min`, a `MeanVE` — `L/min`. Potrzebne są zweryfikowane jednostki, skala i przekształcenia. Do tego czasu danych tych nie używałbym do wyznaczania progów oddechowych. Kontrola matematycznej dostępności nie potwierdza poprawności fizjologicznej.

`partial` także wymaga odczytania przyczyny: pominięcie części serii w kompakcie lub błąd opcjonalnej krzywej kj0 nie unieważnia dostępnego wyniku całej jazdy lub krzywej normalnej. Z drugiej strony kompletna odpowiedź API nie ustanawia poprawnego protokołu analizy dryfu.

### 5. Historia planu i dopasowanie wykonania są niepełne

Powiązany event przedstawia aktualnie zapisany plan. Nie gwarantuje wersji obowiązującej podczas wykonywania sesji. Zapisane interwały mogą być edytowane, a `compliance` nie podaje przyczyny rozbieżności i nie jest miarą zrealizowanej adaptacji fizjologicznej. Na przykład cały wymagający zapis 5 września ma etykietę RECOVERY — nie wolno na tej podstawie sklasyfikować go jako lekkiej jednostki.

Potrzebne są historyczne snapshoty zaleceń i uzasadnień oraz porównanie kroków z wykonaniem z jawną pewnością dopasowania. Warto wykorzystać istniejące odczyty, zamiast od nowa implementować pobieranie danych.

## Zakres sportów i publikowania

Odczyt historii obejmuje także bieganie; w badanym oknie były dwa biegi. To pozwala uwzględnić zgłoszone i zapisane obciążenie poza rowerem. Obecny kontrakt safe writes obejmuje rower i siłę, a nie pełne planowanie Run/Swim. Dla siły brakuje spójnego odczytu wykonanych ćwiczeń, serii, powtórzeń, ciężaru i RIR; ogólny czas lub masa podniesiona nie wystarczą do prowadzenia progresji.

Dzienniki i niezależne read-back zwiększają kontrolę nad wykonaniem zleconej operacji. Nie potwierdzają zasadności sportowej zalecenia. Ta ocena nie obejmuje zapisów live ani wdrożonego kontenera; ogólne capabilities pozostają `live_verified=false`.

## Kolejność usprawnień

| Priorytet | Usprawnienie | Praktyczny efekt dla coacha |
|---|---|---|
| 1 | Trwały profil, krótki feedback i historia decyzji | Wiadomo, po co planować sesję, czy jest wykonalna i dlaczego poprzednie zalecenie zmieniono. Wykorzystać rozmowę i proste dokumenty; nie wymagać nowego endpointu bez potrzeby. |
| 2 | Kontekst okresu planowania, np. `get_planning_context` | Jedno wejście niezależne od ID aktywności: jawna data oceny, historia, wellness, przyszły kalendarz, progi, pokrycie i kontynuacje. Nie powinno samo wydawać arbitralnego readiness score. |
| 2 | Jakość zależna od sygnału i zastosowania | Typ próbki, zweryfikowane jednostki i skala, pokrycie wybranego fragmentu, ograniczenia zastosowania. Szczególnie HRV i dane oddechowe. |
| 3 | Wersja zaleceń i porównanie plan–wykonanie | Zachowanie historycznej recepty; dopasowanie kroków ze wskazaniem niepewności i brakującego wyjaśnienia. |
| 4 | Porównywanie podobnych sesji | Progresja oceniana na porównywalnych wysiłkach, przy właściwych historycznych progach i kontekście, nie na pojedynczym rekordzie lub nazwie jednostki. |

Powyższe nazwy nowych narzędzi są propozycjami; nie zostały zaimplementowane w ramach tej oceny. Kontekst okresu powinien korzystać z istniejących odczytów i ujawniać granice historii, a nie maskować paginację. Pomocne są metadane o tym, jakie braki faktycznie mogą zmienić decyzję, zamiast wymagać zapełnienia wszystkich pól API.

## Jak prowadziłbym decyzję treningową

1. Odczytać cel, intencję bloku, ograniczenia i poprzednie uzasadnienie planu.
2. Zebrać historię obciążenia, reakcję z wellness, feedback oraz przyszły kalendarz w jawnym oknie.
3. Sprawdzić jakość danych istotnych dla aktualnego pytania i wybrać potrzebne analizy sesji.
4. Oddzielić fakty, hipotezy i brakujące wyjaśnienia; zadać pytanie tylko wtedy, gdy odpowiedź może zmienić decyzję.
5. Wybrać utrzymanie planu, zmianę konkretnej sesji lub rewizję bloku, z krótkim uzasadnieniem i warunkiem ponownej oceny.
6. Po zatwierdzonym w danym systemie działaniu zapisać i zweryfikować kalendarz oraz utrwalić decyzję i późniejszą odpowiedź zawodnika.

Najbliższym krokiem wybrałbym uporządkowanie profilu/feedbacku i kontekstu okresu. Obecna liczba wskaźników wystarcza już do zadawania dobrych pytań trenerskich; kolejne wskaźniki nie zastąpią informacji, która wyjaśnia zachowanie podopiecznego.
