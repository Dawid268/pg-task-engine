# pg-task-engine — kontrakt domenowy JobRequest / Job / JobAttempt

**Data projektu:** 2026-10-11

**Status:** specyfikacja do przeglądu użytkowniczki (projekt zaakceptowany w rozmowie; implementacja wymaga oddzielnego planu)

**Zakres:** pierwsza wersja rdzenia biblioteki Python/PostgreSQL. Nie obejmuje implementacji i wdrożenia.

## 1. Problem i cele

Budujemy instalowalną bibliotekę trwałych kolejek zadań. Kod aplikacji zgłasza pracę, silnik przyjmuje zlecenie, workery podejmują próby, a PostgreSQL utrzymuje autorytatywny stan, historię oraz wynik. Biblioteka jest niezależna od FastAPI i GCP. Opcjonalny adapter HTTP wykonuje wywołania na zlecenie workera, a Gateway udostępnia funkcje tej samej biblioteki systemom niepythonowym.

Podstawowe gwarancje: trwałe zlecenie po zatwierdzeniu transakcji, co najwyżej **jeden ważny przydział** danego Job naraz, idempotentne zgłaszanie w zadanym zakresie i odrzucanie zapisów nieaktualnych prób. **Nie** obiecujemy jednorazowego wykonania funkcji ani jej zewnętrznych skutków — po utracie potwierdzenia zadanie może wykonać się ponownie.

Granice: `JobRequest` opisuje intencję; `Job` to odczyt bieżącego, trwałego stanu; `JobAttempt` to zapis jednej przydzielonej próby. Nie są to DTO tego samego zasobu o różnej liczbie pól. Głównym źródłem prawdy jest PostgreSQL, nie obiekt Pythona w pamięci.

## 2. Oddzielne odpowiedzialności i przepływ

1. Aplikacja wybiera zarejestrowaną definicję zadania, kolejkę, argumenty JSON, najwcześniejszy termin i politykę wykonania. Tworzy `JobRequest`.
2. Silnik waliduje dane, kopiuje zwalidowaną reprezentację, rozstrzyga ustawienia domyślne i zapisuje nowy `Job` w PostgreSQL. Dopiero **commit** oznacza trwałe przyjęcie. Wspólna transakcja z danymi aplikacji jest możliwa wyłącznie przez odpowiednie użycie wspólnego połączenia/transaction scope.
3. Worker atomowo przydziela pracę, tworzy `JobAttempt` z numerem i ważnym lease, ustawia `Job.RUNNING` i zatwierdza krótką transakcję. Funkcja zadania wykonuje się **poza** tą transakcją.
4. Worker odnawia lease i przed zatwierdzeniem wyniku wykazuje, że jego token próby nadal jest aktualny oraz przydział nie wygasł. Sukces lub porażka zamyka próbę i transakcyjnie aktualizuje stan Job.
5. Przy retry zlecenie i payload nie zmieniają się; następne przydzielenie tworzy nowy `JobAttempt`. Stany końcowe Job nie są odwracalne.

Rdzeń nie interpretuje znaczenia biznesowego pól payloadu, nie parsuje dowolnych zewnętrznych REST API i nie przechowuje ciężkich plików. Takie czynności należą do zarejestrowanych wykonawców lub wymiennych adapterów.

## 3. Wspólne typy i walidacja

- `JobId`, `AttemptId`, `WorkerId`: **oddzielne typy domenowe** oparte na `UUID`; nie używa się ich zamiennie. Zapis PostgreSQL: `UUID`. W SDK daty mają typ `datetime` z obowiązkową strefą czasową (UTC), a czas trwania `timedelta` lub jawnie opisaną jednostkę liczbową.
- `TaskRef`: stabilna, niepusta nazwa typu zadania (`TaskName`) oraz **dodatni numer wersji kontraktu** (`int >= 1`; wejście/wyjście). Brak zgodnego workera nie daje prawa do arbitralnego wykonania innej wersji; niewykonalne zlecenie pozostaje oczekujące i jest raportowane operacyjnie.
- `JobStatus` i `AttemptStatus`: zamknięte enuma dostarczane przez **bibliotekę**; statusy mogą zmieniać tylko operacje silnika.
- `Queue`: członek **enuma aplikacji**, skonfigurowanego/rejestrowanego przy inicjalizacji silnika; biblioteka nie ma globalnej zamkniętej listy nazw. Domyślna kolejka również musi być zarejestrowana. W PostgreSQL zapisujemy stabilną tekstową wartość z ograniczeniem do skonfigurowanych kolejek. Zarówno adnotacje, jak i walidacja runtime odrzucają nieznane wartości; sam `StrEnum` jest kompatybilny z `str`, więc nie wystarczy jako jedyna kontrola.
- Zarejestrowana definicja zadania wiąże typ wejścia, typ wyniku i wykonawcę. Model żądania ma generyczne typowanie dla payloadu; silnik nie wymaga od wszystkich zadań jednego sztywnego schematu danych biznesowych. Modele Pydantic mogą być adapterem walidacji, ale nie narzucamy zależności Pydantic przy imporcie pakietu `pg_task_engine`.
- Wymagamy świadomej walidacji wejścia przed przyjęciem zadania i ponownie przed wykonaniem zgodnie z wersją `TaskRef`. Nie polegamy jedynie na adnotacjach mypy. Brak obsługi starej wersji schematu przez workera nie może prowadzić do wykonania payloadu pod nową wersją.

## 4. JobRequest — żądanie zlecenia

| Pole | Typ / semantyka |
| --- | --- |
| `task` | Zarejestrowana definicja/`TaskRef` z kontraktem wejścia i wyjścia |
| `queue` | Enum aplikacji; jeśli nie podano, skonfigurowana kolejka domyślna |
| `payload` | Zwalidowane argumenty, reprezentowalne jako **obiekt JSON** (najwyższy poziom: mapowanie nazw do wartości); pusta mapa przy braku argumentów |
| `not_before` | Świadoma strefy czasowej data lub brak (od razu po zatwierdzeniu) |
| `execution_policy` | Konfiguracja liczby prób, timeoutu i retry lub ustawienia domyślne |
| `idempotency_key` | Opcjonalny niepusty klucz ograniczony do przestrzeni danej aplikacji/instalacji |

**Nigdy nie przyjmujemy od aplikacji:** `status`, `attempts_count`, `worker_id`, `finished_at`, wyniku ani nadawanego przez silnik `job_id`.

`payload` nie oznacza pliku ani całego HTTP requestu. Obiekt wejściowy może być silnie typowany w SDK, ale zapis w PostgreSQL to samodzielna, sprawdzona i skopiowana reprezentacja `JSONB`. Odrzucamy nieobsługiwane wartości (np. NaN, Infinity, niepoprawny Unicode), błędy serializacji i przekroczenie limitu **64 KiB po serializacji**. Nie serializujemy arbitralnych obiektów Pythona ani sekretów. Pliki przekazujemy przez trwałe referencje do wersjonowanych obiektów; nie przechowujemy w kolejce plików ani krótko żyjących podpisanych URL-i.

Klucz idempotencji (`IdempotencyKey`: tekst niepusty, maksymalnie 128 znaków) oraz skrót kanonicznej intencji (`task_ref`, `queue`, payload, termin, polityka) są zapisywane atomowo. Porównanie uwzględnia **znormalizowaną intencję**, a nie generowany przez system czas utworzenia: brak `not_before` jest odrębną kanoniczną wartością „jak najszybciej”. Ten sam klucz + ta sama intencja w tym samym zakresie = zwróć istniejący Job, inna intencja = konflikt. W pierwszej wersji klucz żyje co najmniej tak długo, jak przechowywany Job; po jawnym usunięciu historii i klucza nie ma gwarancji deduplikacji. `JobRequest` nie jest zapisywany jako mutowalny obiekt domenowy.

## 5. Job — aktualny trwały stan

| Pole | Typ / znaczenie |
| --- | --- |
| `id` | `JobId`, nadawany przez silnik |
| `task_ref` | Stabilny identyfikator + wersja kontraktu zadania |
| `queue` | Zarejestrowana kolejka (enum po stronie aplikacji) |
| `payload` | Niezmienny od przyjęcia dokument JSON |
| `execution_policy` | Polityka rozstrzygnięta i zamrożona przy przyjęciu |
| `idempotency_key` | Klucz lub brak |
| `status` | `JobStatus` |
| `created_at` | UTC, czas trwałego utworzenia rekordu |
| `scheduled_at` | Początkowy termin, niezmienny po retry |
| `available_at` | UTC podczas `QUEUED` / `RETRY_SCHEDULED`; najbliższy termin możliwego przydziału. W `RUNNING` i stanach końcowych: brak |
| `first_started_at` | UTC lub brak; pierwsze zgłoszone faktyczne rozpoczęcie wykonywania |
| `finished_at` | UTC lub brak; moment zatwierdzenia **końcowego** stanu |
| `attempts_count` | Liczba utworzonych **przydziałów/prób**, nie potwierdzonych uruchomień funkcji |
| `current_attempt_id` | Aktualnie ważna próba lub brak |
| `result` | Opcjonalna otoczka `JobResult` z zatwierdzonym wynikiem |
| `revision` | Wersja stanu do kontroli nieaktualnych operacji |

Nie dublujemy per-attempt danych workerów, tracebacków, błędów i pełnej historii. Można wystawić `last_error` w **widoku odczytowym** opartym na najnowszej właściwej próbie. `result` ma trzy semantyczne przypadki: jeszcze brak wyniku; sukces i JSON `null`; sukces i wartość JSON różna od `null`. Rozróżnia je obecność `JobResult`, nie sama wartość. Wynik także jest walidowany zgodnie z kontraktem i ograniczony do **64 KiB po serializacji**.

Stan `Job` odczytany do Pythona jest niezmiennym snapshotem, nie bezpośrednim mutowalnym obiektem ORM. Zmiany inicjują operacje silnika, które sprawdzają przejścia i niezmienniki w PostgreSQL.

## 6. JobAttempt — pojedynczy przydział pracy

| Pole | Typ / znaczenie |
| --- | --- |
| `id` | Unikalny `AttemptId`; pełni także rolę tokenu przydziału (fencing token) |
| `job_id` | Powiązany `JobId` |
| `number` | 1..N w obrębie tego samego Job, bez duplikatów |
| `worker_id` | Instancja workera, której przydzielono próbę |
| `status` | `AttemptStatus` |
| `claimed_at` | UTC, przydzielenie przez bazę |
| `started_at` | UTC lub brak; worker potwierdził uruchomienie |
| `heartbeat_at` | UTC, ostatnie przyjęte odnowienie lease (początkowo chwila przydziału) |
| `lease_expires_at` | UTC, aktualna granica ważności przydziału |
| `deadline_at` | UTC lub brak; granica dopuszczalnego wykonania wyznaczana po potwierdzeniu startu. Dla próby `CLAIMED`, która nigdy nie wystartowała: brak |
| `finished_at` | UTC lub brak; chwila zapisania końcowego statusu próby |
| `execution_duration_ms` | `int >= 0 | None`, czas wykonania zmierzony zegarem monotonicznym, zaokrąglony do milisekund; brak, gdy pomiar jest nieznany |
| `error` | `ErrorInfo | None`, z bezpieczną kategorią i komunikatem |

`ErrorInfo` zawiera kod błędu (enum biblioteki, np. `EXECUTION_ERROR`, `VALIDATION_ERROR`, `TIMEOUT`, `LEASE_LOST`), bezpieczny komunikat `str` i opcjonalną nazwę wyjątku `str | None`. Nie zapisujemy surowych wyjątków, sekretów ani dowolnej zawartości pamięci procesu. Rozbudowany traceback należy do odpowiednio zabezpieczonych logów diagnostycznych.

Próba liczona jest **od przydzielenia**, nawet jeśli worker umrze przed uruchomieniem funkcji. Jeden Job może mieć wiele prób, ale tylko jeden **ważny** przydział jednocześnie. Wygasły przydział uznajemy za utracony, zanim wydamy nowy. `LOST` nie dowodzi, że nie wystąpił efekt uboczny w usłudze zewnętrznej; `finished_at` dla LOST oznacza moment wykrycia utraty, a nie moment zakończenia procesu.

Pomiary: całkowity czas Job to różnica `finished_at-created_at` (obejmuje oczekiwanie i retry); czas pojedynczej próby wyznacza lokalny zegar monotoniczny, gdy jest dostępny; czas oczekiwania liczony jest osobno. Nie nazywamy jednej niejednoznacznej wartości `duration`.

## 7. Statusy i maszyny stanów

`JobStatus`:

- `QUEUED`: oczekuje na pierwszy przydział, także przy przyszłym terminie.
- `RUNNING`: istnieje aktualnie przydzielona próba; nie gwarantuje to rzeczywistego wykonywania funkcji w tej sekundzie.
- `RETRY_SCHEDULED`: poprzednia próba zakończona; kolejna może zostać przydzielona po `available_at`.
- `SUCCEEDED`: wynik zwalidowany i zatwierdzony.
- `FAILED`: zlecenie zakończone bez sukcesu (błąd nieponawialny lub wyczerpany limit).
- `CANCELLED`: anulowane przed kolejnym przydziałem, bez anulowania aktywnego kodu.

Dozwolone przejścia `Job`:

```text
QUEUED           -> RUNNING | CANCELLED
RETRY_SCHEDULED  -> RUNNING | CANCELLED
RUNNING          -> SUCCEEDED | RETRY_SCHEDULED | FAILED
SUCCEEDED, FAILED, CANCELLED -> [brak przejść]
```

`AttemptStatus`: `CLAIMED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `LOST`.

```text
CLAIMED -> RUNNING | LOST
RUNNING -> SUCCEEDED | FAILED | TIMED_OUT | LOST
SUCCEEDED, FAILED, TIMED_OUT, LOST -> [brak przejść]
```

**Status próby != status całego zlecenia.** Nieudana próba może prowadzić do `Job.RETRY_SCHEDULED` lub końcowego `Job.FAILED`. Wygaśnięcie lease zamyka próbę jako LOST; jeżeli timeout został wiarygodnie wykryty przez silnik, może zostać oznaczony jako TIMED_OUT. Nie wyciągamy wniosków o tym, co stało się z zewnętrznym efektem ubocznym.

Stany końcowe Job są nieodwracalne. **Ręczny retry** po stanie końcowym tworzy nowy Job (nowe ID i nowe warunki idempotencji); nie zeruje historii poprzednika. Powiązanie z poprzednikiem może być dodane jako osobne metadane administracyjne w kolejnym etapie.

## 8. Niezmienniki bazy i granice atomowości

- W jednym atomowym przydziale: utworzenie `JobAttempt`, unikalny numer próby, zwiększenie `attempts_count`, ustawienie `current_attempt_id`, `Job.RUNNING` i zapis niezbędnej historii zdarzeń.
- `execution_policy.max_attempts >= 1` oraz dodatnie, skończone przedziały timeoutu i retry (w Pythonie `timedelta`). `attempts_count <= max_attempts`; przy wyczerpaniu limitu oraz błędzie nieponawialnym nie tworzymy nowej próby.
- `current_attempt_id` wskazuje bieżącą próbę tylko przy `Job.RUNNING`; po zamknięciu próby musi być wyczyszczone. Wymagamy unikalności `(job_id, number)` i kontroli jednego aktywnego przydziału.
- W jednej transakcji sukcesu: sprawdzenie ważności przydziału i jego tokenu, końcowy stan próby, walidowany/zapisany wynik i `Job.SUCCEEDED` z `finished_at`. Brak zatwierdzonego wyniku = brak sukcesu.
- W jednej transakcji błędu: zamknięcie próby oraz `RETRY_SCHEDULED` z terminem kolejnej próby albo `FAILED` z `finished_at`. Licznik zmienia się **przy claim**, nie przy błędzie.
- `QUEUED`/`RETRY_SCHEDULED` nie mogą mieć aktywnego przydziału. `SUCCEEDED` ma `JobResult`; `FAILED` i `CANCELLED` go nie mają. `finished_at` jest obecny tylko dla końcowych stanów.
- `scheduled_at` przy braku jawnego `not_before` równa się chwili przyjęcia zlecenia, nie zmienia się po ponowieniu. `available_at` jest **zawsze określony** w `QUEUED` i `RETRY_SCHEDULED` (dla nowego Job co najmniej `scheduled_at`), a w `RUNNING` i stanach końcowych ma wartość brak.
- Heartbeat jest przyjmowany tylko dla ważnego tokenu i przydziału; **nie przedłuża `deadline_at`**, który powstaje po potwierdzeniu rozpoczęcia wykonania. Dla `CLAIMED` bez potwierdzonego startu stosujemy wygaszenie lease i `LOST`, nie fikcyjny pomiar wykonania. Utrata przydziału i retry używają zegara PostgreSQL do decyzji sterujących, nie niespójnych zegarów workerów.
- Spóźniony worker nie może nadpisać wyniku lub stanu nowszej próby. To nie zabezpiecza samoistnie operacji w obcej bazie ani plików; zewnętrzne wykonanie wymaga własnej idempotencji/fencing.

Blokady i transakcje służą do przydzielania i zapisywania stanów, a **nie** do trzymania transakcji przez pełny czas wywołania funkcji. Przy wielu workerach rozważamy `SELECT ... FOR UPDATE SKIP LOCKED`, indeksy gotowości do wykonania i krótkie atomowe operacje. Migracje schematu są jawne, niezależne od importu biblioteki.

## 9. Błędy, bezpieczeństwo i ograniczenia wykonawców

- Podczas **przyjmowania** zlecenia nieznany `TaskRef` (nazwa/wersja) lub niezarejestrowana kolejka powodują błąd walidacji. Jeśli zadanie zostało prawidłowo przyjęte, ale po aktualizacji żaden worker nie obsługuje już jego wersji, pozostaje w stanie oczekiwania i jest raportowane operacyjnie. Nigdy nie importujemy i nie wykonujemy arbitralnego kodu z payloadu.
- Błędny JSON, rozmiar, niezgodna walidacja, nieaktualny token przydziału oraz konflikt klucza idempotencji mają jawne, typowane kategorie błędów; nie są zamieniane na fałszywy sukces.
- Przy zewnętrznym API worker może zlecić pracę i utracić potwierdzenie. Ponowienie może zlecić ją drugi raz; adapter musi korzystać z identyfikatora korelacyjnego/idempotencji. Ogólny adapter HTTP nie przyjmuje bez kontroli dowolnych wewnętrznych adresów URL z payloadu (ochrona przed SSRF).
- W dużych zadaniach payload/result przechowują referencje do plików, w tym wersję obiektu lub checksum. Uprawnienia tymczasowe generowane są podczas wykonania, nie zapisywane jako długotrwałe dane zadania. Osierocone pliki po awariach sprząta osobny mechanizm; brak transakcji obejmującej jednocześnie PostgreSQL i obiekt storage.
- Nie logujemy bez kontroli pełnego payloadu, tokenów ani sekretów. Trwała historia stanu/attemptów jest oddzielna od diagnostycznego `logging` oraz metryk.
- Termin wykonania w `asyncio` wymaga współpracującej funkcji. Biblioteka w pierwszej wersji nie obiecuje twardego zabijania dowolnego kodu ani cofania jego skutków.

## 10. Co wchodzi do pierwszego wdrożenia, a co nie?

**Kontrakt projektowy dla pierwszego rdzenia** obejmuje trzy modele, walidowane małe wejście/wyjście, enuma stanów, trwały zapis w PostgreSQL, przydział i zapis prób, podstawowe retry, lease i ochronę przed starymi workerami, historię zdarzeń, testy awarii oraz możliwość obserwacji przez SDK. Implementujemy go **małymi, osobno testowanymi krokami**, zgodnie z `docs/learning/00-course.md`.

**Poza pierwszym rdzeniem**: pełny DAG/zależności i cron, wykonywanie wielogodzinnych operacji zewnętrznych przez callback/polling, masowe przetwarzanie plików, własny format transportu, gRPC, dashboard, zarządzanie wieloma organizacjami, autoskalowanie GCP, gwarancje exactly-once i dowolny kod dostarczany przez REST.

Adapter FastAPI/Gateway oraz pierwsze wdrożenie GCP użyją **tego samego** rdzenia, gdy podstawowy przepływ enqueue/claim/execute/result już działa. Rdzeń pozostaje instalowalny bez uruchamiania serwera API. Cloud Run/Cloud SQL to przykład wdrożenia, nie warunek instalacji biblioteki. Nie tworzymy płatnych zasobów bez oddzielnego ustalenia kosztów i sposobu ich usunięcia.

## 11. Kryteria akceptacji kontraktu i przyszłej implementacji

1. Użytkownik może zarejestrować różne schematy payloadu/wyniku i enuma kolejek; nieznana kolejka, format i rozmiar są jawnie odrzucane.
2. Dwa identyczne żądania z tym samym kluczem tworzą najwyżej jeden trwały Job; konflikt treści nie tworzy drugiego.
3. Równoległe workery nie otrzymują dwóch **ważnych** przydziałów tego samego Job.
4. Po awarii workera zadanie ma nową próbę tylko wtedy, gdy polityka na to pozwala; liczba prób liczy także nieuruchomione przydziały.
5. Zapis wyniku przez nieaktualny token nie nadpisuje nowszej próby.
6. Błąd pojedynczej próby nie tworzy automatycznie końcowego `Job.FAILED`, gdy retry jest dopuszczone.
7. `SUCCEEDED` z JSON `null` różni się od zadania bez wyniku; błędny wynik nie może być zatwierdzony jako sukces.
8. Wartości `scheduled_at`, `available_at`, `first_started_at` i `finished_at` zachowują odrębne znaczenie; brak potwierdzenia startu lub pomiaru czasu nie jest fałszowany.
9. Niedozwolone zmiany stanów i ręczny restart terminalnego Job są odrzucane; nowe zlecenie ma nową tożsamość.
10. Pakiet nie wymaga FastAPI; testy na PostgreSQL obejmują prawdziwe transakcje, współbieżność i wstrzyknięte awarie. Dokumentacja jasno podaje ograniczenia semantyki at-least-once.

## 12. Repozytorium i następny krok

Zastane lokalne `tests/test_job.py` (testy uproszczonego `Job(task_name, queue: str)`) i pusty, nieśledzony `job.py` są **wcześniejszym eksperymentem**. Nie są zatwierdzonym kontraktem, nie modyfikujemy ich w kroku dokumentacyjnym ani nie dodajemy do commita. Po przeglądzie specyfikacji należy przygotować mały plan zmiany tych testów **z udziałem użytkowniczki**.

Następny krok po zatwierdzeniu tego pliku: oddzielny plan implementacji, począwszy od testów typowanych `JobRequest`, `TaskRef`, enumów i walidacji bez bazy. Dopiero potem stany Job, JobAttempt, PostgreSQL i worker. Każda ukończona zmiana ma własny test, mały commit i push na gałąź roboczą.

## Źródła techniczne

- Python `enum`: https://docs.python.org/3.13/library/enum.html
- Python `typing`: https://docs.python.org/3.13/library/typing.html
- PostgreSQL row locking: https://www.postgresql.org/docs/17/sql-select.html
- PostgreSQL JSON/JSONB: https://www.postgresql.org/docs/17/datatype-json.html
- PostgreSQL time functions: https://www.postgresql.org/docs/17/functions-datetime.html
- Python monotonic clock: https://docs.python.org/3.13/library/time.html
- Celery task semantics: https://docs.celeryq.dev/en/stable/userguide/tasks.html
