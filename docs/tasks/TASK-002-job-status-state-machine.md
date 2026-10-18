# TASK-002 — JobStatus State Machine

**Projekt:** `pg-task-engine`
**Gałąź robocza:** `dawid268/feat/job-status-state-machine` (od `dev`)
**Status:** TODO — zadanie do samodzielnej implementacji
**Zakres:** kontrakt stanów `Job`, testy, aktualizacja specyfikacji i README

## Cel biznesowy

Każde zlecenie w trwałej kolejce musi przechodzić przez dozwolone stany w
przewidywalny sposób. Mechanizm ma umożliwiać planowane ponowienie pracy,
anulowanie i jednoznaczne zakończenie zadania, ale nie może „wskrzeszać”
zakończonego zlecenia ani traktować błędu jednej próby jako automatycznego
zakończenia całego `Job`.

Zakończ i przetestuj `JobStatus` oraz `can_transition(current, target)`.
To ma być **czysta logika domenowa**, bez PostgreSQL, workerów i FastAPI.

## Punkt startowy

- `src/pg_task_engine/job_status.py` zawiera sześć wartości `JobStatus` i
  wstępną funkcję `can_transition`.
- `tests/test_job_transitions.py` ma tylko dwa testy.
- `docs/superpowers/specs/2026-10-11-job-lifecycle-design.md`, sekcja 7,
  opisuje pierwotną macierz. Kod jest z nią niezgodny w kwestii retry.
- Później uzgodniono także **kontrolowane anulowanie aktywnego zadania**.
  Uwzględnij tę decyzję w macierzy i zsynchronizuj dokumentację.

## Wymagany kontrakt przejść

| Obecny stan | Dozwolone następne stany |
| --- | --- |
| `QUEUED` | `RUNNING`, `CANCELLED` |
| `RUNNING` | `SUCCEEDED`, `RETRY_SCHEDULED`, `FAILED`, warunkowo `CANCELLED` |
| `RETRY_SCHEDULED` | `RUNNING`, `CANCELLED` |
| `SUCCEEDED` | brak |
| `FAILED` | brak |
| `CANCELLED` | brak |

**Semantyka retry:**

- Po nieudanej próbie, jeśli polityka retry pozwala kontynuować, aktualny
  `Job` może przejść z `RUNNING` do `RETRY_SCHEDULED`.
- `FAILED` oznacza **ostateczną porażkę Job**, a nie pojedynczej próby.
- `FAILED → RETRY_SCHEDULED`, `FAILED → RUNNING` i `FAILED → CANCELLED`
  są niedozwolone.
- Ręczne ponowienie zadania zakończonego wymaga **nowego Job z nowym ID**.

**Semantyka anulowania aktywnego zadania:**

- `request_cancel` nie jest automatycznie przejściem statusu. Aktywny Job
  pozostaje `RUNNING`, dopóki wykonawca nie potwierdzi bezpiecznego
  zakończenia pracy i silnik nie zatwierdzi anulowania.
- `RUNNING → CANCELLED` jest *możliwą krawędzią grafu*, ale tylko po takim
  potwierdzeniu oraz sprawdzeniu ważnej próby/lease przez przyszły silnik.
- `can_transition` widzi wyłącznie dwa statusy, **nie** dowodzi, że worker
  faktycznie się zatrzymał. Dlatego dla tej pary zwraca `True` jako
  informację o dopuszczalności **warunkowej**, nie jako upoważnienie do zapisu.
- Anulowanie nie kasuje ostatniego zatwierdzonego `JobProgress`; np.
  `4000/10000` pozostaje obserwowalne. `JobProgress` nie jest checkpointem
  pozwalającym automatycznie wznowić skutki biznesowe.
- Nie dodawaj teraz `CANCELLING`, `PAUSED` ani metody zatrzymywania workera;
  zostaną rozważone z warstwą silnika. Pauza kolejki to odrębny problem.

## Implementacja

1. Zachowaj sześć istniejących wartości i tekstowy kontrakt `StrEnum`
   (`queued`, `running`, `succeeded`, `failed`, `retry_scheduled`,
   `cancelled`). Nie zmieniaj ich nazw ani wartości.
2. Popraw `can_transition(current: JobStatus, target: JobStatus) -> bool`
   zgodnie z macierzą. Zwracaj `False` dla niedozwolonego przejścia między
   **poprawnymi** stanami, również dla przejścia stanu do samego siebie.
3. Odrzucaj niepoprawnie otypowane argumenty poprzez `TypeError`
   (także surowe stringi typu `"queued"`, choć `StrEnum` porównuje się
   do `str`). Nie traktuj takich wartości jak poprawnych statusów.
4. Preferuj jedną deklaratywną, niezmienną mapę dozwolonych przejść, bez
   przebudowywania jej podczas każdego wywołania. Zachowaj prosty publiczny
   interfejs, bez zbędnych abstrakcji i zależności runtime.
5. Zaktualizuj sekcję 7 specyfikacji cyklu życia oraz krótko opisz publiczny
   kontrakt `JobStatus` w README. Wyraźnie odróżnij status `Job` od statusu
   `JobAttempt` i działanie helpera od atomowego zapisu stanu.

## Testy — obowiązkowo

Rozszerz `tests/test_job_transitions.py`:

- Przetestuj wszystkie **36 par** sześciu poprawnych statusów. Macierz
  oczekiwanych wyników w teście powinna być jawna i niezależna od
  implementacyjnej mapy przejść (unikaj testowania funkcji nią samą).
- Uwzględnij `RUNNING → RETRY_SCHEDULED` (True),
  `RUNNING → CANCELLED` (True jako krawędź warunkowa),
  `FAILED → RETRY_SCHEDULED` (False) i `FAILED → CANCELLED` (False).
- Sprawdź brak wyjść z `SUCCEEDED`, `FAILED` i `CANCELLED` oraz
  odrzucenie przejść do tego samego stanu.
- Dodaj testy odrzucające surowe napisy, `None` i inne niepoprawne typy
  zarówno w `current`, jak i `target`. Do testowania celowo błędnych
  adnotacji możesz użyć `typing.cast`.
- Sprawdź stabilność tekstowych wartości enuma i brak duplikatów.
- Przetestuj semantykę anulowania i retry na poziomie **macierzy stanów**;
  nie udawaj w unit testach, że istnieje działający worker albo persystencja.

## Definition of Done

- Wszystkie przejścia odpowiadają tabeli i są sprawdzone testami.
- `can_transition` jest deterministyczną, czystą funkcją bez I/O.
- Niepoprawne typy nie są po cichu akceptowane.
- Specyfikacja i README jednoznacznie opisują retry, terminalność i
  kontrolowane anulowanie; nie ma sprzeczności z implementacją.
- Istniejące testy `JobProgress`, `TaskRef` i API nadal przechodzą.
- Ruff, formatowanie, mypy strict i pakowanie biblioteki przechodzą.
- Do repo nie dochodzą sterowniki bazy, modele `JobAttempt`, workery,
  harmonogramy ani endpointy HTTP.
- Po code review: jeden niewielki commit implementacji na feature,
  push, następnie merge do `dev` **po pozytywnej weryfikacji**.

## Weryfikacja

```bash
uv run --locked pytest tests/test_job_transitions.py -v
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src app tests run.py
uv build
```

## Tryb nauki

Zadanie wykonujesz samodzielnie. Po napisaniu całości zgłoś:
`review TASK-002`. Agent zrobi szczegółowe code review, uruchomi testy
i wskaże błędy bez nadpisywania Twoich zmian. Jeśli zadanie okaże się za
duże, zgłoś `podziel TASK-002`, a rozbijemy je na mniejsze ćwiczenia.
