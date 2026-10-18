# TASK-003 — JobRequest: typowane zgłoszenie zadania i walidacja danych

**Typ:** Story / Backend · Python 3.13
**Priorytet:** High
**Status:** To Do
**Assignee:** Dawid268
**Gałąź robocza:** `dawid268/feat/job-request-contract`
**Gałąź docelowa:** `dev`
**Obszar:** Publiczny kontrakt SDK; bez PostgreSQL i workera

## User story / problem biznesowy

Jako aplikacja korzystająca z `pg-task-engine` chcę utworzyć
`JobRequest` z typem zadania, kolejką, argumentami, opcjonalnym terminem
i polityką wykonania, żeby silnik mógł później bezpiecznie przyjąć
jednoznaczne zlecenie. Nie chcę dopuścić niepoprawnego JSON, nieznanej
postaci identyfikatora kolejki ani arbitralnych obiektów Pythona.

`JobRequest` opisuje **intencję** aplikacji. Nie jest jeszcze zapisanym
`Job`, nie posiada `JobId`, statusu ani historii prób. Trwałość nastąpi
dopiero po commit transakcji PostgreSQL w kolejnym etapie.

## Przykład użycia (docelowe zachowanie API)

```python
from enum import StrEnum
from pg_task_engine.task_ref import TaskRef
from pg_task_engine.job_request import JobRequest


class AppQueue(StrEnum):
    DEFAULT = "default"
    EMAILS = "emails"


request = JobRequest(
    task=TaskRef(name="send_email", version=1),
    queue=AppQueue.EMAILS,
    payload={"recipient_id": 42, "dry_run": False},
    not_before=None,
    execution_policy=None,
    idempotency_key="email:42:welcome",
)
```

Przykład jest kontraktem zachowania, nie gotową implementacją.
Nazwy pomocniczych typów i modułów mogą zostać doprecyzowane w kodzie.

## Zakres implementacji

### A. `JobRequest` oraz typy domenowe

- Dodaj `src/pg_task_engine/job_request.py`.
- Pola: `task`, `queue`, `payload`, `not_before`,
  `execution_policy`, `idempotency_key`.
- `task` musi być instancją istniejącego `TaskRef`.
  Rejestrację definicji zadania sprawdzi później silnik.
- `queue` musi być członkiem `StrEnum` zdefiniowanego przez aplikację.
  Odrzuć surowe stringi (także `"emails"`), `None`, dowolny inny
  enum i inne typy. Nie twórz globalnego enuma nazw kolejek w bibliotece.
  Sprawdzanie, czy dana kolejka należy do zbioru **zarejestrowanych**
  kolejek instalacji, zostaw dla przyszłej konfiguracji silnika.
- Zaprojektuj jawne adnotacje typów bez `Any` w publicznym API.
  Rozważ generyki dla enuma aplikacji i typu danych zadania, tak aby
  mypy pomagał użytkownikowi SDK, a runtime nadal odrzucał złe typy.
- Nie przyjmuj od aplikacji pól `status`, `job_id`, `worker_id`,
  `attempts_count`, `result` ani `finished_at`.

### B. Walidacja argumentów JSON

- `payload` musi być **obiektem JSON**: mapą z kluczami `str`,
  domyślnie pustą, nigdy `None`, listą ani wartością skalarną na
  najwyższym poziomie.
- Wartości mogą zawierać: `None`, `bool`, `int`, skończony `float`,
  `str`, listy i zagnieżdżone obiekty o kluczach `str`.
- Odrzucaj: `NaN`, `Infinity`, `-Infinity`, zagnieżdżone klucze niebędące
  `str`, `set`, `tuple`, `datetime`, obiekty własnych klas,
  niepoprawne Unicode, cykle referencji oraz błędy serializacji.
- Maksymalny rozmiar payloadu to **64 KiB (= 65536 bajtów) po
  serializacji do UTF-8**, nie liczba znaków ani `sys.getsizeof`.
  Wybierz i opisz deterministyczny format serializacji dla tego pomiaru.
- Zapewnij, aby przyjęta, zwalidowana reprezentacja nie zmieniała się
  wskutek późniejszej mutacji oryginalnego `dict` lub jego zagnieżdżeń.
  Nie udawaj, że `@dataclass(frozen=True)` automatycznie zamraża słowniki.
- Bez `pickle`, dynamicznych importów i zależności FastAPI/Pydantic
  w instalowalnej bibliotece.

### C. Czas zgłoszenia i klucz idempotencji

- `not_before: datetime | None`: `None` oznacza „możliwie szybko”.
  Jeśli podano datę, musi mieć świadomą strefę i offset UTC równy zero;
  odrzuć `datetime` naive, nie-UTC oraz nie-`datetime`.
  Nie przeliczaj dat automatycznie i nie odrzucaj terminu w przeszłości.
- `idempotency_key: str | None`: brak jest poprawny; podany klucz musi
  być niepusty, nie składać się wyłącznie z białych znaków i mieć
  maksymalnie **128 znaków**. Nie modyfikuj klucza po cichu przez `strip`.
- Faktyczna deduplikacja, porównanie kanonicznej intencji oraz konflikty
  w PostgreSQL **nie należą jeszcze do tego zadania**.

### D. Minimalny `ExecutionPolicy`

- Zdefiniuj mały, typowany model polityki wykonania w rdzeniu, bez
  wbudowywania algorytmu retry. Przyjmij opcjonalne nadpisania:
  `max_attempts: int | None`, `timeout: timedelta | None`,
  `retry_delay: timedelta | None`.
- `max_attempts` musi być `int >= 1` (odrzucaj `bool`), a podane
  `timeout` i `retry_delay` muszą być dodatnimi `timedelta`.
- `None` dla polityki lub jej pól pozostawia wybór domyślnych wartości
  na etap konfiguracji silnika. Nie wymyślaj globalnych domyślnych czasów.
- Waliduj model i odrzucaj obiekty o niezgodnym typie polityki.

### E. Błędy, testy, dokumentacja

- Dla błędów wejścia preferuj przewidywalne wyjątki typu `TypeError`
  i `ValueError`. Jeżeli dodajesz wyjątki domenowe, udostępnij stabilne
  kody analogicznie do `JobProgressErrorCode`. Nie opieraj testów tylko
  na treści komunikatu.
- Dodaj `tests/test_job_request.py`, a jeśli wyodrębnisz politykę
  lub walidator JSON — osobne testy tych elementów.
- Testuj przypadki poprawne, błędne typy, wartości graniczne,
  samą granicę 65536 bajtów i przekroczenie o jeden bajt, Unicode,
  wielopoziomową mutację wejścia, offset UTC±, zachowanie klucza
  idempotencji i błędne `ExecutionPolicy`.
- Dodaj w README krótki przykład tworzenia `JobRequest` oraz opis
  ograniczeń kontraktu. Dokument architektoniczny
  `docs/superpowers/specs/2026-10-11-job-lifecycle-design.md` jest
  punktem odniesienia; jeśli wybierzesz inne szczegóły API, zapisz i
  uzasadnij je w dokumentacji.

## Definition of Done

- [ ] `JobRequest` z typowanymi polami i poprawną kontrolą typu kolejki.
- [ ] JSON payload walidowany rekurencyjnie, kopiowany i limitowany do 64 KiB.
- [ ] `not_before` i `idempotency_key` spełniają powyższe ograniczenia.
- [ ] Podstawowy `ExecutionPolicy` ma testowane niezmienniki.
- [ ] Testy obejmują wszystkie wymienione przypadki brzegowe i wyjątki.
- [ ] README wyjaśnia model, a biblioteka nie zależy od FastAPI/Pydantic.
- [ ] Cały test suite, Ruff, formatowanie, mypy strict i `uv build` przechodzą.
- [ ] Po review: commit, push, merge **feature → dev**, aktualizacja Issue.

## Poza zakresem

Nie implementujemy teraz `Job`, `JobAttempt`, kolejki w PostgreSQL,
rejestru wykonawców, deduplikacji w bazie, heartbeat, workera, retry
schedulera, API HTTP ani obsługi GCP. Do tego powstaną kolejne zadania.

## Testowanie

```bash
uv run --locked pytest tests/test_job_request.py -v
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src app tests run.py
uv build
```

## Materiały

- [Kontrakt JobRequest / Job / JobAttempt](https://github.com/Dawid268/pg-task-engine/blob/dev/docs/superpowers/specs/2026-10-11-job-lifecycle-design.md)
- [Gałąź robocza](https://github.com/Dawid268/pg-task-engine/tree/dawid268/feat/job-request-contract)
- [Python typing](https://docs.python.org/3.13/library/typing.html)
- [Python json](https://docs.python.org/3.13/library/json.html)

**Tryb pracy:** jedno większe zadanie. Po wykonaniu zgłoś
`review TASK-003`; gdy zechcesz je rozbić, napisz `podziel TASK-003`.
