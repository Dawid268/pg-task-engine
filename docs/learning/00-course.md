# Kurs: Python, backend i GCP przez pg-task-engine

Ustalenia z 11 października 2026 r. Ten dokument określa sposób dalszej pracy; nie jest deklaracją ukończenia kursu.

## Cel i punkt startowy

Budujemy własną bibliotekę trwałych kolejek w Pythonie i PostgreSQL, aplikację referencyjną FastAPI oraz wdrożenie GCP. Długofalowym celem jest samodzielność i poziom kompetencji senior Python/backend developer. Pierwsze ograniczone wydanie pozostaje celem na 1–2 miesiące, nie obietnicą zdobycia poziomu senior w tym terminie.

Zaczynamy od podstaw Pythona mimo doświadczenia użytkowniczki w innych technologiach. Nie utożsamiamy gotowego kodu wygenerowanego przez agenta z umiejętnościami użytkowniczki.

Wzorcem boilerplate jest `touchpoint-taxonomy`. Kod biblioteki pozostaje w `src/pg_task_engine/`, a `app/` jest aplikacją referencyjną. Aktualne funkcje opisuje README. Początkowy commit `15330ec` został opublikowany na main; nie tworzymy kolejnego init i nie zmieniamy jego historii.

## Rytm jednej lekcji

1. Jeden konkretny rezultat i najwyżej kilka nowych pojęć.
2. Skondensowane wyjaśnienie, zwykle 150–300 słów, mały przykład i jedna istotna pułapka. Dłuższy temat dzielimy na lekcje.
3. Dokładny plik, miejsce zmiany, oczekiwane zachowanie i komenda sprawdzająca. Przy pierwszym wystąpieniu objaśniamy składnię, np. `def`, `self`, `:`, `->`, dekorator, adnotację typu.
4. Użytkowniczka przewiduje wynik, pisze mały fragment lub test; agent czeka na próbę i pomaga w razie trudności. Pełne rozwiązanie podajemy na prośbę, nie od razu.
5. Przegląd z wyjaśnieniem przyczyny błędów, uruchomienie testów, krótkie podsumowanie.
6. Po ukończeniu małego kroku: przegląd diffu, commit i push. Etap dokumentacyjny nie wymaga fikcyjnego testu zachowania.

Agent może wykonywać wyraźnie zlecone czynności techniczne, np. konfigurację, testy lub konkretną implementację. Nie rozszerza takiego polecenia na budowę kolejnych modułów. Analogie do TypeScriptu pomagają, ale nie zastępują objaśnienia modelu Pythona.

## Commity

Jedna logiczna zmiana na commit: model i jego testy, osobna walidacja, osobna migracja, osobna konfiguracja wdrożenia. Nie commit po każdym zapisie pliku ani duży pakiet niepowiązanych funkcji.

Przykładowe tematy przyszłych commitów: `feat: Add validated job name`, `test: Cover invalid job payloads`, `ci: Add Python checks`. To propozycje, nie lista wykonanych funkcji. Czerwony etap TDD pozostaje lokalny, a zielony etap trafia do przeglądu i push.

Domyślnie używamy krótkich gałęzi tematycznych. Push nie oznacza automatycznego merge do main; nie przepisujemy historii i nie publikujemy sekretów. Agent zgłasza hash commita, gałąź, wynik sprawdzenia i rzeczywisty wynik push. Nie udaje CI, którego jeszcze nie ma.

## Pytania i sprawdzanie wiedzy

Co 2–3 małe etapy (elastycznie, nie po każdej wiadomości) zadajemy 2–3 pytania: przewidywanie wyniku kodu, wyjaśnienie mechanizmu lub samodzielną zmianę. Co najmniej jedno pytanie wraca do wcześniejszego tematu. Pierwszy zestaw sprawdza rozumienie nazw, obiektów i referencji.

Najpierw próba, potem ocena rozumowania i wyjaśnienie. Nie dodajemy odpowiedzi zaraz pod pytaniami. Gdy potrzebna jest pomoc, dajemy wskazówkę i mniejszy przykład. Do mylącego zagadnienia wracamy później w innym kontekście, bez mechanicznego powtarzania rozwiązanego pytania.

Temat oznaczamy jako przećwiczony dopiero po rzeczywistym ćwiczeniu, a jako samodzielny po poprawnej nowej próbie. Nie wywodzimy opanowania z samej liczby testów napisanych przez agenta.

## Ścieżka Pythona i backendu

- Podstawy: nazwy i obiekty, typy, mutowalność, `is` i `==`, przypisanie i kopia, zakresy, warunki, pętle, kolekcje i funkcje.
- Pamięć: silne i słabe referencje, zliczanie referencji w CPythonie, cykle, `del`, alokator i pamięć procesu. Używamy małych eksperymentów; nie obiecujemy natychmiastowego spadku RAM ani zerowania danych.
- Model danych: klasy, instancje, atrybuty klasy i instancji, `self`, `__new__` vs `__init__`, dataclass, enum, mutowalne wartości domyślne, wyjątki, kompozycja.
- Kontrakty: duck typing, `Protocol`, klasy abstrakcyjne ABC, adnotacje typów, generyki; kiedy prosty obiekt/funkcja wystarcza i abstrakcja nie pomaga.
- Zasoby: moduły, pakowanie, iteratory, generatory, dekoratory, context managers i jawne zamykanie zasobów.
- Współbieżność: asyncio, await, pętla zdarzeń, anulowanie, TaskGroup, synchronizacja, wątki, procesy i GIL z uwzględnieniem wersji/builda.
- PostgreSQL: SQL, schematy, klucze, ograniczenia, transakcje, indeksy, migracje, blokady, EXPLAIN i pule połączeń.
- FastAPI: walidacja wejścia, zależności, cykl życia, autoryzacja, kontrakt HTTP i testy; niezależność biblioteki od API.
- Niezawodność: stany zadania i próby, claim/lease, heartbeat, ponowienia, idempotencja i ograniczenia gwarancji wykonania.
- Jakość: testy integracyjne i awarii, profilowanie, benchmarki, ewolucja publicznego API, kompatybilność i dokumentacja utrzymania.

To kolejność tematów, nie zobowiązanie do użycia każdego wzorca w kodzie biblioteki. Zawsze oddzielamy gwarancje języka od implementacji CPythona 3.13; inne wersje i wariant free-threaded omawiamy osobno.

## GCP krok po kroku

1. Podstawy projektu chmurowego, billing, alerty kosztów, regiony, gcloud, IAM i konta serwisowe — bez tworzenia zasobów w tej sesji.
2. Pierwsze niewielkie wdrożenie istniejącego kontenera API do Cloud Run z obrazem w Artifact Registry. Poznajemy rewizje, port, logi, dostęp, usunięcie zasobu i koszt pozostawienia go włączonego.
3. Cloud SQL, sieć, pule połączeń i Secret Manager, kiedy lokalny zapis zadania rzeczywiście działa.
4. Osobne uruchomienie działającego workera, ograniczenia cyklu życia, skalowanie i test utraty procesu; nie zastępujemy własnej kolejki Cloud Tasks ani Pub/Sub.
5. Cloud Logging/Monitoring, bezpieczne wdrożenia GitHub Actions z Workload Identity Federation, Terraform, rollback i ograniczanie kosztów.

Każdy krok zaczyna się od wyjaśnienia po co dana usługa, jakie potrzebuje uprawnienia i jak ją posprzątać. Aktualne warunki i koszty sprawdzamy przed wdrożeniem. Nie zakładamy, że alert budżetowy automatycznie wyłączy zasoby. Nie zapisujemy kluczy ani sekretów w repozytorium. Nie odkładamy całej nauki GCP do momentu ukończenia silnika.

## Dowody kompetencji, nie obietnica tytułu

Po kolejnych modułach sprawdzamy samodzielne zaprojektowanie i napisanie zmiany, testowanie awarii, zdiagnozowanie problemu, uzasadnienie dwóch wariantów rozwiązania oraz utrzymanie własnego wdrożenia. Te umiejętności mają budować poziom senior; sama liczba tygodni ani ilość wygenerowanego kodu go nie potwierdzają.

## Stan nauki

- Fundament i pierwsze wdrożenie do repozytorium: przygotowane przez agenta.
- Zrozumienie podstaw Pythona przez użytkowniczkę: jeszcze niezweryfikowane.
- Bieżąca pierwsza lekcja: nazwy, obiekty, przypisanie, mutacja oraz podstawy zwalniania pamięci.
- Następny mały temat: funkcje i walidacja, potem klasy potrzebne do modelu `Job`.
- GCP: żadne zasoby nie zostały jeszcze utworzone w ramach projektu.

## Materiały źródłowe

- Model danych: https://docs.python.org/3.13/reference/datamodel.html
- Przypisanie i del: https://docs.python.org/3.13/reference/simple_stmts.html
- Typowanie: https://docs.python.org/3.13/library/typing.html
- Garbage collector: https://docs.python.org/3.13/library/gc.html
- Zarządzanie pamięcią CPythona: https://docs.python.org/3.13/c-api/memory.html
- Pierwsze wdrożenie Cloud Run: https://docs.cloud.google.com/run/docs/deploying
- Tożsamości Cloud Run: https://docs.cloud.google.com/run/docs/securing/service-identity
