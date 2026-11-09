#!/usr/bin/env python3
"""Second checkers: exact checks written apart from the benchmark's checkers, for the claim checks (run_claim_checks).

  python3 -I second_check.py KIND ARGS... FILE

KIND is the benchmark checker the check doubles, without "_check.py": ramsey S T, multiramsey S1 ... Sr,
schur schur|weak K, vdw R K, covering V K T M, cw N D W, sph D N CLAIM, kissing D, golomb M, sortnet N, capset N,
no3line N, hadamard N, cwm N K, costas N, mols N, projplane N, srg V K L M, cage K G, degdiam D K, snake snake|coil D,
superperm N, strongpow M K, tree_unimodal, lincode Q N K, ca T K V, matmul N M P FIELDS. FILE is the certificate in
the benchmark's format for that problem (get_problem gives it).

Each check reads the certificate, decides it exactly from the definition (integers, fractions and bit sets; no
floating point), prints what it found and, as its last line, "RESULT v" with the value it proves. Exit status 0: the
object is valid and v is proved; 1: the object is invalid (the reason is printed); 2: the input could not be read or
the object is beyond this checker's size limits (nothing is proved either way). For spherical codes the value is the
first checker's printed largest cosine, CLAIM, confirmed exactly to one unit of its 20th decimal.

These programs were written for the claim checks from the problem statements, separately from the benchmark's
checkers, which they double: a claim needs two separately written programs to agree (Quantavane's claim pipeline).
Standard library only; nothing is written and nothing is fetched."""
import itertools
import json
import math
import operator
import re
import sys
from fractions import Fraction

MAX_WORK = 60_000_000          # rough bound on the elementary steps a brute-force check may take


class Invalid(Exception):
    """The object does not satisfy the definition (exit 1)."""


class Unreadable(Exception):
    """The input cannot be read, or the check would exceed this program's limits (exit 2: no verdict)."""


def need(cond, why):
    if not cond:
        raise Invalid(why)


def ints(text):
    """Every integer in the text (signs kept)."""
    return [int(x) for x in re.findall(r"-?\d+", text)]


def data_lines(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def popcount(x):
    return bin(x).count("1")


def binom(n, k):
    return math.comb(n, k) if 0 <= k <= n else 0


def work(amount, what):
    if amount > MAX_WORK:
        raise Unreadable(f"{what}: about {amount:,} steps, beyond this second checker's limit of {MAX_WORK:,}")


# --------------------------------------------------------------------------------------------- graphs


def _n6(data, i):
    """N(n) of the graph6/sparse6 formats at data[i]: (n, next index)."""
    if data[i] < 126:
        return data[i] - 63, i + 1
    if data[i + 1] < 126:
        return ((data[i + 1] - 63) << 12) | ((data[i + 2] - 63) << 6) | (data[i + 3] - 63), i + 4
    n = 0
    for b in data[i + 2:i + 8]:
        n = (n << 6) | (b - 63)
    return n, i + 8


def _bits6(data):
    for b in data:
        v = b - 63
        if not 0 <= v < 64:
            raise Unreadable("a character outside the graph6/sparse6 range")
        for s in range(5, -1, -1):
            yield (v >> s) & 1


def decode_graph(text, matrix_ok=False):
    """(n, edges) from graph6, sparse6, an edge list "u v" per line (vertices from 0) or, when matrix_ok, a 0/1
    adjacency matrix. Loops and repeated edges are refused."""
    body = text.strip()
    for head in (">>graph6<<", ">>sparse6<<"):
        if body.startswith(head):
            body = body[len(head):].strip()
    lines = data_lines(body)
    if not lines:
        raise Unreadable("no graph in the file")
    first = lines[0]
    edges = []
    if first.startswith(":"):                                      # sparse6
        data = first[1:].encode("ascii")
        n, i = _n6(data, 0)
        k = max(1, (n - 1).bit_length()) if n > 1 else 1
        bits = list(_bits6(data[i:]))
        v, pos = 0, 0
        while pos + 1 + k <= len(bits):
            b = bits[pos]
            x = int("".join(map(str, bits[pos + 1:pos + 1 + k])), 2)
            pos += 1 + k
            if b:
                v += 1
            if v >= n or x >= n:
                break
            if x > v:
                v = x
            else:
                edges.append((x, v))
    elif all(63 <= ord(ch) <= 126 for ch in first) and len(lines) == 1 and not re.search(r"\d", first):   # graph6
        data = first.encode("ascii")
        n, i = _n6(data, 0)
        bits = _bits6(data[i:])
        for j in range(1, n):
            for a in range(j):
                if next(bits, 0):
                    edges.append((a, j))
    elif matrix_ok and all(re.fullmatch(r"[01]+", ln) for ln in lines) and len(lines) > 1 \
            and all(len(ln) == len(lines) for ln in lines):        # adjacency matrix
        n = len(lines)
        for a in range(n):
            need(lines[a][a] == "0", f"a loop at vertex {a}")
            for b in range(a + 1, n):
                need(lines[a][b] == lines[b][a], f"the matrix is not symmetric at ({a}, {b})")
                if lines[a][b] == "1":
                    edges.append((a, b))
    else:                                                          # edge list
        nums = []
        for ln in lines:
            t = ints(ln)
            if len(t) != 2:
                raise Unreadable(f"an edge-list line that is not two vertices: {ln[:60]!r}")
            nums.append(t)
        need(all(a >= 0 and b >= 0 for a, b in nums), "a negative vertex number")
        n = 1 + max(max(a, b) for a, b in nums)
        edges = [(a, b) for a, b in nums]
    seen = set()
    for a, b in edges:
        need(a != b, f"a loop at vertex {a}")
        e = (min(a, b), max(a, b))
        need(e not in seen, f"the edge {e[0]} {e[1]} is repeated")
        seen.add(e)
    return n, sorted(seen)


def adjacency(n, edges):
    adj = [[] for _ in range(n)]
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    return adj


def bitsets(n, edges):
    bs = [0] * n
    for a, b in edges:
        bs[a] |= 1 << b
        bs[b] |= 1 << a
    return bs


# --------------------------------------------------------------------------------------------- cliques


def clique_of_size(nbr, verts, size):
    """A clique of `size` vertices inside the bit set `verts` (nbr[v]: v's neighbours as a bit set), or None.
    Branch and bound with a greedy colouring bound (a set that needs c colours holds no clique of c + 1 vertices)."""
    def colour_order(cand):
        order, bound, colour = [], [], 0
        uncol = cand
        while uncol:
            colour += 1
            avail = uncol
            while avail:
                v = (avail & -avail).bit_length() - 1
                avail &= ~nbr[v] & ~(1 << v)
                uncol &= ~(1 << v)
                order.append(v)
                bound.append(colour)
        return order, bound

    def grow(chosen, cand, missing):
        if missing == 0:
            return chosen
        order, bound = colour_order(cand)
        for i in range(len(order) - 1, -1, -1):
            if bound[i] < missing:
                return None
            v = order[i]
            found = grow(chosen + [v], cand & nbr[v], missing - 1)
            if found is not None:
                return found
            cand &= ~(1 << v)
        return None
    if size <= 0:
        return []
    sys.setrecursionlimit(max(1000, 4 * size + 100))
    # relabel the vertices by decreasing degree inside verts, so that the greedy colouring meets the busiest first
    order = sorted((v for v in range(len(nbr)) if verts >> v & 1), key=lambda v: -popcount(nbr[v] & verts))
    new = {v: i for i, v in enumerate(order)}
    old_nbr = nbr
    nbr = [0] * len(order)
    for v in order:
        bits, x = 0, old_nbr[v] & verts
        while x:
            low = x & -x
            bits |= 1 << new[low.bit_length() - 1]
            x ^= low
        nbr[new[v]] = bits
    found = grow([], (1 << len(order)) - 1, size)
    return None if found is None else [order[i] for i in found]


def check_ramsey(args, text):
    s, t = int(args[0]), int(args[1])
    rows = data_lines(text)
    n = len(rows)
    need(n >= 1, "an empty matrix")
    need(n <= 4096, "more than 4096 vertices")
    need(all(len(r) == n for r in rows), "the rows do not all have n characters")
    red = [0] * n
    for i, r in enumerate(rows):
        need(set(r) <= {"0", "1"}, f"row {i} has a character other than 0 and 1")
        need(r[i] == "0", f"the diagonal entry of row {i} is not 0")
        for j in range(i + 1, n):
            need(r[j] == rows[j][i], f"the matrix is not symmetric at ({i}, {j})")
            if r[j] == "1":
                red[i] |= 1 << j
                red[j] |= 1 << i
    full = (1 << n) - 1
    blue = [full & ~red[i] & ~(1 << i) for i in range(n)]
    c = clique_of_size(red, full, s)
    need(c is None, f"a red K_{s}: vertices {sorted(c or [])}")
    c = clique_of_size(blue, full, t)
    need(c is None, f"a blue K_{t}: vertices {sorted(c or [])}")
    print(f"n {n}: no red K_{s} and no blue K_{t}")
    return n


def check_multiramsey(args, text):
    sizes = [int(a) for a in args]
    r = len(sizes)
    rows = data_lines(text)
    n = len(rows)
    need(n >= 1 and all(len(x) == n for x in rows), "the rows do not all have n characters")
    cls = [[0] * n for _ in range(r)]
    for i in range(n):
        for j in range(i + 1, n):
            a, b = rows[i][j], rows[j][i]
            need(a == b, f"the matrix is not symmetric at ({i}, {j})")
            need(a.isdigit() and int(a) < r, f"the colour {a!r} of the edge {{{i},{j}}} is not in 0..{r - 1}")
            c = int(a)
            cls[c][i] |= 1 << j
            cls[c][j] |= 1 << i
    full = (1 << n) - 1
    for c in range(r):
        k = clique_of_size(cls[c], full, sizes[c])
        need(k is None, f"colour {c} holds a K_{sizes[c]}: vertices {sorted(k or [])}")
    print(f"n {n}: no colour c holds K_(S_c)")
    return n


# --------------------------------------------------------------------------------------------- colourings of 1..n


def digits(text):
    return "".join(text.split())


def check_schur(args, text):
    kind, k = args[0], int(args[1])
    need(kind in ("schur", "weak"), "the kind is schur or weak")
    s = digits(text)
    n = len(s)
    need(n >= 1, "an empty colouring")
    need(all(ch.isdigit() and int(ch) < k for ch in s), f"a colour outside 0..{k - 1}")
    for c in range(k):
        members = [i + 1 for i in range(n) if int(s[i]) == c]
        bits = 0
        for x in members:
            bits |= 1 << x
        for x in members:
            hit = (bits >> x) & bits            # y in the class with x + y in the class
            if kind == "weak":
                hit &= ~(1 << x)
            if hit:
                y = (hit & -hit).bit_length() - 1
                raise Invalid(f"{x} + {y} = {x + y}, all of colour {c}")
    print(f"n {n}: a {'weak ' if kind == 'weak' else ''}Schur colouring with {k} colours")
    return n


def check_vdw(args, text):
    r, k = int(args[0]), int(args[1])
    s = digits(text)
    n = len(s)
    need(n >= 1, "an empty colouring")
    need(k >= 2, "progressions of at least 2 terms")
    need(all(ch.isdigit() and int(ch) < r for ch in s), f"a colour outside 0..{r - 1}")
    work(r * (n // (k - 1)) * k, "van der Waerden check")
    for c in range(r):
        members = 0
        for i, ch in enumerate(s):
            if int(ch) == c:
                members |= 1 << i
        for d in range(1, (n - 1) // (k - 1) + 1):
            starts = members                 # bit a stays set while a, a + d, ..., a + j d are all of colour c
            for j in range(1, k):
                starts &= members >> (j * d)
                if not starts:
                    break
            if starts:
                a = (starts & -starts).bit_length() - 1
                raise Invalid(f"colour {c} holds the progression {a + 1}, {a + 1 + d}, ... ({k} terms, step {d})")
    print(f"n {n}: no monochromatic {k}-term progression in {r} colours")
    return n


# --------------------------------------------------------------------------------------------- designs and codes


def check_covering(args, text):
    v, k, t, m = (int(a) for a in args)
    blocks = []
    for ln in data_lines(text):
        b = ints(ln.split("#")[0])
        if not b:
            continue
        need(len(b) == k and len(set(b)) == k, f"a block that is not {k} distinct points: {ln[:60]}")
        need(all(1 <= x <= v for x in b), f"a point outside 1..{v}: {ln[:60]}")
        blocks.append(sum(1 << (x - 1) for x in b))
    need(blocks, "no blocks")
    if m == t:
        total = binom(v, t)
        work(total + len(blocks) * binom(k, t), "covering check")
        seen = bytearray(total)
        table = [[binom(a, i) for i in range(t + 1)] for a in range(v + 1)]
        for b in blocks:
            pts = [i for i in range(v) if b >> i & 1]
            for sub in itertools.combinations(pts, t):
                seen[sum(table[x][i + 1] for i, x in enumerate(sub))] = 1
        missing = seen.find(0)
        if missing >= 0:
            raise Invalid(f"a {t}-subset of 1..{v} lies in no block ({total - sum(seen)} of {total} uncovered)")
    else:
        work(binom(v, m) * len(blocks), "covering check")
        for sub in itertools.combinations(range(v), m):
            mask = sum(1 << x for x in sub)
            if not any(popcount(mask & b) >= t for b in blocks):
                raise Invalid(f"the {m}-subset {[x + 1 for x in sub]} meets every block in fewer than {t} points")
    print(f"blocks {len(blocks)}: a ({v},{k},{t}{',' + str(m) if m != t else ''}) covering")
    return len(blocks)


def check_cw(args, text):
    n, d, w = (int(a) for a in args)
    words = []
    for ln in data_lines(text):
        p = ints(ln)
        need(len(p) == w and len(set(p)) == w, f"a word that is not {w} distinct positions: {ln[:60]}")
        need(all(1 <= x <= n for x in p), f"a position outside 1..{n}")
        words.append(sum(1 << (x - 1) for x in p))
    need(words, "no words")
    share = w - (d + 1) // 2           # most positions two words at distance >= d may share
    need(len(set(words)) == len(words) or share >= w, "a repeated word")
    pairs = len(words) ** 2 // 2
    if pairs <= MAX_WORK // 2:         # every pair compared
        for i in range(len(words)):
            a = words[i]
            for j in range(i + 1, len(words)):
                if popcount(a & words[j]) > share:
                    raise Invalid(f"words {i + 1} and {j + 1} are at distance {2 * (w - popcount(a & words[j]))} "
                                  f"< {d}")
    else:                              # large codes: no (share + 1)-set of positions may lie in two words
        work(len(words) * binom(w, share + 1), "constant weight code check")
        owner = {}
        for i, a in enumerate(words):
            pos = [x for x in range(n) if a >> x & 1]
            for sub in itertools.combinations(pos, share + 1):
                key = sum(1 << x for x in sub)
                j = owner.setdefault(key, i)
                if j != i:
                    raise Invalid(f"words {j + 1} and {i + 1} share {share + 1} positions: distance below {d}")
    print(f"words {len(words)}: an ({n},{d},{w}) constant weight code")
    return len(words)


def check_lincode(args, text):
    q, n, k = (int(a) for a in args)
    p, e, poly = {2: (2, 1, None), 3: (3, 1, None), 5: (5, 1, None), 7: (7, 1, None),
                  4: (2, 2, [1, 1, 1]), 8: (2, 3, [1, 1, 0, 1]), 9: (3, 2, [2, 2, 1])}.get(q, (None, 0, None))
    if p is None:
        raise Unreadable(f"GF({q}) is not one of the fields 2, 3, 4, 5, 7, 8, 9")

    def to_poly(a):
        return [(a // p ** i) % p for i in range(e)]

    def from_poly(c):
        return sum(x * p ** i for i, x in enumerate(c))

    def pmul(a, b):                    # multiply in GF(p)[x] / poly (poly: low degree first, monic)
        if e == 1:
            return a * b % p
        ca, cb = to_poly(a), to_poly(b)
        prod = [0] * (2 * e - 1)
        for i, x in enumerate(ca):
            for j, y in enumerate(cb):
                prod[i + j] = (prod[i + j] + x * y) % p
        for deg in range(2 * e - 2, e - 1, -1):
            c = prod[deg]
            if c:
                for i in range(e + 1):
                    prod[deg - e + i] = (prod[deg - e + i] - c * poly[i]) % p
        return from_poly(prod[:e])
    add = [[from_poly([(x + y) % p for x, y in zip(to_poly(a), to_poly(b))]) for b in range(q)] for a in range(q)]
    mul = [[pmul(a, b) for b in range(q)] for a in range(q)]
    neg = [next(b for b in range(q) if add[a][b] == 0) for a in range(q)]
    inv = [0] + [next(b for b in range(q) if mul[a][b] == 1) for a in range(1, q)]
    rows = []
    for ln in data_lines(text):
        r = [int(x) for x in ln] if re.fullmatch(r"\d+", ln) and len(ln) == n else ints(ln)
        need(len(r) == n, f"a row without {n} entries: {ln[:60]}")
        need(all(0 <= x < q for x in r), f"an entry outside 0..{q - 1}")
        rows.append(r)
    need(len(rows) == k, f"{len(rows)} rows, not {k}")
    m = [list(r) for r in rows]                                    # rank by elimination over GF(q)
    rank = 0
    for col in range(n):
        piv = next((i for i in range(rank, k) if m[i][col]), None)
        if piv is None:
            continue
        m[rank], m[piv] = m[piv], m[rank]
        f = inv[m[rank][col]]
        m[rank] = [mul[f][x] for x in m[rank]]
        for i in range(k):
            if i != rank and m[i][col]:
                c = m[i][col]
                m[i] = [add[x][neg[mul[c][y]]] for x, y in zip(m[i], m[rank])]
        rank += 1
    need(rank == k, f"the rows have rank {rank}, not {k}")
    best = n
    if q == 2:
        work(2 ** k, "minimum distance by listing the code")
        vec = [sum(1 << j for j in range(n) if r[j]) for r in rows]
        cur = 0
        for i in range(1, 2 ** k):                               # Gray code: one row added per step
            cur ^= vec[(i & -i).bit_length() - 1]
            best = min(best, popcount(cur))
    else:
        count = (q ** k - 1) // (q - 1)
        work(count * n * k, "minimum distance by listing the code")
        # codewords whose first nonzero coefficient is 1 (one per line through the origin); same weight as multiples
        for lead in range(k):
            for tail in itertools.product(range(q), repeat=k - 1 - lead):
                coef = [0] * lead + [1] + list(tail)
                word = [0] * n
                for c, r in zip(coef, rows):
                    if c:
                        word = [add[x][mul[c][y]] for x, y in zip(word, r)]
                best = min(best, sum(1 for x in word if x))
    print(f"distance {best}: a [{n},{k}] code over GF({q})")
    return best


def check_ca(args, text):
    t, k, v = (int(a) for a in args)
    rows = []
    for ln in data_lines(text):
        r = [int(x) for x in ln] if v <= 10 and re.fullmatch(r"\d+", ln) and len(ln) == k else ints(ln)
        need(len(r) == k, f"a row without {k} symbols: {ln[:60]}")
        need(all(0 <= x < v for x in r), f"a symbol outside 0..{v - 1}")
        rows.append(tuple(r))
    need(rows, "no rows")
    work(binom(k, t) * len(rows), "covering array check")
    full = v ** t
    cols = list(zip(*rows))
    for ts in itertools.combinations(range(k), t):
        seen = set(zip(*(cols[c] for c in ts)))
        if len(seen) < full:
            raise Invalid(f"the columns {list(ts)} miss {full - len(seen)} of the {full} tuples")
    print(f"rows {len(rows)}: a CA({len(rows)}; {t}, {k}, {v})")
    return len(rows)


# --------------------------------------------------------------------------------------------- geometry


def check_sph(args, text):
    d, n, claim = int(args[0]), int(args[1]), Fraction(args[2])
    pts = []
    for ln in text.splitlines():
        toks = [x.strip() for x in ln.split(",")]
        if len(toks) != d:
            continue
        try:
            pts.append([Fraction(x) for x in toks])
        except (ValueError, ZeroDivisionError):
            continue
    need(len(pts) == n, f"{len(pts)} points of {d} coordinates, not {n}")
    work(n * n * d // 2, "spherical code check")
    scale = 1
    for p_ in pts:
        for x in p_:
            scale = scale * x.denominator // math.gcd(scale, x.denominator)
    vec = [[int(x * scale) for x in p_] for p_ in pts]
    norm = [sum(x * x for x in v) for v in vec]
    need(all(norm), "a point at the origin")
    unit = Fraction(1, 10 ** 20)
    hi, lo = claim + unit, claim - unit                            # the claim is printed to 20 decimals
    top = None
    for i in range(n):
        a = vec[i]
        for j in range(i + 1, n):
            ip = sum(x * y for x, y in zip(a, vec[j]))
            nn = norm[i] * norm[j]
            # cos > hi ?  (cos = ip / sqrt(nn))
            if ip > 0 and (hi <= 0 or ip * ip * hi.denominator ** 2 > hi.numerator ** 2 * nn):
                raise Invalid(f"points {i + 1} and {j + 1} have cosine above {hi}")
            if ip <= 0 and hi < 0 and ip * ip * hi.denominator ** 2 < hi.numerator ** 2 * nn:
                raise Invalid(f"points {i + 1} and {j + 1} have cosine above {hi}")
            # cos >= lo ?
            if top is None:
                if lo <= 0 and (ip >= 0 or ip * ip * lo.denominator ** 2 <= lo.numerator ** 2 * nn):
                    top = (i, j)
                elif lo > 0 and ip > 0 and ip * ip * lo.denominator ** 2 >= lo.numerator ** 2 * nn:
                    top = (i, j)
    need(top is not None, f"every cosine is below {lo}: the largest cosine is not {args[2]}")
    print(f"max_cos within 1e-20 of {args[2]} (points {top[0] + 1} and {top[1] + 1} reach it)")
    return claim


def check_kissing(args, text):
    d = int(args[0])
    vecs = [ints(ln.replace(",", " ")) for ln in data_lines(text)]
    need(vecs, "no vectors")
    dim = len(vecs[0])
    need(all(len(v) == dim for v in vecs), "vectors of different lengths")
    norm = sum(x * x for x in vecs[0])
    need(norm > 0, "a zero vector")
    need(all(sum(x * x for x in v) == norm for v in vecs), "vectors of different norms")
    work(len(vecs) ** 2 // 2 * max(1, dim // 16), "kissing check")
    half = norm // 2                          # 2 ip <= norm  <=>  ip <= floor(norm / 2)
    for i in range(len(vecs)):
        a = vecs[i]
        for j in range(i + 1, len(vecs)):
            if sum(map(operator.mul, a, vecs[j])) > half:
                raise Invalid(f"vectors {i + 1} and {j + 1} are at an angle below 60 degrees")
    if dim > d:                                                    # rank over Q by fraction-free elimination
        m = [list(v) for v in vecs]
        rank, prev = 0, 1
        for col in range(dim):
            piv = next((i for i in range(rank, len(m)) if m[i][col]), None)
            if piv is None:
                continue
            m[rank], m[piv] = m[piv], m[rank]
            for i in range(rank + 1, len(m)):
                row = []
                for c in range(dim):
                    quo, rem = divmod(m[rank][col] * m[i][c] - m[i][col] * m[rank][c], prev)
                    if rem:
                        raise Unreadable("the fraction-free elimination met an inexact division")
                    row.append(quo)
                m[i] = row
            prev = m[rank][col]
            rank += 1
            need(rank <= d, f"the vectors span a space of dimension above {d}")
    print(f"{len(vecs)} vectors of squared norm {norm}, pairwise angles at least 60 degrees, dimension at most {d}")
    return len(vecs)


def check_no3line(args, text):
    n = int(args[0])
    pts = [tuple(int(c) for c in tok.split(",")) for tok in text.split() if tok.strip()]
    need(all(len(p) == 2 and 0 <= p[0] < n and 0 <= p[1] < n for p in pts), f"a point outside the {n} x {n} grid")
    need(len(set(pts)) == len(pts), "a repeated point")
    work(len(pts) ** 2, "no-three-in-line check")
    lines = {}
    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            dx, dy = b[0] - a[0], b[1] - a[1]
            g = math.gcd(dx, dy)
            dx, dy = dx // g, dy // g
            if dx < 0 or (dx == 0 and dy < 0):
                dx, dy = -dx, -dy
            key = (dx, dy, dy * a[0] - dx * a[1])                  # direction and offset fix the line
            lines[key] = lines.get(key, 0) + 1
            need(lines[key] < 2, f"three points on the line through {a} and {b}")
    print(f"{len(pts)} points, no three on a line")
    return len(pts)


def check_capset(args, text):
    n = int(args[0])
    pts = text.split()
    need(all(len(p) == n and set(p) <= set("012") for p in pts), f"a point that is not {n} digits 0-2")
    need(len(set(pts)) == len(pts), "a repeated point")
    have = set(pts)
    work(len(pts) ** 2 * n // 2, "cap set check")
    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            c = "".join(str((-int(x) - int(y)) % 3) for x, y in zip(a, b))
            need(c not in have, f"{a}, {b} and {c} are on a line")
    print(f"{len(pts)} points, no three on a line")
    return len(pts)


def check_strongpow(args, text):
    m, k = int(args[0]), int(args[1])
    words = text.split()
    need(all(len(w) == k and all(ch.isdigit() and int(ch) < m for ch in w) for w in words),
         f"a vertex that is not {k} digits 0-{m - 1}")
    need(len(set(words)) == len(words), "a repeated vertex")
    work(len(words) ** 2 * k // 2, "strong power check")
    vv = [[int(ch) for ch in w] for w in words]
    for i, a in enumerate(vv):
        for j in range(i + 1, len(vv)):
            if all((x - y) % m in (0, 1, m - 1) for x, y in zip(a, vv[j])):
                raise Invalid(f"{words[i]} and {words[j]} are adjacent")
    print(f"{len(words)} vertices, pairwise non-adjacent in C_{m}^{k}")
    return len(words)


# --------------------------------------------------------------------------------------------- sequences


def check_golomb(args, text):
    m = int(args[0])
    marks = sorted(ints(text))
    need(len(marks) == m, f"{len(marks)} marks, not {m}")
    need(len(set(marks)) == m, "a repeated mark")
    diffs = set()
    for i in range(m):
        for j in range(i + 1, m):
            d = marks[j] - marks[i]
            need(d not in diffs, f"the difference {d} occurs twice")
            diffs.add(d)
    print(f"a Golomb ruler with {m} marks, length {marks[-1] - marks[0]}")
    return marks[-1] - marks[0]


def check_costas(args, text):
    n = int(args[0])
    p = ints(text)
    need(len(p) == n, f"{len(p)} numbers, not {n}")
    if min(p) == 1:
        p = [x - 1 for x in p]
    need(sorted(p) == list(range(n)), f"not a permutation of 1..{n}")
    vecs = set()
    for i in range(n):
        for j in range(i + 1, n):
            v = (j - i, p[j] - p[i])
            need(v not in vecs, f"the displacement {v} occurs twice")
            vecs.add(v)
    print(f"a Costas array of order {n}")
    return 1


def check_superperm(args, text):
    n = int(args[0])
    s = digits(text)
    need(all("1" <= ch <= str(n) for ch in s), f"a character outside 1..{n}")
    found = {s[i:i + n] for i in range(len(s) - n + 1) if len(set(s[i:i + n])) == n}
    need(len(found) == math.factorial(n), f"{math.factorial(n) - len(found)} permutations are missing")
    print(f"a superpermutation on {n} symbols of length {len(s)}")
    return len(s)


def check_snake(args, text):
    kind, d = args[0], int(args[1])
    need(kind in ("snake", "coil"), "the kind is snake or coil")
    seq = digits(text).lower()
    need(seq, "an empty sequence")
    steps = [int(ch, 36) for ch in seq]
    need(all(0 <= c < d for c in steps), f"a coordinate outside 0..{d - 1}")
    walk = [0]
    for c in steps:
        walk.append(walk[-1] ^ (1 << c))
    length = len(steps)
    if kind == "coil":
        need(walk[-1] == 0, "the transitions do not lead back to 0")
        verts = walk[:-1]
    else:
        verts = walk
    where = {}
    for i, v in enumerate(verts):
        need(v not in where, f"the vertex {v} is visited twice")
        where[v] = i
    m = len(verts)
    for i, v in enumerate(verts):
        for b in range(d):
            j = where.get(v ^ (1 << b))
            if j is None:
                continue
            gap = abs(i - j)
            ok = gap == 1 or (kind == "coil" and gap == m - 1)
            need(ok, f"vertices {i} and {j} of the {kind} are adjacent but not consecutive")
    print(f"a {kind} of length {length} in Q_{d}")
    return length


# --------------------------------------------------------------------------------------------- matrices and designs


def check_hadamard(args, text):
    n = int(args[0])
    rows = []
    for ln in data_lines(text):
        if re.fullmatch(r"[+\-]+", ln):
            r = [1 if ch == "+" else -1 for ch in ln]
        else:
            r = ints(ln)
        need(len(r) == n and all(x in (1, -1) for x in r), f"a row that is not {n} entries +1 or -1")
        rows.append(sum(1 << j for j, x in enumerate(r) if x < 0))
    need(len(rows) == n, f"{len(rows)} rows, not {n}")
    work(n * n // 2, "Hadamard check")
    for i in range(n):
        for j in range(i + 1, n):
            need(2 * popcount(rows[i] ^ rows[j]) == n, f"rows {i + 1} and {j + 1} are not orthogonal")
    print(f"a Hadamard matrix of order {n}")
    return 1


def check_cwm(args, text):
    n, k = int(args[0]), int(args[1])
    t = text.replace(",", " ").split()
    if len(t) == 1 or (t and all(set(x) <= set("+-0") for x in t) and len("".join(t)) == n):
        row = [{"+": 1, "-": -1, "0": 0}[ch] for ch in "".join(t)]
    else:
        row = [int(x) for x in t]
    need(len(row) == n and all(x in (-1, 0, 1) for x in row), f"a first row that is not {n} entries -1, 0, 1")
    need(sum(1 for x in row if x) == k, f"weight {sum(1 for x in row if x)}, not {k}")
    for s in range(1, n):
        need(sum(row[i] * row[(i + s) % n] for i in range(n)) == 0, f"the autocorrelation at shift {s} is not 0")
    support = [i for i in range(n) if row[i]]
    g = n
    for i in support:
        g = math.gcd(g, i - support[0])
    need(g == 1, f"improper: the support lies in a coset of the subgroup of index {g}")
    print(f"a proper circulant weighing matrix CW({n}, {k})")
    return 1


def check_mols(args, text):
    n = int(args[0])
    nums = ints(text)
    need(nums and len(nums) % (n * n) == 0, f"{len(nums)} symbols, not a multiple of {n * n}")
    if min(nums) == 1:
        nums = [x - 1 for x in nums]
    need(all(0 <= x < n for x in nums), f"a symbol outside 0..{n - 1}")
    sq = [nums[i:i + n * n] for i in range(0, len(nums), n * n)]
    full = set(range(n))
    for s, a in enumerate(sq):
        for r in range(n):
            need(set(a[r * n:(r + 1) * n]) == full, f"square {s + 1}: row {r + 1} is not a permutation")
            need(set(a[r::n]) == full, f"square {s + 1}: column {r + 1} is not a permutation")
    for i in range(len(sq)):
        for j in range(i + 1, len(sq)):
            need(len(set(zip(sq[i], sq[j]))) == n * n, f"squares {i + 1} and {j + 1} are not orthogonal")
    print(f"{len(sq)} mutually orthogonal Latin squares of order {n}")
    return len(sq)


def check_projplane(args, text):
    q = int(args[0])
    v = q * q + q + 1
    lines = [ints(ln) for ln in data_lines(text)]
    need(len(lines) == v, f"{len(lines)} lines, not {v}")
    if min(min(ln) for ln in lines) == 1:
        lines = [[x - 1 for x in ln] for ln in lines]
    need(all(len(ln) == q + 1 and len(set(ln)) == q + 1 and all(0 <= x < v for x in ln) for ln in lines),
         f"a line that is not {q + 1} distinct points")
    sets = [set(ln) for ln in lines]
    for i in range(v):
        for j in range(i + 1, v):
            need(len(sets[i] & sets[j]) == 1, f"lines {i + 1} and {j + 1} do not meet in exactly one point")
    print(f"a projective plane of order {q}")
    return 1


def check_matmul(args, text):
    n, m, p, fields = int(args[0]), int(args[1]), int(args[2]), args[3]
    try:
        doc = json.loads(text)
    except ValueError as e:
        raise Unreadable(f"not JSON: {e}") from None
    field = str(doc.get("field", ""))
    gf = re.fullmatch(r"GF\((\d+)\)", field)
    need(field in ("Q", "Q(i)") or gf, f"the field {field!r} is not Q, Q(i) or GF(p)")
    need(fields == "any" or (fields == "char0" and not gf), f"the field {field} is not allowed here ({fields})")
    mod = int(gf.group(1)) if gf else 0
    if gf:
        need(mod > 1 and all(mod % d for d in range(2, math.isqrt(mod) + 1)), f"{mod} is not a prime")

    def num(x):
        if isinstance(x, bool):
            raise Unreadable("a boolean entry")
        if isinstance(x, int):
            return Fraction(x)
        if isinstance(x, str) and re.fullmatch(r"-?\d+(/\d+)?", x.strip()):
            return Fraction(x.strip())
        raise Unreadable(f"an entry that is not an integer or a/b: {x!r}")

    def val(x):
        if field == "Q(i)" and isinstance(x, list):
            need(len(x) == 2, "a Q(i) entry that is not [re, im]")
            return (num(x[0]), num(x[1]))
        f = num(x)
        if gf:
            need(f.denominator % mod, f"a denominator divisible by {mod}")
            return f.numerator * pow(f.denominator, -1, mod) % mod
        return (f, Fraction(0)) if field == "Q(i)" else f

    def mul(a, b):
        if field == "Q(i)":
            return (a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0])
        return a * b % mod if gf else a * b

    def plus(a, b):
        if field == "Q(i)":
            return (a[0] + b[0], a[1] + b[1])
        return (a + b) % mod if gf else a + b
    zero = (Fraction(0), Fraction(0)) if field == "Q(i)" else 0

    def mat(x, r, c):
        need(isinstance(x, list) and len(x) == r and all(isinstance(row, list) and len(row) == c for row in x),
             f"a matrix that is not {r} x {c}")
        return [[val(e) for e in row] for row in x]
    terms = []
    for t in doc.get("terms", []):
        need(isinstance(t, list) and len(t) == 3, "a term that is not [U, V, W]")
        u, v, w = mat(t[0], n, m), mat(t[1], m, p), mat(t[2], n, p)
        if all(any(e != zero for row in x for e in row) for x in (u, v, w)):
            terms.append((u, v, w))
    work((n * m) * (m * p) * (n * p) * max(len(terms), 1), "matrix multiplication check")
    for i, j, j2, k, i2, k2 in itertools.product(range(n), range(m), range(m), range(p), range(n), range(p)):
        s = zero
        for u, v, w in terms:
            a = u[i][j]
            if a == zero:
                continue
            b = v[j2][k]
            if b == zero:
                continue
            s = plus(s, mul(mul(a, b), w[i2][k2]))
        want = 1 if (i == i2 and j == j2 and k == k2) else 0
        target = (Fraction(want), Fraction(0)) if field == "Q(i)" else want
        need(s == target, f"the coefficient of A[{i}][{j}] B[{j2}][{k}] in C[{i2}][{k2}] is not {want}")
    print(f"a bilinear algorithm of rank {len(terms)} for <{n},{m},{p}> over {field}")
    return len(terms)


# --------------------------------------------------------------------------------------------- graphs: checks


def check_srg(args, text):
    v, k, lam, mu = (int(a) for a in args)
    n, edges = decode_graph(text, matrix_ok=True)
    need(n == v, f"{n} vertices, not {v}")
    bs = bitsets(n, edges)
    need(all(popcount(b) == k for b in bs), f"a vertex of degree other than {k}")
    work(n * n // 2, "strongly regular check")
    for a in range(n):
        for b in range(a + 1, n):
            c = popcount(bs[a] & bs[b])
            want = lam if bs[a] >> b & 1 else mu
            need(c == want, f"vertices {a} and {b} have {c} common neighbours, not {want}")
    print(f"srg({v}, {k}, {lam}, {mu})")
    return 1


def check_cage(args, text):
    k, g = int(args[0]), int(args[1])
    n, edges = decode_graph(text)
    adj = adjacency(n, edges)
    need(all(len(a) == k for a in adj), f"a vertex of degree other than {k}")
    reach = (g - 1) // 2                     # cycles shorter than g show up within this depth from a vertex on them
    work(n * (k ** (reach + 1)), "girth check")
    for r in range(n):
        depth, parent = {r: 0}, {r: -1}
        frontier = [r]
        while frontier:
            nxt = []
            for u in frontier:
                if depth[u] > reach:
                    continue
                for w in adj[u]:
                    if w == parent[u]:
                        continue
                    if w in depth:
                        length = depth[u] + depth[w] + 1
                        need(length >= g, f"a cycle of length at most {length} through vertex {r}")
                    else:
                        depth[w], parent[w] = depth[u] + 1, u
                        nxt.append(w)
            frontier = nxt
    print(f"a {k}-regular graph of girth at least {g} on {n} vertices")
    return n


def check_degdiam(args, text):
    delta, diam = int(args[0]), int(args[1])
    n, edges = decode_graph(text)
    adj = adjacency(n, edges)
    need(all(len(a) <= delta for a in adj), f"a vertex of degree above {delta}")
    work(n * (n + len(edges)), "diameter check")
    for r in range(n):
        seen = {r}
        frontier = [r]
        for _ in range(diam):
            frontier = [w for u in frontier for w in adj[u] if w not in seen and not seen.add(w)]
        need(len(seen) == n, f"a vertex at distance above {diam} from vertex {r}")
    print(f"a graph on {n} vertices with maximum degree at most {delta} and diameter at most {diam}")
    return n


def check_tree_unimodal(args, text):
    lines = data_lines(text)
    n = None
    if lines and lines[0].split()[0] == "n":
        n = int(lines[0].split()[1])
        lines = lines[1:]
    edges = []
    for ln in lines:
        t = ints(ln)
        need(len(t) == 2, f"a line that is not an edge: {ln[:60]}")
        edges.append((t[0], t[1]))
    top = max((max(a, b) for a, b in edges), default=-1) + 1
    n = top if n is None else n
    need(n >= top, "an edge outside 0..n-1")
    seen = set()
    for a, b in edges:
        need(a != b, f"a loop at {a}")
        need((min(a, b), max(a, b)) not in seen, f"the edge {a} {b} is repeated")
        seen.add((min(a, b), max(a, b)))
    need(len(edges) <= n - 1, "more edges than a forest has")
    adj = adjacency(n, edges)

    def pmul(a, b):
        out = [0] * (len(a) + len(b) - 1)
        for i, x in enumerate(a):
            if x:
                for j, y in enumerate(b):
                    out[i + j] += x * y
        return out

    def padd(a, b):
        return [(a[i] if i < len(a) else 0) + (b[i] if i < len(b) else 0) for i in range(max(len(a), len(b)))]
    total = [1]
    done = [False] * n
    for root in range(n):
        if done[root]:
            continue
        order, parent, stack = [], {root: -1}, [root]
        done[root] = True
        while stack:
            u = stack.pop()
            order.append(u)
            for w in adj[u]:
                if w == parent[u]:
                    continue
                need(not done[w], "a cycle: not a forest")
                done[w], parent[w] = True, u
                stack.append(w)
        with_v, without_v = {}, {}
        for u in reversed(order):
            inc, exc = [0, 1], [1]
            for w in adj[u]:
                if w != parent[u]:
                    inc = pmul(inc, without_v[w])
                    exc = pmul(exc, padd(with_v[w], without_v[w]))
            with_v[u], without_v[u] = inc, exc
        total = pmul(total, padd(with_v[root], without_v[root]))
    seq = total
    fell = next((i for i in range(1, len(seq)) if seq[i] < seq[i - 1]), None)
    rise = next((i for i in range(fell + 1, len(seq)) if seq[i] > seq[i - 1]), None) if fell else None
    need(rise is not None, "the independent set sequence is unimodal")
    print(f"n {n}: the independent set sequence rises again at {rise} after falling at {fell}")
    return 1


CHECKS = {
    "ramsey": check_ramsey, "multiramsey": check_multiramsey, "schur": check_schur, "vdw": check_vdw,
    "covering": check_covering, "cw": check_cw, "lincode": check_lincode, "ca": check_ca, "sph": check_sph,
    "kissing": check_kissing, "no3line": check_no3line, "capset": check_capset, "strongpow": check_strongpow,
    "golomb": check_golomb, "costas": check_costas, "superperm": check_superperm, "snake": check_snake,
    "hadamard": check_hadamard, "cwm": check_cwm, "mols": check_mols, "projplane": check_projplane,
    "matmul": check_matmul, "srg": check_srg, "cage": check_cage, "degdiam": check_degdiam,
    "tree_unimodal": check_tree_unimodal,
}

# sortnet is defined after CHECKS so that it can use the 0-1 principle helper below


def check_sortnet(args, text):
    n = int(args[0])
    nums = ints(text)
    need(len(nums) % 2 == 0, "an odd number of channel numbers")
    comps = [(min(a, b), max(a, b)) for a, b in zip(nums[::2], nums[1::2])]
    need(all(0 <= a < b < n for a, b in comps), f"a comparator outside channels 0..{n - 1} or on one channel")
    low = min(n, 20)                         # channels run bit-sliced together; the others are fixed per chunk
    chunks = 1 << (n - low)
    work(chunks * max(len(comps), 1) * 4, "0-1 check of the sorting network")
    size = 1 << low
    base = []
    for c in range(low):                     # bit x of channel c is bit c of the input x
        block = ((1 << (1 << c)) - 1) << (1 << c)
        pattern, length = block, 1 << (c + 1)
        while length < size:
            pattern |= pattern << length
            length <<= 1
        base.append(pattern)
    ones = (1 << size) - 1
    for hi in range(chunks):
        wires = base + [ones if hi >> (c - low) & 1 else 0 for c in range(low, n)]
        for a, b in comps:
            wires[a], wires[b] = wires[a] & wires[b], wires[a] | wires[b]
        for c in range(n - 1):
            bad = wires[c] & ~wires[c + 1]
            if bad:
                x = ((bad & -bad).bit_length() - 1) | (hi << low)
                raise Invalid(f"the 0-1 input {x:0{n}b} (channel 0 is the last digit) is not sorted")
    print(f"a sorting network on {n} channels with {len(comps)} comparators")
    return len(comps)


CHECKS["sortnet"] = check_sortnet


def main(argv):
    if len(argv) < 2 or argv[0] not in CHECKS:
        print(__doc__)
        return 2
    kind, args, path = argv[0], argv[1:-1], argv[-1]
    try:
        with open(path, encoding="utf-8", errors="strict") as f:
            text = f.read()
        if kind != "matmul":                 # '#' starts a comment in every text format (the JSON one has none)
            text = "\n".join(line.split("#")[0] for line in text.splitlines())
        value = CHECKS[kind](args, text)
    except Invalid as e:
        print(f"INVALID: {e}")
        return 1
    except (Unreadable, ValueError, IndexError, UnicodeDecodeError, OverflowError) as e:
        print(f"NO VERDICT: {e}")
        return 2
    value = Fraction(value)
    print(f"RESULT {value.numerator}" + (f"/{value.denominator}" if value.denominator != 1 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
