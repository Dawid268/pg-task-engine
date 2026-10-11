# Właściwy wzorzec: touchpoint-taxonomy

Źródłem boilerplate jest `/home/dawid/Projekty/touchpoint-taxonomy`. Wcześniejszy wybór `komino-api` został skorygowany zgodnie z poleceniem użytkowniczki. Repozytorium źródłowe jest tylko odczytywane; zmiany dotyczą `pg-task-engine`.

## Co zachowujemy ze wzorca

- `app/app.py`: składanie aplikacji przez `app_factory`, `setup_routing` i `setup_middlewares`.
- `app/main.py`: punkt wejścia ASGI.
- `app/settings.py`: klasa ustawień i `get_settings`, z wyborem pliku przez `SETTINGS_ENV`.
- `app/modules/base/api.py`: router diagnostyczny i endpoint `/version`.
- `run.py`: uruchomienie Uvicorna; lokalnie nasz port to 9031.
- Testy asynchroniczne przez HTTPX `ASGITransport` i `LifespanManager`.
- Rodziny reguł Ruff, szerokość 100 znaków, Python 3.13, narzędzia pre-commit.
- Wieloetapowy Dockerfile z uv i plikiem lock oraz lokalny Docker Compose.

Kod szkieletu został dostosowany do nowego projektu, a nie skopiowany razem z domeną taxonomii. Własne modele, migracje, seedy i konfiguracja chmurowa źródła nie należą do naszej biblioteki.

## Dlaczego nadal mamy src/ i app/?

`src/pg_task_engine/` to biblioteka instalowana z wheel. `app/` to przykładowa aplikacja używająca biblioteki. Wzorzec pokazuje budowę FastAPI, ale nie zmienia naszego celu w samodzielną aplikację wymagającą serwera HTTP do każdego użycia kolejki.

`dependency-groups.api` zawiera zależności przykładowego serwera. Grupa `dev` obejmuje `api` i narzędzia testowe. Żadna z tych grup nie trafia do zależności uruchomieniowych publikowanego wheel. Potwierdzamy to nadal testem pakowania.

## Celowe różnice

Nie przenosimy `mxmz-*`, uwierzytelniania firmowego, Datadog ani konfiguracji GitLab/GKE. Nic nie pobiera sekretów ze źródłowego projektu. Nie kopiujemy `.env`, `env_variables/`, stanów Terraform, historii Git ani firmowych adresów.

Źródło deklaruje Python 3.13, ale miało ustawienie mypy na 3.10. U nas oba narzędzia używają 3.13, a mypy pozostaje w trybie strict. Usunięte reguły ANN101/ANN102 nie są kopiowane. Reguły kolidujące z formatowaniem są pominięte; nie wyłączamy masowo kontroli typów i bezpieczeństwa.

Zamiast starego `tool.uv.dev-dependencies` używamy `dependency-groups`. Nie kopiujemy trybu pokrycia `gevent`, ponieważ obecne testy są oparte na asyncio. Hooki korzystają z tego samego lockfile co lokalne kontrole, bez drugiego zestawu wersji narzędzi.

Testy wzorca automatycznie tworzyły i usuwały bazę. Nasze testy nie łączą się z żadną bazą. PostgreSQL w Compose jest osobnym, opcjonalnym profilem i nie jest jeszcze używany przez API. SQLAlchemy, asyncpg i Alembic wprowadzimy wraz z pierwszym modelem i prawdziwym zapisem zadania.

`/health/live` oznacza tylko, że działa HTTP. Nie ma `/health/ready` ani fikcyjnego `/jobs`. Nie mamy jeszcze logiki kolejki ani uwierzytelnionego API zarządzającego zadaniami.

## Komendy

```bash
uv sync --locked
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src app tests run.py
uv run --locked pre-commit validate-config
uv run --locked python run.py
```

Nie publikujemy projektu i nie uruchamiamy GCP w tym kroku. Dalsza nauka nadal polega na wspólnym pisaniu małych fragmentów kodu: najpierw `Job` i walidacja, następnie baza i worker.

## Weryfikacja po adaptacji

- Pełny zestaw: 15 testów zaliczonych; Ruff lint/format i strict mypy bez błędów.
- Walidacja konfiguracji pre-commit, Docker Compose i zgodności uv.lock: poprawna. Hooki nie zostały zainstalowane w Git.
- Wheel i sdist budują się. Osobna instalacja wheel nie zawiera FastAPI ani pakietu `app`; 3 testy pakowania przechodzą także w izolacji.
- Obraz `pg-task-engine:boilerplate-check` został zbudowany. Rzeczywisty Uvicorn odpowiedział poprawnie na `/version`, `/health/live` i `/openapi.json` wewnątrz kontenera, jako użytkownik nieuprzywilejowany, z systemem plików tylko do odczytu i bez sieci zewnętrznej. Sprawdzono również niestandardowy `PORT`.
- Kontener testowy zakończono i usunięto. Nie uruchomiono bazy ani GCP. Profil PostgreSQL ma sprawdzoną konfigurację Compose, ale jego uruchomienie nie było testowane.
- Repozytorium źródłowe nie ma zmian śledzonych plików. Jego wcześniejsze nieśledzone katalogi pozostawiono bez zmian.

To weryfikacja boilerplate, nie działającego silnika zadań.

## Dokumentacja

- https://docs.astral.sh/uv/concepts/projects/dependencies/
- https://docs.astral.sh/ruff/formatter/
