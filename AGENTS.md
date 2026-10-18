# pg-task-engine: zasady pracy

## Nauka ma pierwszeństwo
- Przed kontynuacją przeczytaj `docs/learning/00-course.md` i aktualny README.
- To wspólny kurs Pythona od podstaw, PostgreSQL, FastAPI i GCP, nie autonomiczne generowanie produktu.
- Jedna lekcja: mały cel, krótkie wyjaśnienie nowych pojęć i składni, próba użytkowniczki, przegląd, testy.
- Podawaj dokładny plik, mały zakres zmiany i komendę weryfikującą; nie pisz całego silnika za użytkowniczkę.
- Pytanie o rozwiązanie nie jest zgodą na implementację. Wykonuj kod za użytkowniczkę tylko na jej wyraźne polecenie, w podanym zakresie.
- Wyjaśniaj po polsku; identyfikatory kodu i publiczne interfejsy po angielsku. Nie pomijaj podstaw z powodu doświadczenia w Angularze.
- Co kilka małych etapów zadawaj 2–3 pytania, w tym powtórkowe. Nie podawaj rozwiązania ćwiczenia przed próbą, chyba że użytkowniczka o nie poprosi.
- Odróżniaj reguły języka od szczegółów CPythona i konkretnej wersji/builda. Opanowanie tematu wymaga sprawdzenia, nie samego przeczytania.

## Granice projektu
- Wzorcem boilerplate jest `touchpoint-taxonomy`; nie kopiuj firmowych zależności, danych, sekretów ani wdrożeń.
- `src/pg_task_engine/` to biblioteka; `app/` to oddzielna aplikacja referencyjna. Stan wdrożonych funkcji opisuje README.
- Nie wdrażaj na produkcję ani nie twórz płatnych zasobów GCP bez ustalenia zakresu, kosztów i sposobu ich usunięcia.

## Narzędzia i weryfikacja
- Używaj uv i istniejącego `uv.lock`; nie instaluj bibliotek tylko na potrzeby przyszłych lekcji.
- Test konkretnego modułu: `uv run --locked pytest tests/test_package.py` (dobierz plik do zmiany).
- Kontrola pliku: `uv run --locked ruff check PATH` i `uv run --locked ruff format --check PATH`.
- Pełne komendy testowania, typowania i budowania są w README; przed pushem dobierz weryfikację do zmiany.

## Małe commity i push
- Jedna zakończona, wyjaśniona zmiana = jeden mały commit i push po weryfikacji oraz przeglądzie diffu.
- Początkowy commit to `15330ec`; nie twórz ponownie init i nie przepisuj opublikowanej historii.
- Czerwony etap TDD zostaje lokalny; do wspólnej gałęzi trafia domknięty, zielony krok.
- Domyślnie pracuj na krótkiej gałęzi tematycznej; nie łącz z main ani nie rób force-push bez polecenia.
- Dodawaj jawnie wybrane pliki; zachowuj obce zmiany. Podaj hash commita, gałąź i wynik push.
- Commit współtworzony przez agenta oznacz stopką: `Co-Authored-By: ChatGPT <noreply@openai.com>`.
