# Lekcja 1: zakładamy bibliotekę, nie aplikację serwerową

> Zapis pierwszego, historycznego kroku. Właściwym źródłem boilerplate jest teraz `touchpoint-taxonomy`; aktualne zmiany i komendy opisuje `02-touchpoint-boilerplate.md`. Dodano przykładowe API, ale silnik kolejki nadal nie jest zaimplementowany.

## Cel obecnego kroku

Mamy instalowalny pakiet `pg-task-engine`, importowany w Pythonie jako `pg_task_engine`. Nie mamy jeszcze silnika zadań. Wersja `0.0.1` oznacza początek projektu, nie gotowość produkcyjną.

Robocza nazwa i lokalny katalog nie rezerwują nazwy na PyPI ani GitHubie. Nie utworzono zdalnego repozytorium i niczego nie opublikowano. Inicjalizacja historii Git i wybór licencji należą do przygotowania repozytorium do publikacji; w tym kroku powstały tylko lokalne pliki projektu.

## Dlaczego nie kopiujemy całego komino-api?

Komino jest aplikacją. Ten projekt ma być biblioteką, z której korzystają inne aplikacje. Dlatego import pakietu nie uruchamia serwera, nie otwiera połączenia z bazą i nie wymaga FastAPI. Integrację HTTP dodamy w osobnym module, gdy będzie już co udostępnić.

## Pliki i ich zadania

- `pyproject.toml`: nazwa i wersja dystrybucji, wymagany Python, konfiguracja budowania oraz narzędzi developerskich.
- `.python-version`: uv wybiera dla tego projektu Pythona 3.13; systemowego Pythona nie zmieniamy.
- `uv.lock`: konkretne wersje rozwiązanego zestawu zależności; nie edytujemy go ręcznie.
- `.venv/`: lokalne środowisko projektu; nie trafia do Git.
- `src/pg_task_engine/__init__.py`: początek publicznego pakietu. Na razie eksportuje tylko `__version__`.
- `src/pg_task_engine/py.typed`: pusty znacznik informujący narzędzia typujące, że dystrybucja zawiera informacje o typach.
- `tests/test_package.py`: sprawdzenie wersji, znacznika typowania i aktualnego braku zależności uruchomieniowych.
- `.gitignore`: wykluczenie środowisk, artefaktów, cache i typowych plików z sekretami. Nie zastępuje przeglądu bezpieczeństwa przed publikacją.

## Narzędzia

`uv` zarządza środowiskiem i zależnościami oraz uruchamia polecenia w środowisku projektu. `uv_build` jest backendem budowania: tworzy dystrybucję źródłową i wheel, czyli paczkę do instalacji. Używamy rodziny wersji zgodnej z zainstalowanym uv 0.10.9, a nie zmieniamy globalnej instalacji.

`pytest` wykonuje testy. `pytest-cov` będzie przydatny przy mierzeniu pokrycia rzeczywistej logiki; pokrycie obecnego jednoelementowego pakietu nie jest miarą jakości przyszłego silnika.

Ruff analizuje kod i sprawdza formatowanie. mypy działa w trybie `strict`, żeby błędy typów wychodziły od początku. Zależności te są w grupie `dev`, a nie w wymaganiach użytkownika biblioteki.

## Polecenia do samodzielnego sprawdzenia

```bash
cd /home/dawid/Projekty/pg-task-engine
uv sync --locked
uv run --locked python --version
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests
uv build
uv run --locked python -c 'import pg_task_engine; print(pg_task_engine.__version__)'
```

Po `uv build` pliki są w `dist/`. Nie wysyłamy ich jeszcze na PyPI.

## Pierwsze zadanie z kodem domenowym — jeszcze niewykonane

Wspólnie zaprojektujemy `Job` oraz sposób walidacji nazwy typu zadania i argumentów. Zaczniemy od zwykłego kodu Pythona i testów, bez FastAPI i bez bazy. Potem dodamy stany i PostgreSQL.

Do omówienia przed tym krokiem: różnica między definicją funkcji zadania a konkretnym zleceniem oraz między zleceniem a próbą jego wykonania. Nie traktujemy ponowienia próby jako nowego, niezależnego zadania.

Dwa pytania kontrolne:

1. Dlaczego kod biblioteki jest w `src/`, a nie bezpośrednio obok `pyproject.toml`?
2. Dlaczego pytest jest w grupie developerskiej, a nie w `project.dependencies`?

## Zweryfikowane ograniczenia obecnego kroku

Testy obejmują wyłącznie pakowanie. Nie utworzono tabel ani połączenia z PostgreSQL, nie ma workerów i endpointów, nie uruchomiono zasobów GCP. Nie należy interpretować zielonych testów jako gotowości kolejki.

## Dokumentacja źródłowa

- https://docs.astral.sh/uv/concepts/projects/init/#libraries
- https://docs.astral.sh/uv/configuration/build-backend/
