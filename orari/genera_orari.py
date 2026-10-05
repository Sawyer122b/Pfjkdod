"""Genera una bozza di orari settimanali per il negozio (OR-Tools CP-SAT)."""
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
    ("PROIETTI BENEDETTA", "Cassiera", 40, True, (2, 4)),
    ("LORETI MARTINA", "Cassiera", 24, False, None),
    ("PRESTI DEBORA", "Cassiera", 24, False, None),
    ("PELLEGRINI GIORGIA", "Cassiera", 24, False, None),
    ("DIANA LUIGI", "Magazziniere", 40, False, None),
]
# mezze giornate a settimana (gli altri giorni lavorati sono giornate intere)
MEZZE = {"DE SANTIS MIRKO": 1, "CILIANI ANDREA": 2, "DI ERASMO GABRIELE": 2,
         "GERMANO ALESSANDRO": 2, "PROIETTI BENEDETTA": 2}
REPARTO = {"Addetto vendite", "Vicedirettore"}


def turni():
    """Ogni turno = lista di tratti (inizio, fine)."""
    out = []
    for s in range(9, 21):
        for L in (4, 5, 6):
            if s + L <= 21:
                out.append(((s, s + L),))
    for s1 in range(9, 13):
        for e1 in range(12, 17):
            for e2 in range(e1 + 3, 22):
                p1, p2 = e1 - s1, e2 - (e1 + 1)
                if 2 <= p1 <= 6 and 2 <= p2 <= 6 and 7 <= p1 + p2 <= 10:
                    out.append(((s1, e1), (e1 + 1, e2)))
    return out


def ore_turno(t):
    return sum(e - s for s, e in t)


def copre(t, h):
    return any(s <= h < e for s, e in t)


def coppie_riposo(prec):
    """Coppie di riposi ammesse: giorni diversi dalla settimana scorsa, mai il sabato,
    distanza tra riposi consecutivi (anche a cavallo delle settimane) tra 2 e 5 giorni."""
    ok = []
    for a, b in combinations([0, 1, 2, 3, 4, 6], 2):
        if a in prec or b in prec:
            continue
        if not (2 <= (a + 7) - max(prec) <= 5 and 2 <= b - a <= 5):
            continue
        ok.append((a, b))
    return ok


def risolvi():
    T = turni()
    m = cp_model.CpModel()
    x = {}
    for p, (nome, ruolo, ore, chiavi, prec) in enumerate(PERSONE):
        for d in range(7):
            for i, t in enumerate(T):
                ore_t, intera = ore_turno(t), len(t) == 2
                if ruolo == "Magazziniere":
                    ammesso = d < 5 and t == ((9, 13), (14, 18))
                elif nome == "BRUNI LAURA":  # niente apertura/chiusura
                    ammesso = (t[0][0] >= 10 and t[-1][1] <= 20 and
                               (ore_t == 9 if intera else 4 <= ore_t <= 6 and
                                (t[0][1] <= 15 or t[0][0] >= 14)))
                elif ore == 24:  # il sabato giornata lunga, gli altri giorni 5-6h filate
                    ammesso = (intera and 7 <= ore_t <= 8 and min(e - s for s, e in t) >= 3) \
                        if d == 5 else (not intera and ore_t >= 5)
                else:  # giornata intera spezzata 9-10h oppure mezza giornata 4-6h
                    ammesso = (9 <= ore_t <= 10 and min(e - s for s, e in t) >= 3) if intera \
                        else 4 <= ore_t <= 6
                if ammesso:
                    x[p, d, i] = m.NewBoolVar(f"x{p}_{d}_{i}")
    lavora = {}
    for p in range(len(PERSONE)):
        for d in range(7):
            vs = [x[p, d, i] for i in range(len(T)) if (p, d, i) in x]
            lavora[p, d] = m.NewBoolVar("")
            m.Add(sum(vs) == lavora[p, d])

    obj = []
    for p, (nome, ruolo, ore, chiavi, prec) in enumerate(PERSONE):
        tot = sum(ore_turno(T[i]) * v for (q, d, i), v in x.items() if q == p)
        if nome == "DE SANTIS MIRKO":
            m.Add(tot >= 44); m.Add(tot <= 45)
        else:
            m.Add(tot == ore)
        if ruolo == "Magazziniere":
            for d in range(5):
                m.Add(lavora[p, d] == 1)
            continue
        m.Add(lavora[p, 5] == 1)  # sabato lavorano tutti
        intere = sum(v for (q, d, i), v in x.items() if q == p and len(T[i]) == 2)
        if ore >= 30:  # sabato giornata intera per tutti
            m.Add(sum(v for (q, d, i), v in x.items()
                      if q == p and d == 5 and len(T[i]) == 2) == 1)
        if nome in MEZZE:
            m.Add(intere == 5 - MEZZE[nome])
        if nome == "BRUNI LAURA":  # alternare mattine e pomeriggi
            for cond in (lambda t: t[0][1] <= 15, lambda t: t[0][0] >= 14):
                m.Add(sum(v for (q, d, i), v in x.items()
                          if q == p and len(T[i]) == 1 and cond(T[i])) >= 1)
            pomeriggi = sum(v for (q, d, i), v in x.items()
                            if q == p and len(T[i]) == 1 and T[i][0][0] >= 14)
            mattine = sum(v for (q, d, i), v in x.items()
                          if q == p and len(T[i]) == 1 and T[i][0][1] <= 15)
            m.Add(pomeriggi - mattine <= 1); m.Add(mattine - pomeriggi <= 1)
        if prec is not None:
            coppie = coppie_riposo(prec)
            scelta = [m.NewBoolVar("") for _ in coppie]
            m.AddExactlyOne(scelta)
            for d in range(7):
                m.Add(lavora[p, d] == 1 - sum(s for s, c in zip(scelta, coppie) if d in c))
        else:  # part-time: 4 giorni, mai 3 giorni di riposo di fila
            m.Add(sum(lavora[p, d] for d in range(7)) == 4)
            for d in range(5):
                m.Add(sum(lavora[p, d + k] for k in range(3)) >= 1)

    def presenti(d, h, filtro):
        return sum(v for (p, dd, i), v in x.items()
                   if dd == d and copre(T[i], h) and filtro(PERSONE[p]))

    for d in range(7):
        m.Add(presenti(d, 9, lambda q: q[3]) >= 1)    # apertura con chiavi
        m.Add(presenti(d, 20, lambda q: q[3]) >= 1)   # chiusura con chiavi
        for h in ORE:
            m.Add(presenti(d, h, lambda q: q[1] == "Cassiera") >= 1)
            rep = presenti(d, h, lambda q: q[1] in REPARTO)
            m.Add(rep >= 1)
            manca = m.NewIntVar(0, 1, "")
            m.Add(manca >= 2 - rep)
            obj.append(100 * manca)
            # il terzo addetto di reparto serve soprattutto di pomeriggio
            manca3 = m.NewIntVar(0, 2, "")
            m.Add(manca3 >= 3 - rep)
            obj.append((10 if h >= 15 else 1) * manca3)
            cas = presenti(d, h, lambda q: q[1] == "Cassiera")
            extra = m.NewIntVar(0, 5, "")
            m.Add(extra >= cas - 2)
            obj.append(5 * extra)
    # preferisci tratti di almeno 3 ore (niente spezzoni da 2 ore)
    obj += [3 * v for (p, d, i), v in x.items() if min(e - s for s, e in T[i]) < 3]
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
            for d in range(7)))
    print("\nOre con meno di 2 addetti di reparto:")
    for d in range(7):
        buchi = [h for h in ORE if sum(
            1 for nome, ruolo, *_ in PERSONE if ruolo in REPARTO and d in piano[nome]
            and copre(piano[nome][d], h)) < 2]
        print(GIORNI[d], [f"{h}-{h+1}" for h in buchi])
    print("\nAddetti di reparto ora per ora (9..20):")
    for d in range(7):
        print(f"{GIORNI[d][:10]:11}", [sum(1 for nome, ruolo, *_ in PERSONE if ruolo in REPARTO
              and d in piano[nome] and copre(piano[nome][d], h)) for h in ORE])
