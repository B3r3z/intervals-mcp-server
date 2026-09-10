# Independent agent evaluation — 2026-09-09

**12/12 answers passed root review for factual support and the agreed inference limits.** No material unsupported conclusion or critical MCP defect was found in this run. Passing includes correctly explaining insufficient data; it does not imply a numerical answer is possible in every case.

This was one fresh agent (`fork_turns=none`), separate from the scripted tests. It chose tools and arguments from the actual public MCP catalogue and received results through ClientSession/stdio. The server used synthetic GET-only HTTP fixtures. Blinding was by explicit instructions in a shared workspace, not an OS-enforced access boundary. This is not a statistical benchmark or a live account test. The evaluator did not grade itself.

The [machine-readable evidence](v1_independent_agent_evaluation.json) retains all answers, chosen arguments, root findings, source hashes, costs and structured results. Large base64 bodies and the server artifact path are replaced by explicit markers; original result file hashes remain. Raw client captures are retained locally under `.runtime/v1-agent-client`.

## Protocol and integrity evidence

- All **42 tools/call results** (41 scenario calls plus one discovery call) validate against the advertised output schemas and match their JSON text. Domain errors remain structured envelopes.
- All **31 serving-file hashes** match the pre-evaluation freeze. The production code and fixture server did not change during the run.
- Root independently reconstructed the same **299,283 artifact bytes from 10 MCP chunks**, checked every chunk hash, contiguous offsets, EOF and stream counts, and compared the bytes with the evaluator's reconstructed file. No server artifact file was needed.
- Full SHA-256: `01e1228923a183c592ce05a0053ebfaae2064050a28cf952cc4a1e319869db4b`. This verifies a local composite assembled from separate upstream reads, not upstream atomicity.
- The private HTTP audit contains **49 synthetic GET attempts**, including read retries; no mutation. For S12 the three contexts used 2/4/4 attempts. These private counts were not required in the agent's answer.

## Measured costs

Counts exclude discovery, initialization, internal catalogue reads performed by each bridge command, process startup and JSON-RPC framing. Complete result bytes include both structured and text content; these are byte measurements, not tokens or a runtime comparison.

| Case | Root review | MCP calls | HTTP attempts | Text bytes | Result bytes |
| --- | --- | ---: | ---: | ---: | ---: |
| S01 | pass | 1 | 2 | 10,025 | 16,868 |
| S02 | pass | 3 | 3 | 6,299 | 11,724 |
| S03 | pass | 4 | 4 | 9,159 | 16,657 |
| S04 | pass | 2 | 2 | 7,943 | 13,812 |
| S05 | pass | 3 | 7 | 16,944 | 29,369 |
| S06 | pass | 4 | 5 | 19,097 | 33,908 |
| S07 | pass | 2 | 4 | 5,779 | 10,476 |
| S08 | pass | 4 | 4 | 11,345 | 20,322 |
| S09 | pass | 12 | 3 | 430,779 | 858,723 |
| S10 | pass | 2 | 2 | 2,958 | 5,793 |
| S11 | pass | 1 | 3 | 7,175 | 12,499 |
| S12 | pass | 3 | 10 | 20,675 | 36,119 |
| **Total** | **12/12** | **41** | **49** | **548,178** | **1,066,270** |

Separately, one general metric-definition call used 0 HTTP attempts, 25,736 text bytes and 47,230 result bytes; the explicit initial tool-catalogue listing was 77,686 bytes. The agent's sequence is different from the scripted sequence and is not a like-for-like optimization comparison.

## Limits and optional improvements

- One synthetic agent run, with instruction-based blinding in a shared workspace; not a statistical benchmark or an OS-enforced access boundary
- No live account, deployment, or mutation was exercised
- Tool choices were useful but not minimal: S03 used extra full curve reads, and the general metric catalogue was fetched before case-specific work
- S05 has insufficient execution samples for plan adherence; historical activity date in S03 and formal custom definition in S10 are unavailable
- The metric catalogue is deliberately non-exhaustive: S06 correctly retained hr_load as unknown rather than assigning an unsupported formula or unit
- Smaller compact metadata and more selective discovery could reduce response size. The measured S01 context saves calls but is larger than separate minimal reads; no token saving is claimed.

## Reviewed answers

The Polish answers below are retained from the evaluator. Root's separate findings follow each answer. The linked JSON contains the exact evidence filenames and structured results for each chosen call.

### S01

Cztery odcinki WORK mają po 480 s czasu ruchu (8 min). Zwrócone przez źródło średnie:

| Powtórzenie | Średnia moc | Średnie tętno | Następująca regeneracja |
|---|---:|---:|---|
| 1 | 315 W | 154 bpm | 420 s, 125 W, 138 bpm |
| 2 | 318 W | 155 bpm | 420 s, 125 W, 137 bpm |
| 3 | 321 W | 156 bpm | 420 s, 125 W, 136 bpm |
| 4 | 324 W | 157 bpm | 420 s, 125 W, 135 bpm |

Obliczenie klienta: czwarta moc minus pierwsza = 324−315 = +9 W, czyli 9/315×100 ≈ +2,9%; średnie tętno wzrosło o 157−154 = 3 bpm. Czasy ruchu sumują się do 4×480 = 1920 s pracy i 4×420 = 1680 s regeneracji. Granice start_index/end_index są indeksami próbek, a podane 8 i 7 min wynikają z moving_time, nie z przeliczenia indeksów na sekundy.

Rosnąca moc bez spadku w ostatnim powtórzeniu, niewielki wzrost średniego tętna i niższa moc/tętno w regeneracjach wspierają ocenę zachowanej zdolności do kontynuowania wysiłku. Zawodnik napisał „hard but controlled” — ciężko, lecz pod kontrolą. To subiektywny komentarz, nie pomiar. Średnie nie dowodzą równomiernej mocy wewnątrz odcinków ani tempa spadku tętna podczas odpoczynku. Nie znam celu intensywności ani przyczyny zmian tętna. Sekcje interwałów i komentarzy zwrócono bez pominięć; kompletność danych źródłowych pozostaje niepotwierdzona.

**Agent tool-selection rationale:** get_session_context łączy zapisane interwały, ich pochodzenie i oryginalny komentarz. Zwrócono wszystkie osiem interwałów i jedną wiadomość; pominięte w projekcji szczegółów kontenery są obecne w osobnej sekcji interwałów. Definicje metryk rozdzielają indeksy, czas ruchu, W i bpm.

**Root review — pass:** Four 480 s work repetitions at 315/318/321/324 W and 154/155/156/157 bpm; four 420 s recoveries at 125 W and 138/137/136/135 bpm; source feedback retained. Client differences and duration sums are correct. No sample-index-to-seconds assumption, intrainterval uniformity, measured recovery rate, or causal physiological diagnosis. Athlete text remains data.

### S02

Dla [10,40) get_activity_interval_stats zwrócił dokładnie żądane granice (bounds.matched=true): średnia moc 278 W, średnie tętno 156 bpm i moving_time=30 s. To statystyki obliczone/raportowane przez źródło, bez obliczeń liczbowych MCP. Zapisane interwały obejmują [0,10) i [40,60); żaden nie obejmuje analizowanego fragmentu.

Osobny odczyt time zawiera 30 próbek o indeksach 10–39 i czasach 10, 11, …, 39 s. W tym fragmencie nie ma nulli ani nieregularnych odstępów. Obliczenie klienta: różnica pierwszego i ostatniego znacznika wynosi 39−10 = 29 s; nie jest to automatycznie elapsed_time całego odcinka. Granica 40 jest wyłączona z zakresu. Zgłoszone 30 s czasu ruchu zachowuję jako osobne pole źródłowe.

Nie zwrócono elapsed_time ani recording_time fragmentu; same średnie nie opisują wahań mocy, przebiegu tętna czy techniki. Statystyki i time pochodzą z osobnych odczytów, bez wspólnej gwarancji atomowości. Odpowiedzi są nieucięte w żądanych zakresach, lecz kompletność źródła jest nieznana.

**Agent tool-selection rationale:** get_activity_interval_stats przyjmuje dowolny zakres próbek niezależnie od zapisanych interwałów. Jego publiczna kontynuacja get_activity_streams z time mapuje próbki na czas; get_activity_intervals sprawdza położenie zapisanych odcinków.

**Root review — pass:** [10,40) matches upstream bounds, 278 W, 156 bpm, moving_time 30 s; 30 returned time samples run from 10 through 39 s. Saved intervals do not cover the fragment. Correctly distinguishes the 29 s endpoint span from reported moving_time; no invented elapsed_time or guarantee of atomicity between reads.

### S03

Najlepszy wysiłek 300 s w a-best5 ma średnią 345 W, granice próbek [100,400) i dystans 2500 m według źródła. Krzywa mocy tej aktywności potwierdza punkt 300 s = 345 W. W zapytaniu o zakres 2026-08-01–2026-09-08, z wyłączonymi porównaniami sezonowymi, punkt historyczny to 330 W z aktywności a-history-300. Zwrócono również historyczne 4,58 W/kg, z tym samym identyfikatorem wkg_activity_id; wartość W/kg tej sesji nie została podana.

Obliczenie klienta: 345−330 = +15 W; 15/330×100 ≈ +4,5% względem zwróconego punktu historycznego. Dotyczy to otrzymanych wyników, bez gwarancji kompletnej historii lub rekordu osobistego. Nazwy i dokładnej daty historycznej aktywności nie ma w zwróconym punkcie.

Pełne odczyty nie zwracają punktów dla 5, 15, 30, 60, 120, 600, 1200 i 3600 s; to braki, nie zera. Krzywa aktywności ma dodatkowo FATIGUE_SELECTION_UNVERIFIED: żądanie normal nie zostało potwierdzone jawną etykietą krzywej. Bezpośredni wynik best effort nadal podaje 300 s i 345 W. Parametr include_normalised oznacza tu serię W/kg, nie Normalized Power. Z tego porównania nie wyznaczam FTP ani VO₂max; kompletność źródła pozostaje nieznana.

**Agent tool-selection rationale:** get_activity_best_efforts wybiera rzeczywiste najlepsze 300 s i zachowuje granice. get_athlete_power_curves pozwala zadać konkretny zakres dat i zachować identyfikator historycznej aktywności. Pełne krzywe pokazują dostępny surowy zakres, brakujące standardowe czasy i ograniczenie selektora fatigue.

**Root review — pass:** 300 s session effort 345 W at [100,400), historical 330 W from a-history-300 in the requested period, historical 4.58 W/kg. +15 W / approximately 4.5 percent calculation is correct; listed missing durations match full curve results. No invented exact historical date, lifetime record, FTP or VO2max; W/kg is not Normalized Power. Fatigue-selection and unknown-coverage limits retained.

### S04

Aktualne przy pobraniu ustawienia Ride podają after_kj0=246 kJ i after_kj1=480 kJ. Zapytałem o krzywe normal, kj0 i kj1 dla 300 s. Zwrócone punkty źródłowe:

| after_kj w krzywej | Moc 300 s | Granice próbek |
|---|---:|---|
| null | 410 W | [0,300) |
| 246 kJ | 390 W | [600,900) |
| 480 kJ | 370 W | [1200,1500) |

Obliczenie klienta względem punktu 410 W: 390−410 = −20 W, czyli −4,9%; 370−410 = −40 W, czyli −9,8%. Zwrócone wartości po wskazanych progach pracy są niższe, a ich after_kj odpowiada wartościom bieżących ustawień.

Nie można jednak bezwarunkowo nazwać punktu z after_kj=null wynikiem „przed pierwszym progiem”. Nie ma jawnych etykiet fatigue; selection.verified=false oraz ostrzeżenia FATIGUE_SELECTION_UNVERIFIED i FATIGUE_THRESHOLD_UNAVAILABLE uniemożliwiają potwierdzenie pełnego odwzorowania żądanych selektorów. Indeksy nie są sekundami. Krzywe przedstawiają najlepsze osiągnięte moce w zwróconych warunkach, nie kontrolowany test maksymalnej zdolności ani dowód, że spadek spowodowało wyłącznie zmęczenie. Bieżące ustawienia nie dowodzą historycznej konfiguracji aktywności, a kompletność źródła jest nieznana.

**Agent tool-selection rationale:** get_sport_settings ujawnia skonfigurowane progi pracy i ich jednostki. get_activity_power_curves z trzema selektorami oraz pełnym detalem zachowuje after_kj, granice i dane o niepotwierdzonej tożsamości selektorów zamiast domyślania się jej z kolejności krzywych.

**Root review — pass:** Current work selectors 246/480 kJ; returned 300 s points 410/390/370 W with after_kj null/246/480 and correct sample bounds. -20/-40 W and percentage changes are correct. Does not equate null with zero, infer selector identity from order, call the reference necessarily before the first threshold, substitute current historical settings, or diagnose a causal fatigue mechanism.

### S05

Aktywność a-plan z 2026-09-08 07:30 ma numeryczne powiązanie paired_event_id=9001. Zwrócony trening 9001 jest zapisany na 2026-09-07 18:00; resolve wykonano dla dnia wydarzenia, nie dnia aktywności. Jego aktualny zapis zawiera jeden krok 300 s: cel mocy _power.value=221 W (216–226), tętna _hr.value=150 bpm (145–155) i prędkości _pace.value=4,0 m/s (3,9–4,1).

Źródła progów są różne:

| Źródło | FTP | LTHR | Prędkość progowa |
|---|---:|---:|---:|
| Przypisane aktywności | 245 W | 165 bpm | nie podano |
| Zapis wydarzenia/dokumentu treningu | 260 W | 166 bpm w dokumencie | 4,1 m/s |
| Aktualne ustawienia Ride | 280 W | 168 bpm | 4,2 m/s |

Ustawienia mają też indoor_ftp=275 W; nie potwierdzono, że ta sesja używa tej wartości. pace_units=MINS_KM jest preferencją wyświetlania, nie zmianą jednostki threshold_pace z m/s.

Obliczenie klienta: 221/260×100 = 85%, 221/245×100 ≈ 90,2%, a 221/280×100 ≈ 78,9%. To ilorazy do trzech różnych baz, nie dowód pierwotnej reguły procentowej planu. Dzisiejszego FTP nie należy podstawiać w miejsce zapisanych progów ani na jego podstawie odtwarzać celu 221 W.

Wykonanie ma 2700 s czasu ruchu i 2850 s czasu całkowitego. Zwrócono poprawny pusty kontener interwałów. Dodatkowy odczyt wszystkich dostępnych próbek wybranych strumieni daje zaledwie 6 punktów dla 0–5 s, z luką null w mocy i tętnie; to za mało do oceny realizacji kroku 300 s. Nie potwierdzam zatem zgodności wykonania z celem ani nie traktuję różnicy czasu planu i aktywności jako dowodu błędnego wykonania. PLAN_IS_CURRENT_STORED_VERSION oznacza, że otrzymany plan może różnić się od wersji wykonanej historycznie; kompletność źródła pozostaje nieznana.

**Agent tool-selection rationale:** Pełny get_session_context z planem zachowuje numeryczne powiązanie, surowy i rozwiązany dokument oraz progi historyczne. Osobny get_sport_settings sprawdza dzisiejsze wartości. Przy pustych interwałach get_activity_streams sprawdza, czy dostępne próbki pozwalają porównać wykonanie.

**Root review — pass:** Exact paired event 9001 resolved on its own date, excluding the same-day decoy. Activity/event/current FTP 245/260/280 W; resolved 221 W, 150 bpm and 4.0 m/s with returned ranges. Durations 2700/2850 s, empty intervals and six stream samples are reported correctly. Fetched plan is current stored content, not immutable history. Client ratios are not asserted to be the original plan rule; no fabricated adherence score from insufficient execution data.

### S06

To sesja Ride z 1800 s czasu ruchu i 2100 s czasu całkowitego. Aktywność ma LTHR=165 bpm i athlete_max_hr=190 bpm, a przypisane granice stref tętna to [120,145,165,180] bpm. Zwrócone czasy czterech stref, w kolejności źródła, wynoszą 300, 700, 600 i 200 s. Obliczenie klienta: suma = 1800 s; dwie wyższe zwrócone strefy = 600+200 = 800 s, czyli 800/1800×100 ≈ 44,4%. Wskazuje to na mieszaną intensywność z częścią czasu w wyższych strefach. Zawodnik opisuje wysiłek jako ciężki, lecz kontrolowany.

Odczyt zakresu [0,12) z tym samym snapshotem co podgląd zachowuje 12 próbek time i heartrate: 0–11 s oraz 140–175 bpm. Są tam wartości powyżej przypisanego LTHR. Ten krótki fragment nie reprezentuje automatycznie całych 30 min. Strumień watts jest jawnie niedostępny; brak też zapisanych interwałów. Nie wyliczam intensywności ani obciążenia z mocy.

Zgłoszono hr_load=64, hr_load_type=AVG_HR i ogólne icu_training_load=64 (jednostka katalogowa score, czyli wynik punktowy). To liczbowo zgodne pola z selektorem metody tętna AVG_HR; nie jest to równoznaczne z TSS, Strain Score ani TRIMP. icu_training_load_data=17 jest nieprzezroczystą informacją źródłową, nie dodatkowym wynikiem ani rozpoznaną jednostką. Katalog nie zna definicji hr_load (UNKNOWN_METRIC_NAME), więc nie potwierdza jego osobnego wzoru lub jednostki. Nie zwrócono power_load ani Strain Score. Pełne źródłowe pokrycie pozostaje nieznane.

**Agent tool-selection rationale:** get_session_context daje przypisane strefy, czasy, pola obciążenia i feedback. Odczyt strumieni potwierdza dostępność tętna oraz brak mocy; kontynuacja usuwa pominięcia podglądu. Selektywne get_metric_definitions weryfikuje znaczenie pól obciążenia i ujawnia nieznaną definicję hr_load.

**Root review — pass:** Moving/elapsed 1800/2100 s; activity LTHR/max HR 165/190 bpm and zone times 300/700/600/200 s. Sum and 800/1800 percentage are correct. HR-only samples, load 64, AVG_HR and opaque numeric code 17 preserved. No power-derived load, TSS/SS/TRIMP substitution or undocumented hr_load formula. Short stream segment does not represent the entire session.

### S07

Nie da się liczbowo określić obciążenia a-hidden. Szczegóły są ograniczonym rekordem Hidden ze źródłem STRAVA, identyfikatorem a-hidden i datą lokalną 2026-09-08 07:30. Sekcja ma status partial, SOURCE_DATA_LIMITED i source_complete_within_query=false. Nie podano czasu, sportu, progów ani wartości obciążenia.

Dedykowany odczyt interwałów zwrócił poprawne puste listy; odczyt strumieni zakończył się HTTP_403 (brak uprawnienia do zasobu). Data=[] w tym błędzie nie oznacza poprawnego odczytu pustej aktywności. Dostępny jest komentarz zawodnika „hard but controlled”, ale sam opis nie wystarcza do wyznaczenia TSS, SS ani innego wyniku obciążenia. Rekord ukryty, puste interwały i odmowa dostępu nie stanowią dowodu odpoczynku ani zerowego obciążenia.

**Agent tool-selection rationale:** get_session_context rozdziela ograniczone szczegóły od komentarzy i dedykowanych interwałów. Zgodnie z opisem narzędzia szczegółów niezależnie sprawdziłem get_activity_streams; odpowiedź 403 wyznacza granicę dostępnej informacji bez prób obchodzenia uprawnień.

**Root review — pass:** Hidden/STRAVA stub, SOURCE_DATA_LIMITED, false source completeness, valid empty dedicated intervals and HTTP 403 streams are distinguished; available feedback is retained. No invented load, zero-training/rest claim, or unsupported claim about who hid the activity.

### S08

Pierwszy odczyt [0,6) dla tego samego wyboru time,watts zwrócił:

| Indeks próbki | time (s) | watts (W) | watts.data2 |
|---:|---:|---:|---:|
| 0 | 0 | 100 | 99 |
| 1 | 1 | null | null |
| 2 | 1 | 0 | 0 |
| 3 | null | 200 | 198 |
| 4 | 4,5 | 250 | 249 |
| 5 | 5,0 | 260 | 259 |

Wszystkie trzy tablice mają po 6 elementów. alignment=aligned potwierdza równe długości, nie regularność czasu: czas 1 s jest powtórzony, znacznik indeksu 3 jest nieznany, a odstępy nie są stałe. null mocy nie zastępuję zerem; 0 W przy indeksie 2 zachowuję jako zgłoszone zero. Znaczenie i jednostka data2 są nieokreślone — nie nazywam tej tablicy raw_watts.

Kontynuacja [3,6) z expected_snapshot_id pierwszego odczytu (08c334a0…70fc38) zwróciła SNAPSHOT_CHANGED i żadnych nowych próbek. Świeży odczyt [0,6) ma snapshot f20fbae0…c287ef: time[4] zmieniło się z 4,5 na 4,7 s, time[5] z 5,0 na 5,2 s, a watts[3] z 200 na 205 W; data2 jest bez zmian. Nie mieszałem wersji.

Ponowna kontynuacja [3,6), z pełnym nowym identyfikatorem oraz niezmienionymi activity_id i stream_types, zakończyła się sukcesem z tym samym snapshotem: time=[null,4.7,5.2], watts=[205,250,260], data2=[198,249,259]. To spójny kolejny zakres nowej wersji. Braki i duplikaty czasu nadal uniemożliwiają proste założenie próbkowania 1 Hz lub rzetelną integrację pracy bez dodatkowych reguł; danych nie przeindeksowałem i nie interpolowałem. Kompletność źródła pozostaje nieznana.

**Agent tool-selection rationale:** get_activity_streams w trybie range zachowuje indeksy i nulle, a expected_snapshot_id pozwala wykryć zmianę przy kontynuacji. Po SNAPSHOT_CHANGED pobrałem nową bazę i dopiero jej snapshotem zabezpieczyłem kolejny zakres tego samego wyboru strumieni.

**Root review — pass:** Original time, watts and data2 preserve duplicate times/null/zero; stale continuation returns SNAPSHOT_CHANGED. Fresh snapshot and next range retain changed times 4.7/5.2 and watts 205 at index 3. Equal lengths do not imply regular sampling, snapshots are not mixed, data2 is not relabelled raw_watts, and gaps are not interpolated.

### S09

Pobrałem pełny artefakt dostępnych strumieni i interwałów przez MCP, bez odczytu ścieżki serwerowej. Po podglądzie wykonałem export_activity_data bez filtra types, a potem pobrałem wszystkie 10 fragmentów get_artifact_chunk w kolejności offsetów. Każdy base64 dekodowałem do bajtów; zweryfikowałem ciągłość offsetów, rozmiary, identyfikator artefaktu i SHA-256 fragmentów. Ostatni fragment ma eof=true.

Obliczenie klienta z odebranych bajtów: 9×32768+4371 = 299283 bajty, zgodnie z manifestem. SHA-256 całości wynosi 01e1228923a183c592ce05a0053ebfaae2064050a28cf952cc4a1e319869db4b i jest zgodny z manifestem. Dopiero po złączeniu oraz weryfikacji zdekodowałem cały UTF-8 i JSON. Dokument identyfikuje a-large.

Liczebności policzone w odtworzonym JSON i zgodne z manifestem:

| Kolejność strumienia | Typ | Elementy data | Elementy data2 |
|---:|---|---:|---:|
| 0 | time (s) | 10005 | brak |
| 1 | watts (W) | 10005 | brak |
| 2 | watts (W) | 10005 | 10005 |
| 3 | raw_watts (W) | 10005 | brak |
| 4 | custom_large (jednostka nieznana) | 10006 | brak |

Zachowano oba osobne strumienie watts, ich kolejność, data2 oraz raw_watts. Jednostka i znaczenie data2 nie są określone. custom_large zawiera 3335 nulli i 3336 liczbowych zer (obliczenie klienta); zachowano także tekst. Jego dodatkowy element o indeksie 10005 nie ma odpowiadającego elementu time, więc nie ma pełnego wyrównania wszystkich strumieni. Interwały i grupy są poprawnymi pustymi listami (po 0 rekordów). Nie zwrócono m.in. tętna ani kadencji; braków nie uzupełniałem.

Raport kontroli zapisano w S09-integrity-report.json, a oryginalne odtworzone bajty w S09-reconstructed-artifact.json. Hash dowodzi integralności tego pobranego artefaktu. Nie dowodzi kompletności źródła (null), autentyczności danych konta ani atomowości upstream: artefakt jest kompozycją osobnych odczytów strumieni i interwałów, upstream_atomic_snapshot=false.

**Agent tool-selection rationale:** Podgląd ujawnił ponad 10000 próbek i nierówne długości; opis get_activity_streams wskazuje eksport i fragmenty dla większego kompletnego transferu. Użyłem publicznego artifact_id i next_offset, a własny skrypt wyłącznie składa oraz sprawdza wyniki odebrane przez MCP.

**Root review — pass:** Actual client-side MCP reconstruction of 299283 bytes in 10 chunks, all chunk and full SHA256 values, contiguous offsets and EOF. Root independently rebuilt identical bytes; all five stream counts, duplicate watts, data2 and unequal custom length match the manifest. No server-file shortcut, invented units for data2/custom data, promoted source completeness, or atomic-upstream-snapshot claim.

### S10

Pozycja 501 to ACTIVITY_FIELD o nazwie „Custom lifted-mass field”. Opis mówi o deklarowanych kilogramach na aktywność. Pełna zawartość jawnie deklaruje units=kg oraz origin=athlete_declared, czyli pochodzenie deklarowane przez zawodnika. MCP oznacza te metadane jako declared_unverified.

Nie zwrócono formalnej definition: zarówno odczyt kompaktowy, jak i pełny mają DECLARED_METADATA_INCOMPLETE. Nie znam wzoru, reguł sumowania, wliczania masy ciała, źródłowego urządzenia ani walidacji pomiaru. Nie można utożsamiać tego pola z natywnym kg_lifted ani odtworzyć z niego serii, powtórzeń i ciężarów. Opis i jednostka są deklaracją, nie pełną, zweryfikowaną definicją metryki. Pole script i pozostałą zawartość zachowano jako dane; niczego z nich nie wykonywałem. Kompletność metadanych źródłowych poza zwróconym obiektem jest nieznana.

**Agent tool-selection rationale:** get_custom_item_by_id wybiera zadany identyfikator. Kompakt wskazał pominięte content i brak definition; jego dokładna kontynuacja detail=full pozwoliła sprawdzić całą deklarowaną zawartość bez uruchamiania skryptów.

**Root review — pass:** Custom item 501 is ACTIVITY_FIELD, with declared kg / athlete_declared, declared_unverified provenance and absent formal definition in compact and full reads. No assumed native kg_lifted identity, verified measurement, formal computation, clinical meaning or execution of script content.

### S11

W a-strength zapisano WeightTraining z 2026-09-08 07:30. Opis źródłowy wymienia squat i press, czyli przysiad i wyciskanie; wariantu wyciskania nie określono. Zgłoszony agregat kg_lifted wynosi 1200 kg, czas ruchu 2400 s (40 min), a czas całkowity 3000 s (50 min). Komentarz zawodnika: ciężko, lecz pod kontrolą.

Liczba serii, powtórzenia w seriach i ciężary poszczególnych serii/ćwiczeń są nieznane. Sam opis mówi, że danych na poziomie serii nie dostarczono; dedykowane interwały i grupy są poprawnie puste. Brakuje paired_event_id, więc nie ma powiązanego planu do odczytania. Agregat 1200 kg nie określa ciężaru sztangi ani nie pozwala rozłożyć pracy na serie — wiele układów dałoby taki sam wynik. Nie dopisuję serii, powtórzeń, objętości per ćwiczenie ani oceny techniki. Są to dane zgłoszone przez źródło, a nie nowe obliczenie MCP; kompletność źródła pozostaje nieznana.

**Agent tool-selection rationale:** Pełny get_session_context z details, intervals, plan i comments sprawdza opis wykonanej pracy, ewentualne rekordy serii, powiązanie do planu i feedback. Definicja kg_lifted wyraźnie ogranicza wnioskowanie z agregatu.

**Root review — pass:** WeightTraining, squat/press description, 1200 kg aggregate, moving/elapsed 2400/3000 s, feedback, empty intervals/groups and absent pairing. No invented press variant, sets, repetitions, barbell weights, per-exercise volume or technique assessment.

### S12

Dla każdego identyfikatora get_session_context zwrócił partial i zachował udaną sekcję komentarzy. Dostępna jest po jednej wiadomości zawodnika z 2026-09-08 09:20 +02:00, opisującej wysiłek jako ciężki, lecz kontrolowany.

| Aktywność | Przyczyna niedostępności szczegółów | Zachowany komentarz |
|---|---|---:|
| a-error-shape | INVALID_UPSTREAM_RESPONSE, faza response: odpowiedź szczegółów nie spełnia wymogu niepustego obiektu | id 1271 |
| a-error-timeout | READ_TIMEOUT, faza send: przekroczony czas oczekiwania; brak statusu HTTP | id 1517 |
| a-error-rate | HTTP_429, faza http: zbyt wiele żądań | id 1170 |

Sekcje intervals, plan i wellness w każdym z tych kontekstów są niedostępne wskutek zależności od nieudanego odczytu activity. Nie są to trzy niezależnie potwierdzone awarie odpowiednich zasobów ani dowody, że interwały, plan czy wellness nie istnieją. Szczegółów aktywności nie otrzymano, więc brak podstaw do liczbowej oceny czasu, intensywności i obciążenia. Komentarz jest subiektywną informacją, a jego znacznik czasu nie zastępuje daty wykonania aktywności.

Błędy i data=[] w ich sekcjach nie oznaczają poprawnie odczytanego braku treningu, dnia odpoczynku ani zerowego obciążenia. Dla timeout i 429 narzędzie zaleca ponowienie odczytu; 429 wymaga odczekania przed ponowieniem. Nie podano Retry-After. Niepoprawny kształt wymaga wyjaśnienia odpowiedzi źródła/kontraktu. Udane komentarze pozostają użyteczne mimo tych ograniczeń; kompletność źródła nie została potwierdzona.

**Agent tool-selection rationale:** get_session_context z wszystkimi pięcioma sekcjami pozwala porównać dostępność, fazy błędów, zależności i zachowane sukcesy dla każdego identyfikatora. Nie zastępuję błędów pustymi danymi ani nie wnioskuję o braku treningu.

**Root review — pass:** Three partial contexts preserve one comment each; activity failures are INVALID_UPSTREAM_RESPONSE, READ_TIMEOUT and HTTP_429 with the reported phases. Other unavailable sections correctly retain activity dependencies. Dependent failures are not separate confirmed resource failures, error data is not empty training, comment time is not activity time, and read-retry guidance is not applied to mutations. Public results do not expose retry attempt counts or Retry-After; none was invented.
