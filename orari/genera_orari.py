"""Genera una bozza di orari settimanali per il negozio (OR-Tools CP-SAT).

Gli orari delle casse sono fissati in FISSI; il programma organizza gli altri.
"""
from itertools import combinations
import json
from ortools.sat.python import cp_model

GIORNI = ["lunedì 12 ottobre 2026", "martedì 13 ottobre 2026", "mercoledì 14 ottobre 2026",
          "giovedì 15 ottobre 2026", "venerdì 16 ottobre 2026", "sabato 17 ottobre 2026",
          "domenica 18 ottobre 2026"]
ORE = range(9, 21)  # slot orari [h, h+1), negozio aperto 9-21

# nome, ruolo, ore settimanali, chiavi, riposi settimana precedente (0=lun..6=dom)
PERSONE = [
    ("BRUNI LAURA", "Addetto vendite", 30, False, (2, 4)),
    ("DE SANTIS MIRKO", "Vicedirettore", 44, True, (0, 3)),
    ("CILIANI ANDREA", "Addetto vendite", 40, True, (1, 6)),
    ("DI ERASMO GABRIELE", "Addetto vendite", 40, False, (0, 6)),
    ("GERMANO ALESSANDRO", "Addetto vendite", 40, False, (1, 4)),
    ("PROIETTI BENEDETTA", "Cassiera", 40, True, None),
    ("LORETI MARTINA", "Cassiera", 24, False, None),
    ("PRESTI DEBORA", "Cassiera", 24, False, None),
    ("PELLEGRINI GIORGIA", "Cassiera", 24, False, None),
    ("DIANA LUIGI", "Magazziniere", 40, False, None),
]
# turni già decisi (giorno -> tratti); i giorni mancanti sono riposo
FISSI = {
    "PROIETTI BENEDETTA": {0: ((9, 13), (14, 17)), 2: ((10, 13), (14, 21)),
                           3: ((9, 13), (14, 18)), 4: ((11, 13), (14, 21)), 5: ((9, 15),)},
    "LORETI MARTINA": {0: ((17, 21),), 1: ((9, 14),), 4: ((9, 14),), 6: ((10, 14), (15, 21))},
    "PRESTI DEBORA": {1: ((15, 21),), 2: ((9, 14),), 3: ((10, 14),), 4: ((15, 19),),
                      5: ((16, 21),)},
    "PELLEGRINI GIORGIA": {0: ((11, 14),), 1: ((14, 18),), 3: ((17, 21),), 5: ((15, 19),),
                           6: ((9, 13), (14, 19))},
    "DIANA LUIGI": {d: ((9, 13), (14, 18)) for d in range(5)},
}
# mezze giornate a settimana (gli altri giorni lavorati sono giornate intere)
MEZZE = {"DE SANTIS MIRKO": 1, "CILIANI ANDREA": 2, "DI ERASMO GABRIELE": 2,
         "GERMANO ALESSANDRO": 2}
REPARTO = {"Addetto vendite", "Vicedirettore"}


def turni():
    """Ogni turno = tupla di tratti (inizio, fine)."""
    out = []
    for s in range(9, 21):
        for L in (4, 5, 6):
            if s + L <= 21:
                out.append(((s, s + L),))
    for s1 in range(9, 13):
        for e1 in range(12, 17):
            for e2 in range(e1 + 3, 22):
                p1, p2 = e1 - s1, e2 - (e1 + 1)
                if 3 <= p1 <= 6 and 3 <= p2 <= 6 and 9 <= p1 + p2 <= 10:
                    out.append(((s1, e1), (e1 + 1, e2)))
    for giorni in FISSI.values():
        for t in giorni.values():
            if t not in out:
                out.append(t)
    return out


def ore_turno(t):
    return sum(e - s for s, e in t)


def copre(t, h):
    return any(s <= h < e for s, e in t)


def penalita_riposi(a, b, prec):
    """Quante regole sui riposi viola la coppia (a, b): stesso giorno della settimana
    scorsa, riposi attaccati o troppo distanti (oltre 5 giorni)."""
    pen = 0
    if not 2 <= b - a <= 5:
        pen += 1
    if prec:
        pen += (a in prec) + (b in prec)
        if not 2 <= (a + 7) - max(prec) <= 5:
            pen += 1
    return pen


def risolvi():
    T = turni()
    m = cp_model.CpModel()
    x = {}
    for p, (nome, ruolo, ore, chiavi, prec) in enumerate(PERSONE):
        for d in range(7):
            for i, t in enumerate(T):
                if nome in FISSI:
                    ammesso = FISSI[nome].get(d) == t
                elif nome == "BRUNI LAURA":  # niente apertura/chiusura, mattine o pomeriggi
                    ammesso = t[0][0] >= 10 and t[-1][1] <= 20 and (
                        ore_turno(t) == 9 if len(t) == 2 else
                        4 <= ore_turno(t) <= 6 and (t[0][1] <= 15 or t[0][0] >= 14))
                elif len(t) == 2:  # giornata intera spezzata 9-10h
                    ammesso = 9 <= ore_turno(t) <= 10 and min(e - s for s, e in t) >= 3
                else:  # mezza giornata 4-6h
                    ammesso = 4 <= ore_turno(t) <= 6
                if ammesso:
                    x[p, d, i] = m.NewBoolVar(f"x{p}_{d}_{i}")
    lavora = {}
    for p in range(len(PERSONE)):
        for d in range(7):
            lavora[p, d] = m.NewBoolVar("")
            m.Add(sum(v for (q, dd, i), v in x.items() if q == p and dd == d) == lavora[p, d])

    obj = []
    for p, (nome, ruolo, ore, chiavi, prec) in enumerate(PERSONE):
        if nome in FISSI:
            for d in range(7):
                m.Add(lavora[p, d] == int(d in FISSI[nome]))
            continue
        tot = sum(ore_turno(T[i]) * v for (q, d, i), v in x.items() if q == p)
        if nome == "DE SANTIS MIRKO":
            m.Add(tot >= 44); m.Add(tot <= 45)
        else:
            m.Add(tot == ore)
        # domenica niente mezze giornate (o intera o riposo)
        for (q, d, i), v in x.items():
            if q == p and d == 6 and len(T[i]) == 1:
                m.Add(v == 0)
        # sabato giornata intera per tutti
        m.Add(sum(v for (q, d, i), v in x.items() if q == p and d == 5 and len(T[i]) == 2) == 1)
        if nome in MEZZE:
            m.Add(sum(v for (q, d, i), v in x.items() if q == p and len(T[i]) == 2)
                  == 5 - MEZZE[nome])
        if nome == "BRUNI LAURA":  # alternare mattine e pomeriggi
            mezze = [(T[i], v) for (q, d, i), v in x.items() if q == p and len(T[i]) == 1]
            mattine = sum(v for t, v in mezze if t[0][1] <= 15)
            pomeriggi = sum(v for t, v in mezze if t[0][0] >= 14)
            m.Add(mattine >= 1); m.Add(pomeriggi >= 1)
            m.Add(pomeriggi - mattine <= 1); m.Add(mattine - pomeriggi <= 1)
        coppie = list(combinations([0, 1, 2, 3, 4, 6], 2))
        scelta = [m.NewBoolVar("") for _ in coppie]
        m.AddExactlyOne(scelta)
        for d in range(7):
            m.Add(lavora[p, d] == 1 - sum(s for s, c in zip(scelta, coppie) if d in c))
        obj += [60 * penalita_riposi(a, b, prec) * s for s, (a, b) in zip(scelta, coppie)]

    def presenti(d, h, filtro):
        return sum(v for (p, dd, i), v in x.items()
                   if dd == d and copre(T[i], h) and filtro(PERSONE[p]))

    for d in range(7):
        m.Add(presenti(d, 9, lambda q: q[3]) >= 1)    # apertura con chiavi
        m.Add(presenti(d, 20, lambda q: q[3]) >= 1)   # chiusura con chiavi
        for h in ORE:
            rep = presenti(d, h, lambda q: q[1] in REPARTO)
            m.Add(rep >= 1)
            manca = m.NewIntVar(0, 1, "")
            m.Add(manca >= 2 - rep)
            obj.append(100 * manca)
            # il terzo addetto di reparto serve soprattutto di pomeriggio
            manca3 = m.NewIntVar(0, 2, "")
            m.Add(manca3 >= 3 - rep)
            obj.append((10 if h >= 15 else 1) * manca3)
    m.Minimize(sum(obj))
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = 120
    s.parameters.num_workers = 8
    st = s.Solve(m)
    print(s.StatusName(st), s.ObjectiveValue())
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise SystemExit("nessuna soluzione")
    piano = {}
    for (p, d, i), v in x.items():
        if s.Value(v):
            piano.setdefault(PERSONE[p][0], {})[d] = T[i]
    return piano


if __name__ == "__main__":
    piano = risolvi()
    with open("piano.json", "w") as f:
        json.dump({k: {str(d): t for d, t in v.items()} for k, v in piano.items()}, f, indent=1)
    for nome, *_ in PERSONE:
        print(f"{nome:20}", " | ".join(
            "+".join(f"{s}-{e}" for s, e in piano[nome][d]) if d in piano[nome] else "RIPOSO"
            for d in range(7)), sum(ore_turno(t) for t in piano[nome].values()))
    print("\nRiposi e regole violate:")
    for nome, _, _, _, prec in PERSONE:
        if nome in FISSI:
            continue
        a, b = [d for d in range(7) if d not in piano[nome]]
        print(f"{nome:20} {GIORNI[a][:3]} {GIORNI[b][:3]}  violazioni={penalita_riposi(a, b, prec)}")
    print("\nAddetti di reparto ora per ora (9..20):")
    for d in range(7):
        print(f"{GIORNI[d][:10]:11}", [sum(1 for nome, ruolo, *_ in PERSONE if ruolo in REPARTO
              and d in piano[nome] and copre(piano[nome][d], h)) for h in ORE])
