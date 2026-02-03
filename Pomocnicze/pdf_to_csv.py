import re
import os
import glob
import csv
import pdfplumber
import pandas as pd
import tabula

# ================== KONFIGURACJA ==================
# Ścieżka do PDF, z którego wyciągamy tabele
PDF_PATH = r"plik.pdf"

# Zakres stron do przetworzenia (START_PAGE liczony od 1)
# END_PAGE może być większy niż realna liczba stron — skrypt przytnie go do rzeczywistego total
START_PAGE = 1
END_PAGE = 25000

# Ile stron na jeden "batch" (shard) CSV — ułatwia wznawianie i oszczędza RAM
BATCH_PAGES = 25

# Margines do obcięcia krawędzi strony podczas ekstrakcji (żeby nie łapać ramek/stopki)
MARGIN = 6

# True: łączy tabelę z lewej i prawej kolumny w jeden wiersz (side-by-side)
# False: zapisuje osobno lewą i prawą połówkę jako osobne rekordy
SIDE_BY_SIDE = True

# Folder na batchowe CSV oraz wynik końcowy
OUT_DIR = "out_batches_csv"
FINAL_CSV = "wynik_all.csv"
# ===================================================


def sanitize_excel(s: str) -> str:
    """
    Zabezpieczenie przed tzw. CSV/Excel injection:
    - jeśli komórka zaczyna się od znaków interpretowanych jako formuła (= + - @),
      to poprzedzamy apostrofem, żeby Excel nie wykonał formuły.
    """
    if s and s[0] in ("=", "+", "-", "@"):
        return "'" + s
    return s


def clean_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalizacja tabeli po ekstrakcji:
    - rzutowanie na string (żeby ujednolicić typy),
    - zamiana 'nan' na pusty string,
    - zbijanie wielokrotnych spacji/enterów do pojedynczej spacji,
    - trim,
    - ochrona przed Excel injection,
    - usunięcie całkiem pustych wierszy i kolumn.
    """
    df = df.astype(str).replace({"nan": ""})
    df = df.map(lambda x: re.sub(r"\s+", " ", x).strip())
    df = df.map(sanitize_excel)
    df = df.loc[~(df == "").all(axis=1), :]
    df = df.loc[:, ~(df == "").all(axis=0)]
    return df


def find_gutter_x(page, fallback_ratio=0.5) -> float:
    """
    Szukanie "rynny" (gutter) — miejsca podziału strony na lewą i prawą kolumnę.
    Podejście:
    - bierzemy pionowe linie (niemal stałe x, duża wysokość),
    - sortujemy ich pozycje X,
    - szukamy największej przerwy między liniami w środku strony,
    - środek tej przerwy traktujemy jako granicę kolumn.
    Fallback:
    - jeśli nie ma wystarczającej liczby linii, używamy połowy szerokości strony.
    """
    w = float(page.width)
    mid = w * fallback_ratio

    # Zbiór X-ów pionowych linii (potencjalne separatory kolumn)
    xs = []
    for ln in (getattr(page, "lines", None) or []):
        x0, x1 = float(ln.get("x0", 0)), float(ln.get("x1", 0))
        y0, y1 = float(ln.get("y0", 0)), float(ln.get("y1", 0))

        # Warunek na linię pionową: prawie ten sam x oraz odpowiednio wysoka
        if abs(x0 - x1) < 2 and abs(y1 - y0) > float(page.height) * 0.40:
            xs.append(x0)

    # Jeśli nie mamy materiału do wyznaczenia "rynny", wracamy do środka strony
    if len(xs) < 2:
        return mid

    xs = sorted(xs)
    best_gap = 0.0
    best_center = mid

    # Szukamy największej przerwy między kolejnymi liniami w centralnym obszarze strony
    for a, b in zip(xs, xs[1:]):
        gap = b - a
        center = (a + b) / 2.0
        if gap > best_gap and (w * 0.25) < center < (w * 0.75):
            best_gap = gap
            best_center = center

    # Dodatkowy próg: jeśli "najlepsza przerwa" jest zbyt mała, bierzemy fallback
    return best_center if best_gap > 10 else mid


def half_areas(page, margin=MARGIN):
    """
    Wyznaczenie obszarów (area) dla tabula.read_pdf:
    - liczymy granicę kolumn (gutter),
    - budujemy prostokąt dla lewej i prawej połowy strony,
    - uwzględniamy marginesy, żeby nie zaciągać szumu z krawędzi.
    
    Format area dla Tabula: [top, left, bottom, right] (w jednostkach PDF).
    """
    w = float(page.width)
    h = float(page.height)
    gutter = find_gutter_x(page)

    top = margin
    bottom = h - margin

    # Lewa połowa: od lewej krawędzi do okolic rynny
    left_area = [top, margin, bottom, max(margin + 1, gutter - margin)]

    # Prawa połowa: od okolic rynny do prawej krawędzi
    right_area = [top, min(w - margin - 1, gutter + margin), bottom, w - margin]
    return left_area, right_area


def extract_biggest_table_on_area(page_no: int, area):
    """
    Ekstrakcja tabel z podanego obszaru strony przy użyciu Tabula (Java).
    Ustawienia:
    - multiple_tables=True: może zwrócić wiele tabel,
    - lattice=True: tryb "lattice" (dla tabel z liniami),
    - guess=False: nie zgadujemy automatycznie obszaru tabel — trzymamy się 'area',
    - encoding="latin1": bywa potrzebne przy specyficznych PDF-ach,
    - header=None: brak nagłówka w danych.
    
    Następnie:
    - czyścimy każdą tabelę clean_df(),
    - odrzucamy puste,
    - zwracamy największą (po powierzchni: wiersze * kolumny).
    """
    dfs = tabula.read_pdf(
        input_path=PDF_PATH,
        pages=str(page_no),
        multiple_tables=True,
        lattice=True,
        guess=False,
        area=area,
        encoding="latin1",
        pandas_options={"header": None, "dtype": str},
        silent=True
    )

    cleaned = []
    for df in (dfs or []):
        if df is None or df.empty:
            continue
        df = clean_df(df)
        if not df.empty:
            cleaned.append(df)

    if not cleaned:
        return None

    # Wybieramy największą tabelę, zakładając że to "ta właściwa"
    cleaned.sort(key=lambda d: d.shape[0] * d.shape[1], reverse=True)
    return cleaned[0]


def pad_to_cols(df: pd.DataFrame, ncols: int) -> pd.DataFrame:
    """
    Dociągnięcie tabeli do zadanej liczby kolumn:
    - jeśli ma mniej kolumn: dokładamy puste kolumny,
    - jeśli ma więcej: obcinamy nadmiar.
    
    Dzięki temu kolejne concat/CSV mają spójny schemat.
    """
    if df is None:
        return None
    cur = df.shape[1]
    if cur < ncols:
        for i in range(cur, ncols):
            df[i] = ""
    elif cur > ncols:
        df = df.iloc[:, :ncols]
    return df


def pad_rows(df: pd.DataFrame, nrows: int, ncols: int) -> pd.DataFrame:
    """
    Dociągnięcie tabeli do zadanej liczby wierszy:
    - jeśli df jest None: tworzymy minimalną tabelę 1xN (same puste),
    - jeśli ma mniej wierszy niż nrows: dokładamy puste wiersze.
    
    Cel: przy SIDE_BY_SIDE zrównujemy wysokość lewej i prawej tabeli,
    aby można je było skleić "wiersz do wiersza".
    """
    if df is None:
        df = pd.DataFrame([[""] * ncols])
    if len(df) < nrows:
        add = pd.DataFrame([[""] * ncols] * (nrows - len(df)))
        df = pd.concat([df, add], ignore_index=True)
    return df


def rename_half_columns(df: pd.DataFrame, prefix: str, ncols: int) -> pd.DataFrame:
    """
    Nadanie unikalnych nazw kolumn, żeby uniknąć konfliktów przy concat(axis=1).
    Np. lewa tabela: L_0..L_n, prawa tabela: R_0..R_n.
    
    Jeśli df jest None: tworzymy placeholder 1xN.
    """
    if df is None:
        df = pd.DataFrame([[""] * ncols])
    df = df.copy()
    df.columns = [f"{prefix}{i}" for i in range(df.shape[1])]
    return df


def write_shard_csv(path: str, df: pd.DataFrame):
    """
    Zapis pojedynczego batcha do CSV.
    Używamy utf-8-sig (UTF-8 + BOM), żeby Excel poprawnie rozpoznawał kodowanie.
    """
    df.to_csv(path, index=False, encoding="utf-8-sig")


def concat_shards_to_final(shards, out_csv):
    """
    Sklejanie wszystkich shardów do jednego pliku wynikowego bez ładowania całości do RAM:
    - otwieramy plik wynikowy raz,
    - dla pierwszego sharda zapisujemy nagłówek,
    - dla kolejnych pomijamy nagłówek i dopisujemy same wiersze.
    """
    first = True
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as fout:
        writer = None
        for fp in shards:
            with open(fp, "r", encoding="utf-8-sig", newline="") as fin:
                reader = csv.reader(fin)
                header = next(reader, None)
                if header is None:
                    continue

                if first:
                    writer = csv.writer(fout)
                    writer.writerow(header)
                    first = False

                # Pomijamy nagłówek dla kolejnych shardów, zapisujemy tylko dane
                for row in reader:
                    writer.writerow(row)


def main():
    """
    Główna procedura:
    1) Walidacja wejścia + przygotowanie katalogu wyjściowego,
    2) Iteracja po stronach PDF w batchach,
    3) Na każdej stronie:
       - wyznaczenie lewej/prawej połówki (half_areas),
       - ekstrakcja największej tabeli z każdej połówki,
       - ujednolicenie liczby kolumn,
       - zapis side-by-side lub osobno,
    4) Zapis sharda,
    5) Sklejenie shardów do FINAL_CSV.
    """
    if not os.path.exists(PDF_PATH):
        raise FileNotFoundError(f"Nie znaleziono pliku: {PDF_PATH}")

    os.makedirs(OUT_DIR, exist_ok=True)

    # Liczba kolumn, której będziemy się trzymać w całym eksporcie.
    # Ustalana na podstawie pierwszej sensownej tabeli (lewej albo prawej).
    expected_cols = None

    with pdfplumber.open(PDF_PATH) as pdf:
        total = len(pdf.pages)
        start = max(1, START_PAGE)
        end = min(END_PAGE, total)

        print(f"Pages: {start}-{end} (total in file: {total})")
        print(f"Batch: {BATCH_PAGES} | out: {OUT_DIR}")

        # Przetwarzanie w batchach, żeby:
        # - nie trzymać zbyt wiele danych w RAM,
        # - móc wznawiać (pomijamy istniejące shardy).
        b = start
        while b <= end:
            b_end = min(b + BATCH_PAGES - 1, end)
            shard = os.path.join(OUT_DIR, f"batch_{b:05d}_{b_end:05d}.csv")

            # Jeśli shard już istnieje, to zakładamy, że ten batch jest gotowy i go omijamy
            if os.path.exists(shard):
                print(f"skip {b}-{b_end}")
                b = b_end + 1
                continue

            frames = []

            # Iteracja po stronach w bieżącym batchu
            for p in range(b, b_end + 1):
                page = pdf.pages[p - 1]  # pdfplumber indeksuje od 0, my od 1
                left_area, right_area = half_areas(page)

                # Ekstrakcja największej tabeli z lewej i prawej połówki strony
                left_df = extract_biggest_table_on_area(p, left_area)
                right_df = extract_biggest_table_on_area(p, right_area)

                # Ustalenie expected_cols z pierwszej napotkanej sensownej tabeli
                if expected_cols is None:
                    for cand in (left_df, right_df):
                        if cand is not None and not cand.empty:
                            expected_cols = cand.shape[1]
                            break

                # Jeśli nadal nie wiemy ile ma być kolumn, to nie mamy jak normalizować danych
                if expected_cols is None:
                    continue

                # Ujednolicenie liczby kolumn po lewej i prawej stronie
                left_df = pad_to_cols(left_df, expected_cols)
                right_df = pad_to_cols(right_df, expected_cols)

                if SIDE_BY_SIDE:
                    # Zrównanie liczby wierszy (żeby sklejać "wiersz w wiersz")
                    n = max(
                        len(left_df) if left_df is not None else 0,
                        len(right_df) if right_df is not None else 0,
                        1
                    )
                    left_df = pad_rows(left_df, n, expected_cols)
                    right_df = pad_rows(right_df, n, expected_cols)

                    # Unikalne nazwy kolumn (bez tego pd.concat(axis=1) może się wywalić/namieszać)
                    left_df = rename_half_columns(left_df, "L_", expected_cols)
                    right_df = rename_half_columns(right_df, "R_", expected_cols)

                    # Sklejenie w poziomie: L_* i R_* w jednym rekordzie
                    merged = pd.concat(
                        [left_df.reset_index(drop=True), right_df.reset_index(drop=True)],
                        axis=1
                    )

                    # Kolumna techniczna z numerem strony (ułatwia trace-back do PDF)
                    merged.insert(0, "_page", p)
                    frames.append(merged)
                else:
                    # Tryb alternatywny: zapisujemy lewą i prawą tabelę jako osobne rekordy
                    for dfh, pref in ((left_df, "L_"), (right_df, "R_")):
                        if dfh is None or dfh.empty:
                            continue
                        dfh = rename_half_columns(dfh, pref, expected_cols)
                        dfh.insert(0, "_page", p)
                        frames.append(dfh)

            # Jeśli coś zebraliśmy w batchu — składamy do jednej ramki
            if frames:
                batch_df = pd.concat(frames, ignore_index=True)
            else:
                # Marker pustego batcha:
                # - zapisujemy poprawny plik CSV, żeby przy wznawianiu nie mielić tego samego batcha,
                # - schema zależy od tego, czy expected_cols udało się ustalić.
                if expected_cols is None:
                    batch_df = pd.DataFrame({"_page": []})
                else:
                    cols = (
                        ["_page"]
                        + [f"L_{i}" for i in range(expected_cols)]
                        + [f"R_{i}" for i in range(expected_cols)]
                    )
                    batch_df = pd.DataFrame({c: [] for c in cols})

            # Zapis batcha jako shard CSV
            write_shard_csv(shard, batch_df)
            print(f"done {b}-{b_end}")
            b = b_end + 1

    # ======= SCALENIE DO JEDNEGO CSV =======
    # Po przetworzeniu wszystkich batchy zbieramy shardy i sklejamy do FINAL_CSV
    shards = sorted(glob.glob(os.path.join(OUT_DIR, "batch_*.csv")))
    if not shards:
        raise RuntimeError("Brak shardów do scalenia. Nic nie zapisano.")

    print(f"Scalam {len(shards)} shardów -> {FINAL_CSV}")
    concat_shards_to_final(shards, FINAL_CSV)
    print(f"OK -> {FINAL_CSV}")


# Standardowy entrypoint — pozwala uruchomić plik bez importowania
if __name__ == "__main__":
    main()
