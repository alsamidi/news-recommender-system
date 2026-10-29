"""Build the manual-calculation workbook for the hybrid CBF + ALS recommender.

Thesis appendix that walks the served pipeline cell by cell: token -> TF ->
IDF -> TF-IDF -> cosine -> CBF ranking -> ALS dot product -> min-max blend
-> rendered cards -> ranking metrics. Authoring style follows the CBF_KBF
reference workbook: black = Excel formula, blue = data from this repo,
yellow = editable parameter.

Every input traces to an artifact:
  - the 12 sample articles are real rows of data/processed/indo/catalog.parquet
  - the 128-dim item factors are real rows of
    data/processed/indo/indo_als_item_factors.npy
  - alpha / top_k / K match configs/indo_serving.yaml + serving defaults
  - sheet 12 reads models/indo_eval.json (locked) and
    docs/evidence/phase2/metric_comparison.json (reported means)

Limits, stated on the Petunjuk sheet and on the affected sheets:
  - TF-IDF is fit on the 12 sample documents so every cell is recomputable by
    hand. Production fits on 67,381 train documents (~99k terms), so cosine
    values here are method-exact but not numerically equal to served ones.
  - min-max runs over the 12 candidates; production runs over the full
    effective catalog (17,584 items) per account.
  - the 3 session items and the 2 relevant items are scenario inputs, not one
    of the 600 simulated accounts; sheet 12 carries the locked numbers.

Usage:
    venv/bin/python scripts/build_manual_workbook.py [output.xlsx]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "data/processed/indo/catalog.parquet"
FACTORS = REPO / "data/processed/indo/indo_als_item_factors.npy"
TRAIN = REPO / "data/processed/indo/interactions_train.parquet"
EVAL = REPO / "models/indo_eval.json"
METRIC_CMP = REPO / "docs/evidence/phase2/metric_comparison.json"
DEFAULT_OUT = (REPO / "docs/evidence/phase2"
               / "Perhitungan_Manual_Rekomendasi_Hybrid_CBF_ALS.xlsx")

NIDS = [
    "I2d5df0726f",  # Embung Pekayon
    "I0f3340d602",  # Israel dan Hamas tukar sandera
    "Ic3f4f2512e",  # 80 kabupaten SIPP Award
    "Ifa9f81c923",  # Kontroversi Erick Thohir
    "I1d82a5e6ee",  # Sayonara Sri Mulyani
    "Ib13654bb81",  # Seribu Senjata
    "I5259c70cfc",  # Bak Orang
    "I67dbbb2a6e",  # Puthul serangga
    "I307e7d7249",  # Panah ikan
    "I99144f9b4e",  # Mobil nasional PSN
    "I01684f5bad",  # Santri ponpes
    "I18ca3d0ae0",  # Delegasi GSF
]
SESSION_POS = [0, 1, 3]   # profil sesi -> dimask
RELEVANT_POS = [7, 8]     # relevan untuk sheet 11
ALPHA, TOP_K, K_EVAL, N_FACT = 0.8, 10, 5, 128
NDEC = 6

HDR_FILL = PatternFill("solid", fgColor="1F4E78")
HDR_FONT = Font(name="Arial", size=11, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="Arial", size=14, bold=True)
NOTE_FONT = Font(name="Arial", size=10, italic=True, color="555555")
BOLD = Font(name="Arial", size=11, bold=True)
IN = Font(name="Arial", size=11, color="0000FF")
FX = Font(name="Arial", size=11, color="000000")
PARAM_FILL = PatternFill("solid", fgColor="FFFF00")
THIN = Side(style="thin", color="B0B0B0")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
DEC = "0.000000"


def put(ws, coord, value, font=FX, fill=None, fmt=None, border=True):
    c = ws[coord]
    c.value = value
    c.font = font
    if fill is not None:
        c.fill = fill
    if fmt:
        c.number_format = fmt
    if border:
        c.border = BORDER
    return c


def header(ws, row, labels, start=1, height=30):
    for i, lab in enumerate(labels):
        c = ws.cell(row=row, column=start + i, value=lab)
        c.font, c.fill, c.border = HDR_FONT, HDR_FILL, BORDER
        c.alignment = Alignment(horizontal="center", vertical="center",
                                wrap_text=True)
    ws.row_dimensions[row].height = height


def title(ws, text, row=1):
    c = ws.cell(row=row, column=1, value=text)
    c.font, c.border = TITLE_FONT, Border()


def note(ws, text, row=2):
    c = ws.cell(row=row, column=1, value=text)
    c.font, c.border = NOTE_FONT, Border()


def cl(pos: int) -> str:
    """Sample position -> Excel column letter (B is position 0)."""
    return get_column_letter(2 + pos)


def ground_truth() -> dict:
    cat = pd.read_parquet(CATALOG, columns=[
        "nid", "title", "category", "source", "published_at",
        "processed_text"])
    cat = cat.set_index("nid").loc[NIDS].reset_index()

    factors = np.load(FACTORS)
    order = sorted(pd.read_parquet(TRAIN, columns=["nid"])["nid"].unique())
    row_of = {n: i for i, n in enumerate(order)}
    # factors are written to the sheet rounded, so the reference uses them
    # rounded too: sheet and check must agree to the last digit shown.
    F = np.round(np.vstack([factors[row_of[n]] for n in NIDS]), NDEC)

    toks = [t.split() for t in cat["processed_text"].tolist()]
    vocab = sorted({t for tk in toks for t in tk})
    n = len(NIDS)
    tf = np.zeros((len(vocab), n))
    for j, tk in enumerate(toks):
        for t in tk:
            tf[vocab.index(t), j] += 1.0
    dfc = (tf > 0).sum(axis=1)
    idf = np.log((1 + n) / (1 + dfc)) + 1.0
    w = tf * idf[:, None]
    norm = np.sqrt((w ** 2).sum(axis=0))
    wn = w / norm

    prof = wn[:, SESSION_POS].mean(axis=1)
    pnorm = float(np.linalg.norm(prof))
    cos_profile = (wn.T @ prof) / pnorm
    pair = wn.T @ wn

    aprof = F[SESSION_POS].mean(axis=0)
    als_raw = F @ aprof

    def scale(v):
        return (v - v.min()) / (v.max() - v.min())

    m_als, m_cbf = scale(als_raw), scale(cos_profile)
    hybrid = ALPHA * m_als + (1 - ALPHA) * m_cbf
    live = [i for i in range(n) if i not in SESSION_POS]
    ranked = sorted(live, key=lambda i: (-hybrid[i], i))

    rel = set(RELEVANT_POS)

    def dcg(gains):
        return sum(g / math.log2(p + 2) for p, g in enumerate(gains))

    gains = [1.0 if i in rel else 0.0 for i in ranked[:K_EVAL]]
    hits, ap = 0, 0.0
    for p, i in enumerate(ranked[:K_EVAL]):
        if i in rel:
            hits += 1
            ap += hits / (p + 1)
    ap /= min(len(rel), K_EVAL)
    ideal = [1.0] * min(len(rel), K_EVAL)

    return dict(
        cat=cat, F=F, toks=toks, vocab=vocab, tf=tf, dfc=dfc, idf=idf, w=w,
        norm=norm, wn=wn, prof=prof, pnorm=pnorm, cos_profile=cos_profile,
        pair=pair, aprof=aprof, als_raw=als_raw, m_als=m_als, m_cbf=m_cbf,
        hybrid=hybrid, ranked=ranked, rel=rel,
        ndcg=dcg(gains) / dcg(ideal), ap=ap, recall=hits / len(rel))


def build(gt: dict, out: Path) -> None:
    cat, F, toks = gt["cat"], gt["F"], gt["toks"]
    vocab = gt["vocab"]
    n, V = len(NIDS), len(vocab)
    maxtok = max(len(t) for t in toks)
    r0, r1 = 5, 4 + n            # 1_Data rows of the 12 items
    tf0 = 6                      # 3_TF first data row
    tf_last = tf0 + V - 1
    norm_row = tf_last + 2       # 5_TFIDF L2-norm row
    als0 = 5                     # 8_ALS first dimension row
    als_last = als0 + N_FACT - 1
    srow = als_last + 2          # 8_ALS score row
    n_live = n - len(SESSION_POS)

    wb = Workbook()

    # ------------------------------------------------------------ Petunjuk
    ws = wb.active
    ws.title = "Petunjuk"
    title(ws, "Perhitungan Manual Sistem Rekomendasi Hybrid CBF + ALS - goodnews")
    note(ws, "Sel hitam = rumus Excel. Sel biru = data dari proyek. Sel kuning "
             "= parameter yang boleh diubah. Rumus identik dengan "
             "src/phase2/serving.py: skor = alpha x minmax(ALS) + "
             "(1 - alpha) x minmax(TF-IDF cosine), alpha = 0,8.")
    header(ws, 4, ["Sheet", "Isi", "Sumber angka"])
    rows = [
        ("1_Data", "12 artikel sampel + parameter (alpha, top_k, sesi, K)",
         "data/processed/indo/catalog.parquet - nid nyata"),
        ("2_Token", "Token tiap artikel, satu token per kolom",
         "kolom processed_text katalog fase 2"),
        ("3_TF", "Term Frequency: kemunculan tiap term per artikel (COUNTIF)",
         "rumus"),
        ("4_IDF", "df dan IDF = LN((1+N)/(1+df)) + 1 (smooth_idf scikit-learn)",
         "rumus"),
        ("5_TFIDF", "w = TF x IDF, norma L2, bobot ternormalisasi, vektor "
                    "profil sesi", "rumus"),
        ("6_Cosine", "Kosinus item ke profil + matriks 12x12 (dipakai blok "
                     "'Berita serupa')", "rumus"),
        ("7_CBF", "Peringkat content-based; artikel profil dibuang", "rumus"),
        ("8_ALS", "128 faktor laten per artikel, profil sesi = rata-rata "
                  "faktor, skor = SUMPRODUCT",
         "data/processed/indo/indo_als_item_factors.npy"),
        ("9_Hybrid", "min-max ALS dan CBF, blend alpha = 0,8, mask artikel "
                     "profil, peringkat", "rumus"),
        ("10_Tampilan", "Baris kartu yang dirender web - tanpa skor (D22)",
         "rumus"),
        ("11_Evaluasi", "NDCG@5, AP@5, Recall@5 untuk skenario dummy (K diturunkan dari 10 "
         "karena hanya ada 9 kandidat)",
         "rumus + 2 flag relevan (biru)"),
        ("12_Cek_Naskah", "Rata-rata 9 titik evaluasi terkunci vs angka "
                          "naskah", "models/indo_eval.json"),
    ]
    for i, (a, b, c) in enumerate(rows):
        put(ws, f"A{5+i}", a, font=BOLD)
        put(ws, f"B{5+i}", b)
        put(ws, f"C{5+i}", c)
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 64
    ws.column_dimensions["C"].width = 52
    r = 5 + len(rows) + 1
    for t in [
        "BATAS 1 - TF-IDF di sini di-fit pada 12 dokumen sampel agar semua "
        "sel bisa dihitung ulang dengan tangan. Produksi fit pada 67.381 "
        "dokumen train (sekitar 99 ribu term), jadi nilai kosinus di workbook "
        "identik METODENYA, tetapi tidak identik angkanya dengan yang "
        "dilayani web.",
        "BATAS 2 - min-max pada sheet 9 dijalankan atas 12 kandidat; "
        "produksi menjalankannya atas seluruh katalog efektif (17.584 item) "
        "per akun.",
        "BATAS 3 - 3 artikel profil dan 2 artikel relevan adalah skenario "
        "ilustrasi, bukan akun simulasi. Angka evaluasi resmi ada di sheet "
        "12_Cek_Naskah: 600 akun, 9 titik, grid alpha 0,2-0,8.",
        "URUTAN FAKTOR - baris faktor ALS mengikuti urutan nid terurut pada "
        "train (build_csr); di workbook dipakai posisi katalog.",
    ]:
        note(ws, t, row=r)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        ws.row_dimensions[r].height = 30
        r += 1

    # -------------------------------------------------------------- 1_Data
    ws = wb.create_sheet("1_Data")
    title(ws, "1 - Data artikel sampel dan parameter")
    note(ws, "Kolom Teks = processed_text persis di katalog; inilah input "
             "TF-IDF (sudah lowercase, tanpa tanda baca, tanpa stopword, "
             "tanpa stemming).")
    header(ws, 4, ["Pos", "nid", "Judul", "Kategori", "Sumber", "Terbit",
                   "Teks (input TF-IDF)", "Sesi?", "Relevan?"])
    for i, row in cat.iterrows():
        rr = r0 + i
        put(ws, f"A{rr}", i + 1)
        put(ws, f"B{rr}", row["nid"], font=IN)
        put(ws, f"C{rr}", row["title"], font=IN)
        put(ws, f"D{rr}", row["category"], font=IN)
        put(ws, f"E{rr}", row["source"], font=IN)
        put(ws, f"F{rr}", row["published_at"].date(), font=IN,
            fmt="dd mmm yyyy")
        put(ws, f"G{rr}", row["processed_text"], font=IN)
        put(ws, f"H{rr}", "Ya" if i in SESSION_POS else "-")
        put(ws, f"I{rr}", "Ya" if i in gt["rel"] else "-")
        ws.row_dimensions[rr].height = 28
    for col, w in zip("ABCDEFGHI", [5, 13, 44, 12, 10, 13, 86, 8, 9]):
        ws.column_dimensions[col].width = w

    header(ws, 4, ["Parameter", "Nilai", "Keterangan"], start=11, height=18)
    params = [
        ("alpha (bobot ALS)", ALPHA, "cf_weight, configs/indo_serving.yaml",
         True),
        ("bobot CBF (1 - alpha)", "=1-L5", "1 - alpha", False),
        ("top_k", TOP_K, "default serving", False),
        ("N dokumen sampel", f"=COUNT(A{r0}:A{r1})", "dipakai 4_IDF", False),
        ("jumlah term unik", f"=COUNTA('3_TF'!A{tf0}:A{tf_last})", "kosakata",
         False),
        ("dimensi faktor ALS", N_FACT, "model indo_als", False),
        ("K evaluasi", K_EVAL, "metrik @10", False),
        ("artikel profil sesi", "pos 1, 2, 4", "sudah dibaca -> dimask", False),
        ("artikel relevan", "pos 8, 9", "untuk sheet 11", False),
    ]
    for i, (k, v, d, yellow) in enumerate(params):
        rr = 5 + i
        put(ws, f"K{rr}", k, font=BOLD)
        c = put(ws, f"L{rr}", v, fmt=DEC if isinstance(v, float) else None)
        if yellow:
            c.fill, c.font = PARAM_FILL, IN
        put(ws, f"M{rr}", d)
    for col, w in (("K", 24), ("L", 16), ("M", 32)):
        ws.column_dimensions[col].width = w

    # ------------------------------------------------------------- 2_Token
    ws = wb.create_sheet("2_Token")
    title(ws, "2 - Token per artikel")
    note(ws, "Satu token per kolom. Tokenisasi = pemisahan spasi; pola "
             "scikit-learn \\b\\w\\w+\\b otomatis terpenuhi karena korpus "
             "sudah lowercase, tanpa tanda baca, dan tanpa token satu huruf. "
             "Tidak ada stemming dan tidak ada stopword.")
    header(ws, 4, ["Pos", "nid", "Sesi?"] +
           [f"t{i + 1}" for i in range(maxtok)])
    for i, tk in enumerate(toks):
        rr = r0 + i
        put(ws, f"A{rr}", i + 1)
        put(ws, f"B{rr}", cat.loc[i, "nid"], font=IN)
        put(ws, f"C{rr}", "Ya" if i in SESSION_POS else "-")
        for j, t in enumerate(tk):
            put(ws, f"{get_column_letter(4 + j)}{rr}", t, font=IN)
    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 13
    ws.column_dimensions["C"].width = 7
    for j in range(maxtok):
        ws.column_dimensions[get_column_letter(4 + j)].width = 13

    # ---------------------------------------------------------------- 3_TF
    ws = wb.create_sheet("3_TF")
    title(ws, "3 - Term Frequency (TF mentah)")
    note(ws, "TF = jumlah kemunculan term pada artikel, dihitung COUNTIF ke "
             "baris token di 2_Token. scikit-learn tidak membagi TF dengan "
             "panjang dokumen (sublinear_tf = False).")
    header(ws, 4, ["Term"] + [f"pos {i + 1}" for i in range(n)] + ["Total"])
    last_tok_col = get_column_letter(3 + maxtok)
    for i, term in enumerate(vocab):
        rr = tf0 + i
        put(ws, f"A{rr}", term, font=IN)
        for j in range(n):
            tok_row = r0 + j
            put(ws, f"{cl(j)}{rr}",
                f"=COUNTIF('2_Token'!$D${tok_row}:${last_tok_col}${tok_row},"
                f"$A{rr})")
        put(ws, f"{cl(n)}{rr}", f"=SUM(B{rr}:{cl(n - 1)}{rr})")
    put(ws, f"A{tf_last + 1}", "Total token", font=BOLD)
    for j in range(n):
        put(ws, f"{cl(j)}{tf_last + 1}",
            f"=SUM({cl(j)}{tf0}:{cl(j)}{tf_last})")
    ws.column_dimensions["A"].width = 20
    for j in range(n + 1):
        ws.column_dimensions[cl(j)].width = 8

    # --------------------------------------------------------------- 4_IDF
    ws = wb.create_sheet("4_IDF")
    title(ws, "4 - Document Frequency dan IDF")
    note(ws, "IDF = LN((1 + N) / (1 + df)) + 1, yaitu smooth_idf bawaan "
             "TfidfVectorizer. N diambil dari 1_Data!L8.")
    header(ws, 4, ["Term", "df", "(1+N)/(1+df)", "LN(...)", "IDF"])
    for i in range(V):
        rr = tf0 + i
        put(ws, f"A{rr}", f"='3_TF'!A{rr}", font=IN)
        put(ws, f"B{rr}",
            f"=COUNTIF('3_TF'!B{rr}:{cl(n - 1)}{rr},\">0\")")
        put(ws, f"C{rr}", f"=(1+'1_Data'!$L$8)/(1+B{rr})")
        put(ws, f"D{rr}", f"=LN(C{rr})", fmt=DEC)
        put(ws, f"E{rr}", f"=D{rr}+1", fmt=DEC)
    for col, w in zip("ABCDE", [20, 8, 14, 12, 12]):
        ws.column_dimensions[col].width = w

    # -------------------------------------------------------------- 5_TFIDF
    ws = wb.create_sheet("5_TFIDF")
    title(ws, "5 - Bobot TF-IDF dan normalisasi L2")
    note(ws, "Kiri: w = TF x IDF. Baris 'norma' = SQRT(SUMSQ(kolom)). Kanan: "
             "w / norma. Kolom profil = rata-rata vektor ternormalisasi dari "
             "3 artikel sesi (sesuai _cbf_scores).")
    term2_col = get_column_letter(3 + n)
    prof_col = get_column_letter(4 + 2 * n)
    header(ws, 4, ["Term"] + [f"w pos {i + 1}" for i in range(n)] +
           ["", "Term"] + [f"n pos {i + 1}" for i in range(n)] + ["profil"])
    for i in range(V):
        rr = tf0 + i
        put(ws, f"A{rr}", f"='3_TF'!A{rr}", font=IN)
        for j in range(n):
            put(ws, f"{cl(j)}{rr}",
                f"='3_TF'!{cl(j)}{rr}*'4_IDF'!$E{rr}", fmt=DEC)
        put(ws, f"{term2_col}{rr}", f"=A{rr}", font=IN)
        for j in range(n):
            col = get_column_letter(4 + n + j)
            src = cl(j)
            put(ws, f"{col}{rr}",
                f"=IF({src}${norm_row}=0,0,{src}{rr}/{src}${norm_row})",
                fmt=DEC)
        sess = [get_column_letter(4 + n + p) for p in SESSION_POS]
        put(ws, f"{prof_col}{rr}",
            f"=AVERAGE({','.join(f'{c}{rr}' for c in sess)})", fmt=DEC)
    put(ws, f"A{norm_row}", "norma", font=BOLD)
    for j in range(n):
        put(ws, f"{cl(j)}{norm_row}",
            f"=SQRT(SUMSQ({cl(j)}{tf0}:{cl(j)}{tf_last}))", fmt=DEC)
    put(ws, f"{term2_col}{norm_row}", "norma", font=BOLD)
    for j in range(n):
        col = get_column_letter(4 + n + j)
        put(ws, f"{col}{norm_row}",
            f"=SQRT(SUMSQ({col}{tf0}:{col}{tf_last}))", fmt=DEC)
    put(ws, f"{prof_col}{norm_row}",
        f"=SQRT(SUMSQ({prof_col}{tf0}:{prof_col}{tf_last}))", fmt=DEC)

    ws.column_dimensions["A"].width = 18
    for j in range(n):
        ws.column_dimensions[cl(j)].width = 11
    ws.column_dimensions[term2_col].width = 18
    for j in range(n):
        ws.column_dimensions[get_column_letter(4 + n + j)].width = 11
    ws.column_dimensions[prof_col].width = 11

    # ------------------------------------------------------------ 6_Cosine
    ws = wb.create_sheet("6_Cosine")
    title(ws, "6 - Cosine similarity")
    note(ws, "cos(item, profil) = SUMPRODUCT(item ternormalisasi, profil) / "
             "(norma item x norma profil). Tiap item sudah L2 = 1, jadi "
             "penyebutnya = norma profil. Nilai inilah yang masuk 9_Hybrid.")
    header(ws, 4, ["Pos", "nid", "Sesi?", "cos ke profil"])
    for j in range(n):
        rr = r0 + j
        col = get_column_letter(4 + n + j)
        put(ws, f"A{rr}", j + 1)
        put(ws, f"B{rr}", cat.loc[j, "nid"], font=IN)
        put(ws, f"C{rr}", "Ya" if j in SESSION_POS else "-")
        put(ws, f"D{rr}",
            f"=SUMPRODUCT('5_TFIDF'!${col}${tf0}:${col}${tf_last},"
            f"'5_TFIDF'!${prof_col}${tf0}:${prof_col}${tf_last})"
            f"/('5_TFIDF'!{col}${norm_row}*'5_TFIDF'!{prof_col}${norm_row})",
            fmt=DEC)
    for col, w in zip("ABCD", [6, 14, 8, 16]):
        ws.column_dimensions[col].width = w

    head = 5 + n + 2
    put(ws, f"A{head - 1}",
        "Matriks kosinus antar artikel - dasar blok 'Berita serupa' "
        "(similar(nid))", font=BOLD, border=False)
    header(ws, head, [""] + [f"pos {i + 1}" for i in range(n)])
    for a in range(n):
        rr = head + 1 + a
        put(ws, f"A{rr}", f"pos {a + 1}", font=BOLD)
        ca = get_column_letter(4 + n + a)
        for b in range(n):
            cb = get_column_letter(4 + n + b)
            put(ws, f"{get_column_letter(2 + b)}{rr}",
                f"=SUMPRODUCT('5_TFIDF'!${ca}${tf0}:${ca}${tf_last},"
                f"'5_TFIDF'!${cb}${tf0}:${cb}${tf_last})"
                f"/('5_TFIDF'!{ca}${norm_row}*'5_TFIDF'!{cb}${norm_row})",
                fmt=DEC)

    # --------------------------------------------------------------- 7_CBF
    ws = wb.create_sheet("7_CBF")
    title(ws, "7 - Peringkat Content-Based Filtering")
    note(ws, "Skor CBF = kosinus ke profil sesi (6_Cosine). Artikel yang "
             "sudah dibaca dibuang; idx 0 = teratas, sama seperti urutan "
             "_top di serving.py.")
    header(ws, 4, ["Pos", "nid", "Sesi?", "Skor CBF", "idx CBF", "Peringkat"])
    for j in range(n):
        rr = r0 + j
        put(ws, f"A{rr}", j + 1)
        put(ws, f"B{rr}", cat.loc[j, "nid"], font=IN)
        put(ws, f"C{rr}", f"='6_Cosine'!C{rr}")
        put(ws, f"D{rr}", f"='6_Cosine'!D{rr}", fmt=DEC)
        put(ws, f"E{rr}",
            f"=IF(C{rr}=\"Ya\",\"\","
            f"COUNTIFS($D${r0}:$D${r1},\">\"&D{rr},$C${r0}:$C${r1},\"<>Ya\")"
            f"+COUNTIFS($D${r0}:$D${r1},D{rr},$C${r0}:$C${r1},\"<>Ya\","
            f"$A${r0}:$A${r1},\"<\"&A{rr}))")
        put(ws, f"F{rr}", f"=IF(E{rr}=\"\",\"\",E{rr}+1)")
    for col, w in zip("ABCDEF", [6, 14, 8, 14, 10, 10]):
        ws.column_dimensions[col].width = w

    # --------------------------------------------------------------- 8_ALS
    ws = wb.create_sheet("8_ALS")
    title(ws, "8 - Skor Collaborative Filtering (implicit ALS)")
    note(ws, "128 faktor laten per artikel adalah baris nyata dari "
             "indo_als_item_factors.npy (dibulatkan 6 desimal). Kolom profil "
             "= AVERAGE faktor 3 artikel sesi, jalur cold session pada "
             "_als_scores. Skor = SUMPRODUCT(faktor artikel, profil).")
    header(ws, 4, ["Dim"] + [f"f pos {i + 1}" for i in range(n)] + ["profil"],
           height=18)
    prof_als = get_column_letter(2 + n)
    for d in range(N_FACT):
        rr = als0 + d
        put(ws, f"A{rr}", d + 1)
        for j in range(n):
            put(ws, f"{cl(j)}{rr}", float(F[j, d]), font=IN, fmt=DEC)
        sess = [cl(p) for p in SESSION_POS]
        put(ws, f"{prof_als}{rr}",
            f"=AVERAGE({','.join(f'{c}{rr}' for c in sess)})", fmt=DEC)
    put(ws, f"A{srow}", "skor ALS", font=BOLD)
    for j in range(n):
        put(ws, f"{cl(j)}{srow}",
            f"=SUMPRODUCT({prof_als}{als0}:{prof_als}{als_last},"
            f"{cl(j)}{als0}:{cl(j)}{als_last})", fmt=DEC)
    ws.column_dimensions["A"].width = 8
    for j in range(n + 1):
        ws.column_dimensions[get_column_letter(2 + j)].width = 14

    # ------------------------------------------------------------- 9_Hybrid
    ws = wb.create_sheet("9_Hybrid")
    title(ws, "9 - Skor hybrid (alpha = 0,8) dan peringkat")
    note(ws, "min-max per kolom skor mentah (BATAS 2: di sini atas 12 "
             "kandidat). Skor = alpha x minmax(ALS) + (1 - alpha) x "
             "minmax(CBF). Artikel sesi dimask persis seperti _mask di "
             "serving.py.")
    header(ws, 4, ["Pos", "nid", "Sesi?", "skor ALS", "minmax ALS",
                   "skor CBF", "minmax CBF", "skor hybrid", "dilayani?",
                   "Peringkat"])
    for j in range(n):
        rr = r0 + j
        put(ws, f"A{rr}", j + 1)
        put(ws, f"B{rr}", cat.loc[j, "nid"], font=IN)
        put(ws, f"C{rr}", "Ya" if j in SESSION_POS else "-")
        put(ws, f"D{rr}", f"='8_ALS'!{cl(j)}${srow}", fmt=DEC)
        put(ws, f"E{rr}",
            f"=(D{rr}-MIN($D${r0}:$D${r1}))"
            f"/(MAX($D${r0}:$D${r1})-MIN($D${r0}:$D${r1}))", fmt=DEC)
        put(ws, f"F{rr}", f"='7_CBF'!D{rr}", fmt=DEC)
        put(ws, f"G{rr}",
            f"=(F{rr}-MIN($F${r0}:$F${r1}))"
            f"/(MAX($F${r0}:$F${r1})-MIN($F${r0}:$F${r1}))", fmt=DEC)
        put(ws, f"H{rr}",
            f"='1_Data'!$L$5*E{rr}+'1_Data'!$L$6*G{rr}", fmt=DEC)
        put(ws, f"I{rr}", f"=IF(C{rr}=\"Ya\",\"-\",\"ya\")")
        put(ws, f"J{rr}",
            f"=IF(I{rr}=\"-\",\"\","
            f"COUNTIFS($H${r0}:$H${r1},\">\"&H{rr},$I${r0}:$I${r1},\"<>-\")"
            f"+COUNTIFS($H${r0}:$H${r1},H{rr},$I${r0}:$I${r1},\"<>-\","
            f"$A${r0}:$A${r1},\"<\"&A{rr})+1)")
    for col, w in zip("ABCDEFGHIJ", [6, 14, 8, 12, 12, 12, 12, 14, 10, 10]):
        ws.column_dimensions[col].width = w

    # ----------------------------------------------------------- 10_Tampilan
    ws = wb.create_sheet("10_Tampilan")
    title(ws, "10 - Kartu yang dirender halaman Beranda")
    note(ws, "Sesuai keputusan D22 skor tidak pernah dirender. Kartu memuat "
             "kategori, judul, sumber, dan tanggal, urut mengikuti peringkat "
             "hybrid.")
    header(ws, 4, ["Slot", "Peringkat hybrid", "nid", "Kategori", "Judul",
                   "Sumber", "Tanggal"])
    for i in range(n_live):
        rr = 5 + i
        put(ws, f"A{rr}", f"kartu {i + 1}")
        put(ws, f"B{rr}", i + 1)
        put(ws, f"C{rr}",
            f"=IFERROR(INDEX('9_Hybrid'!$B${r0}:$B${r1},"
            f"MATCH(B{rr},'9_Hybrid'!$J${r0}:$J${r1},0)),\"\")", font=IN)
        put(ws, f"D{rr}",
            f"=IFERROR(INDEX('1_Data'!$D${r0}:$D${r1},"
            f"MATCH(B{rr},'9_Hybrid'!$J${r0}:$J${r1},0)),\"\")", font=IN)
        put(ws, f"E{rr}",
            f"=IFERROR(INDEX('1_Data'!$C${r0}:$C${r1},"
            f"MATCH(B{rr},'9_Hybrid'!$J${r0}:$J${r1},0)),\"\")", font=IN)
        put(ws, f"F{rr}",
            f"=IFERROR(INDEX('1_Data'!$E${r0}:$E${r1},"
            f"MATCH(B{rr},'9_Hybrid'!$J${r0}:$J${r1},0)),\"\")", font=IN)
        put(ws, f"G{rr}",
            f"=IFERROR(INDEX('1_Data'!$F${r0}:$F${r1},"
            f"MATCH(B{rr},'9_Hybrid'!$J${r0}:$J${r1},0)),\"\")", font=IN,
            fmt="dd mmm yyyy")
    for col, w in (("A", 10), ("B", 16), ("C", 14), ("D", 12), ("E", 54),
                   ("F", 10), ("G", 13)):
        ws.column_dimensions[col].width = w

    # ---------------------------------------------------------- 11_Evaluasi
    ws = wb.create_sheet("11_Evaluasi")
    title(ws, "11 - Evaluasi Top-K (skenario dummy, K = 5)")
    note(ws, "Ruang evaluasi = artikel non-sesi. Relevan = 2 artikel bertanda "
             "'Ya' di 1_Data kolom I. NDCG@K, AP@K, Recall@K dihitung "
             "dengan rumus mengikuti src/phase2/evaluate.py.")
    header(ws, 4, ["Peringkat", "nid", "Relevan (1/0)", "1/log2(p+1)",
                   "gain x diskon", "Precision@p", "AP term", "Hit"])
    for i in range(n_live):
        rr = 5 + i
        p = i + 1
        put(ws, f"A{rr}", p)
        put(ws, f"B{rr}",
            f"=IFERROR(INDEX('9_Hybrid'!$B${r0}:$B${r1},"
            f"MATCH(A{rr},'9_Hybrid'!$J${r0}:$J${r1},0)),\"\")", font=IN)
        put(ws, f"C{rr}",
            f"=IF(B{rr}=\"\",0,IF(IFERROR(INDEX('1_Data'!$I${r0}:$I${r1},"
            f"MATCH(B{rr},'1_Data'!$B${r0}:$B${r1},0)),\"-\")=\"Ya\",1,0))",
            fmt="0")
        # 1/log2(p+1) = ln(2)/ln(p+1); LOG2 is not portable across importers
        put(ws, f"D{rr}", f"=LN(2)/LN(A{rr}+1)", fmt=DEC)
        put(ws, f"E{rr}", f"=C{rr}*D{rr}", fmt=DEC)
        put(ws, f"F{rr}", f"=IF(C{rr}=1,SUM($C$5:C{rr})/A{rr},0)", fmt=DEC)
        put(ws, f"G{rr}", f"=F{rr}*C{rr}", fmt=DEC)
        put(ws, f"H{rr}", f"=C{rr}", fmt="0")
    tot = 5 + n_live
    kstop = f"'1_Data'!$L$11"
    put(ws, f"A{tot}", "Total sampai K", font=BOLD)
    for col in ("C", "E", "G", "H"):
        put(ws, f"{col}{tot}",
            f"=SUM(${col}$5:INDEX(${col}$5:${col}${tot - 1},{kstop}))",
            fmt="0" if col in ("C", "H") else DEC)

    nrel = f"COUNTIF('1_Data'!$I${r0}:$I${r1},\"Ya\")"
    put(ws, f"A{tot + 1}", "Jumlah artikel relevan", font=BOLD)
    put(ws, f"C{tot + 1}", f"={nrel}", fmt="0")

    header(ws, tot + 3, ["Metrik", "Nilai", "Cara hitung"])
    idcg_end = f"INDEX($D$5:$D${tot - 1},MIN($C${tot + 1},{kstop}))"
    metrics = [
        ("NDCG@K", f"=E{tot}/SUM($D$5:{idcg_end})",
         "DCG / IDCG, ideal = min(jumlah relevan, K)"),
        ("AP@K", f"=G{tot}/MIN($C${tot + 1},{kstop})",
         "rata-rata precision pada posisi relevan, dibagi min(relevan, K)"),
        ("Recall@K", f"=H{tot}/$C${tot + 1}",
         "hit relevan dalam K / total relevan"),
    ]
    for i, (name, formula, how) in enumerate(metrics):
        rr = tot + 4 + i
        put(ws, f"A{rr}", name, font=BOLD)
        put(ws, f"B{rr}", formula, fmt=DEC)
        put(ws, f"C{rr}", how)
    for col, w in zip("ABCDEFGH", [12, 14, 13, 13, 13, 12, 11, 7]):
        ws.column_dimensions[col].width = w

    # -------------------------------------------------------- 12_Cek_Naskah
    ws = wb.create_sheet("12_Cek_Naskah")
    title(ws, "12 - Pengecekan angka evaluasi naskah")
    note(ws, "Nilai per titik (biru) dibaca dari models/indo_eval.json. "
             "Rata-rata, min, maks dihitung rumus; kolom 'dilaporkan' = mean "
             "di metric_comparison.json; kolom selisih harus 0.")
    points = json.loads(EVAL.read_text())["per_point"]
    cmp_rows = json.loads(METRIC_CMP.read_text())
    # titik yang ditampilkan adalah @10, jadi pembandingnya baris K=10
    reported = {(r["system"], r["metric"]): r["mean"]
                for r in cmp_rows if r["K"] == 10}
    systems = ["popularity", "cbf", "als", "hybrid_a0.2", "hybrid_a0.4",
               "hybrid_a0.6", "hybrid_a0.8"]
    labels = {"popularity": "Popularity", "cbf": "CBF (TF-IDF)",
              "als": "ALS (CF)", "hybrid_a0.2": "Hybrid alpha 0,2",
              "hybrid_a0.4": "Hybrid alpha 0,4",
              "hybrid_a0.6": "Hybrid alpha 0,6",
              "hybrid_a0.8": "Hybrid alpha 0,8 (dilayani)"}
    npt = len(points)
    row = 4
    for metric, key, cmp_key in [("NDCG@10", "ndcg@10", "ndcg"),
                                 ("AP@10", "ap@10", "map"),
                                 ("Recall@10", "recall@10", "recall")]:
        put(ws, f"A{row}", metric, font=Font(name="Arial", size=12,
                                             bold=True), border=False)
        row += 1
        header(ws, row, ["Sistem"] + [f"titik {i + 1}" for i in range(npt)] +
               ["Rata-rata", "Min", "Maks", "Dilaporkan", "Selisih",
                "Cocok?"], height=18)
        first, last = 2, 1 + npt
        for k, sysname in enumerate(systems):
            rr = row + 1 + k
            put(ws, f"A{rr}", labels[sysname], font=BOLD)
            for p, pt in enumerate(points):
                put(ws, f"{get_column_letter(first + p)}{rr}",
                    float(pt[key][sysname]), font=IN, fmt="0.00000000")
            put(ws, f"{get_column_letter(last + 1)}{rr}",
                f"=AVERAGE({get_column_letter(first)}{rr}:"
                f"{get_column_letter(last)}{rr})", fmt="0.00000000")
            put(ws, f"{get_column_letter(last + 2)}{rr}",
                f"=MIN({get_column_letter(first)}{rr}:"
                f"{get_column_letter(last)}{rr})", fmt="0.00000000")
            put(ws, f"{get_column_letter(last + 3)}{rr}",
                f"=MAX({get_column_letter(first)}{rr}:"
                f"{get_column_letter(last)}{rr})", fmt="0.00000000")
            rep = reported.get((sysname, cmp_key))
            put(ws, f"{get_column_letter(last + 4)}{rr}",
                float(rep) if rep is not None else "-", font=IN,
                fmt="0.00000000")
            put(ws, f"{get_column_letter(last + 5)}{rr}",
                f"={get_column_letter(last + 1)}{rr}-"
                f"{get_column_letter(last + 4)}{rr}", fmt="0.00000000")
            put(ws, f"{get_column_letter(last + 6)}{rr}",
                f"=IF(ABS({get_column_letter(last + 5)}{rr})<0.0000005,"
                f"\"cocok\",\"periksa\")")
        row += len(systems) + 2
    ws.column_dimensions["A"].width = 26
    for i in range(2, 2 + npt + 6):
        ws.column_dimensions[get_column_letter(i)].width = 13
    put(ws, f"A{row + 1}",
        "Catatan: alpha pemenang = 0,8 (rata-rata NDCG@10 tertinggi pada "
        "grid 0,2-0,8). Angka inilah yang dilayani web. Workbook ini tidak "
        "mengubah satu pun nilai terkunci.", font=NOTE_FONT, border=False)

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    gt = ground_truth()
    build(gt, out)
    print(f"wrote {out}")
    print(f"  dokumen={len(NIDS)} term={len(gt['vocab'])}")
    print("  acuan verifikasi:")
    print(f"    ndcg@{K_EVAL}={gt['ndcg']:.6f}  ap@{K_EVAL}={gt['ap']:.6f}  "
          f"recall@{K_EVAL}={gt['recall']:.6f}")
    print("    urutan 5 teratas (pos):", [int(i) + 1 for i in gt["ranked"][:5]])


if __name__ == "__main__":
    main()
