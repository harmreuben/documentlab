"""Machine-readable zone (MRZ) parsing and checking, following ICAO Doc 9303.

Supported layouts:
    TD3  passports           2 lines x 44 characters
    TD2  ID cards / visas    2 lines x 36 characters
    TD1  ID cards            3 lines x 30 characters

What is checked: line lengths, allowed characters, every check digit (document number,
birth date, expiry date, optional data, composite), real calendar dates, expiry, sex code
and code formats. OCR confusions (O/0, I/1, S/5, B/8...) are corrected only where the
position allows a single kind of character, and every correction is listed so a person
can confirm it. Passing these checks shows the MRZ is internally consistent; it does not
show the document is genuine.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from itertools import product

from .checks import FAIL, PASS, REVIEW, Check, worst
from .dates import nice, yymmdd

LAYOUTS = {"TD3": (2, 44), "TD2": (2, 36), "TD1": (3, 30)}
SPECIMEN_STATE = "UTO"  # ICAO's fictional "Utopia", used on specimen documents

_TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "G": "6", "B": "8"}
_TO_ALPHA = {v: k for k, v in {"O": "0", "I": "1", "Z": "2", "S": "5", "G": "6", "B": "8"}.items()}
_AMBIGUOUS = {"0": "O", "O": "0", "1": "I", "I": "1", "5": "S", "S": "5", "8": "B", "B": "8", "2": "Z", "Z": "2"}
_VALID = re.compile(r"^[A-Z0-9<]*$")


def char_value(c: str) -> int:
    if c.isdigit():
        return int(c)
    if "A" <= c <= "Z":
        return ord(c) - 55
    return 0  # "<" and anything unexpected


def check_digit(data: str) -> str:
    """ICAO 9303 check digit: weights 7, 3, 1 repeating; sum modulo 10."""
    return str(sum(char_value(c) * (7, 3, 1)[i % 3] for i, c in enumerate(data)) % 10)


@dataclass
class Correction:
    line: int
    index: int
    found: str
    used: str
    reason: str

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class MrzResult:
    layout: str
    lines: list[str]                 # after corrections
    original: list[str]              # as received
    fields: dict = field(default_factory=dict)   # name -> {"label", "value", "display"}
    checks: list[Check] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)
    segments: list[dict] = field(default_factory=list)  # for display: line, start, end, field
    number: str = ""                 # document number used for the composite check (after any correction)

    @property
    def status(self) -> str:
        return worst(c.status for c in self.checks)

    def as_dict(self) -> dict:
        return {"layout": self.layout, "lines": self.lines, "original": self.original, "fields": self.fields,
                "checks": [c.as_dict() for c in self.checks], "corrections": [c.as_dict() for c in self.corrections],
                "segments": self.segments, "status": self.status}


# --- Finding the MRZ in text ----------------------------------------------------------

def normalise_line(line: str) -> str:
    line = line.upper().replace("«", "<").replace("‹", "<").replace("〈", "<")
    return re.sub(r"\s+", "", line)


def _looks_like_mrz(line: str) -> bool:
    return len(line) >= 24 and line.count("<") >= 2 and sum(ch.isalnum() or ch == "<" for ch in line) >= len(line) - 2


def find_mrz(text: str) -> list[str] | None:
    """Pick the MRZ lines out of OCR or typed text. Returns 2 or 3 lines, or None."""
    lines = [normalise_line(l) for l in text.splitlines()]
    lines = [l for l in lines if l]
    candidates = [l for l in lines if _looks_like_mrz(l)]
    if len(candidates) >= 3 and all(26 <= len(l) <= 33 for l in candidates[-3:]):
        return candidates[-3:]
    if len(candidates) >= 2:
        return candidates[-2:]
    return None


def detect_layout(lines: list[str]) -> str | None:
    if len(lines) == 3:
        return "TD1"
    if len(lines) == 2:
        longest = max(len(l) for l in lines)
        return "TD3" if longest >= 40 else "TD2" if longest >= 33 else None
    return None


# --- Parsing ------------------------------------------------------------------------------

# Character classes per position: "a" letters/<, "n" digits, "x" any, "c" check digit (digit, or < when allowed)
_CLASSES = {
    "TD3": ["a" * 44,
            "x" * 9 + "n" + "a" * 3 + "n" * 6 + "n" + "a" + "n" * 6 + "n" + "x" * 14 + "c" + "n"],
    "TD2": ["a" * 36,
            "x" * 9 + "n" + "a" * 3 + "n" * 6 + "n" + "a" + "n" * 6 + "n" + "x" * 7 + "n"],
    "TD1": ["aa" + "a" * 3 + "x" * 9 + "c" + "x" * 15,
            "n" * 6 + "n" + "a" + "n" * 6 + "n" + "a" * 3 + "x" * 11 + "n",
            "a" * 30],
}


def _apply_classes(layout: str, lines: list[str], corrections: list[Correction]) -> list[str]:
    fixed = []
    for li, (line, classes) in enumerate(zip(lines, _CLASSES[layout])):
        chars = list(line)
        for i, (ch, cls) in enumerate(zip(chars, classes)):
            if cls == "n" and ch in _TO_DIGIT:
                chars[i] = _TO_DIGIT[ch]
                corrections.append(Correction(li + 1, i + 1, ch, chars[i], "Only a digit is allowed here."))
            elif cls == "a" and ch in _TO_ALPHA:
                chars[i] = _TO_ALPHA[ch]
                corrections.append(Correction(li + 1, i + 1, ch, chars[i], "Only a letter is allowed here."))
        fixed.append("".join(chars))
    return fixed


def _fit_length(layout: str, lines: list[str], checks: list[Check], corrections: list[Correction]) -> list[str] | None:
    count, width = LAYOUTS[layout]
    name_line = 0 if layout in ("TD3", "TD2") else 2
    out = []
    for i, line in enumerate(lines):
        if len(line) == width:
            out.append(line)
        elif i == name_line and len(line) < width:
            # Only trailing "<" fillers can be restored safely: they carry no data.
            missing = width - len(line)
            out.append(line + "<" * missing)
            corrections.append(Correction(i + 1, len(line) + 1, "", "<" * missing,
                                          f"{missing} trailing filler character(s) were missing and were restored."))
        else:
            checks.append(Check("parsing", "mrz.line_length", "Line lengths", FAIL,
                                f"Line {i + 1} has {len(line)} characters; a {layout} line has {width}. "
                                "Characters are missing or extra, so the data can't be placed reliably."))
            return None
    checks.append(Check("parsing", "mrz.line_length", "Line lengths", PASS,
                        f"{count} lines of {width} characters ({layout})."))
    return out


def _date_field(result: MrzResult, name: str, label: str, raw: str, kind: str, today: date):
    value = yymmdd(raw, kind, today)
    result.fields[name] = {"label": label, "value": value.isoformat() if value else raw,
                           "display": nice(value) if value else raw}
    return value


def _check_digit(result: MrzResult, code: str, name: str, data: str, digit: str, positions, allow_filler=False) -> bool:
    expected = check_digit(data)
    if allow_filler and set(data) == {"<"} and digit in ("<", "0"):
        result.checks.append(Check("data_format", code, name, PASS, "Empty field; filler check digit accepted.", positions))
        return True
    ok = digit == expected
    result.checks.append(Check("data_format", code, name, PASS if ok else FAIL,
                               f"Check digit {digit} is correct." if ok else
                               f"Check digit is {digit} but the data gives {expected}. A character was misread or changed.",
                               positions))
    return ok


def _names(field_text: str) -> tuple[str, str, bool]:
    surname, _, given = field_text.partition("<<")
    truncated = not field_text.endswith("<")
    return surname.replace("<", " ").strip(), given.replace("<", " ").strip(), truncated


def _try_fix_number(number: str, digit: str, confirm=None) -> str | None:
    """If the document number fails its check digit, try swapping OCR look-alikes (O/0, I/1, S/5, B/8, Z/2).

    Candidates needing the fewest swaps are preferred. `confirm` (when given) must also accept the
    candidate - the composite check digit, which covers the number again. A fix is returned only
    when exactly one candidate survives; otherwise nothing is guessed."""
    spots = [i for i, ch in enumerate(number) if ch in _AMBIGUOUS]
    if not spots or len(spots) > 8:
        return None
    by_swaps: dict[int, set[str]] = {}
    for choice in product([False, True], repeat=len(spots)):
        if not any(choice):
            continue
        chars = list(number)
        for flip, i in zip(choice, spots):
            if flip:
                chars[i] = _AMBIGUOUS[chars[i]]
        candidate = "".join(chars)
        if check_digit(candidate) == digit and (confirm is None or confirm(candidate)):
            by_swaps.setdefault(sum(choice), set()).add(candidate)
    if not by_swaps:
        return None
    fewest = by_swaps[min(by_swaps)]
    return next(iter(fewest)) if len(fewest) == 1 else None


def parse(raw_lines: list[str], today: date | None = None) -> MrzResult | None:
    """Parse and check an MRZ. Returns None if the text doesn't look like any MRZ layout."""
    today = today or date.today()
    original = [normalise_line(l) for l in raw_lines if normalise_line(l)]
    layout = detect_layout(original)
    if layout is None:
        return None
    result = MrzResult(layout, [], original)

    bad = sorted({c for line in original for c in line if not ("A" <= c <= "Z" or c.isdigit() or c == "<")})
    if bad:
        result.checks.append(Check("parsing", "mrz.characters", "Allowed characters", FAIL,
                                   f"Characters that can't appear in an MRZ were found: {' '.join(bad)}. "
                                   "They usually mean a character was misread or is missing."))
        cleaned = [re.sub(r"[^A-Z0-9<]", "<", l) for l in original]
    else:
        cleaned = original
        result.checks.append(Check("parsing", "mrz.characters", "Allowed characters", PASS, "Only A-Z, 0-9 and < are used."))

    lines = _fit_length(layout, cleaned, result.checks, result.corrections)
    if lines is None:
        result.lines = cleaned
        return result
    lines = _apply_classes(layout, lines, result.corrections)
    result.lines = lines
    {"TD3": _td3, "TD2": _td2, "TD1": _td1}[layout](result, lines, today)

    if result.corrections:
        # A correction inside a passing check digit's range is confirmed by that digit. Others
        # (names, country codes, sex, restored fillers) can't be confirmed, so a person must look.
        confirmed = set()
        for check in result.checks:
            if check.code.startswith("mrz.check_digit") and check.status == PASS and len(check.positions) == 2:
                (line, start), (_, end) = check.positions
                confirmed |= {(line, i) for i in range(start, end + 1)}
        unconfirmed = [c for c in result.corrections if (c.line, c.index) not in confirmed or not c.found]
        result.checks.append(Check(
            "parsing", "mrz.corrections", "Character corrections", REVIEW if unconfirmed else PASS,
            (f"{len(unconfirmed)} correction(s) can't be confirmed by a check digit (for example in names or country "
             "codes). Compare them with the document." if unconfirmed else
             f"{len(result.corrections)} correction(s) made, all confirmed by passing check digits."),
            [(c.line, c.index) for c in unconfirmed or result.corrections]))
    return result


def _common(result: MrzResult, *, confirm=None, doc_type: str, state: str, names: str, number: str, number_digit: str,
            number_pos, nationality: str, birth: str, birth_digit: str, birth_pos, sex: str,
            expiry: str, expiry_digit: str, expiry_pos, today: date):
    surname, given, truncated = _names(names)
    f = result.fields
    f["document_type"] = {"label": "Document type", "value": doc_type.replace("<", ""), "display": doc_type.replace("<", "")}
    f["issuing_state"] = {"label": "Issuing state", "value": state.replace("<", ""), "display": state.replace("<", "")}
    f["surname"] = {"label": "Surname", "value": surname, "display": surname}
    f["given_names"] = {"label": "Given names", "value": given, "display": given}

    if not _check_digit(result, "mrz.check_digit.document_number", "Document number check digit",
                        number, number_digit, number_pos):
        fixed = _try_fix_number(number, number_digit, confirm)
        if fixed:
            for i, (a, b) in enumerate(zip(number, fixed)):
                if a != b:
                    line, start = number_pos[0]
                    result.corrections.append(Correction(line, start + i, a, b, "Look-alike swapped so the check digit passes."))
            result.checks[-1] = Check("data_format", "mrz.check_digit.document_number", "Document number check digit",
                                      REVIEW, f"Passes only if '{number}' is read as '{fixed}'. Confirm the document number "
                                              "on the document.", number_pos)
            number = fixed
    result.number = number
    clean_number = number.replace("<", "")
    f["document_number"] = {"label": "Document number", "value": clean_number, "display": clean_number}
    f["nationality"] = {"label": "Nationality", "value": nationality.replace("<", ""), "display": nationality.replace("<", "")}

    born = _date_field(result, "birth_date", "Date of birth", birth, "birth", today)
    _check_digit(result, "mrz.check_digit.birth_date", "Date of birth check digit", birth, birth_digit, birth_pos)
    f["sex"] = {"label": "Sex", "value": sex, "display": {"M": "Male", "F": "Female", "X": "Unspecified", "<": "Unspecified"}.get(sex, sex)}
    expires = _date_field(result, "expiry_date", "Date of expiry", expiry, "expiry", today)
    _check_digit(result, "mrz.check_digit.expiry_date", "Date of expiry check digit", expiry, expiry_digit, expiry_pos)

    c = result.checks
    c.append(Check("dates", "mrz.birth_date.valid", "Date of birth is a real past date",
                   PASS if born and born <= today else FAIL,
                   f"Born {nice(born)}." if born and born <= today else
                   f"'{birth}' is not a real date." if not born else "The date of birth is in the future."))
    if not expires:
        c.append(Check("dates", "mrz.expiry_date.valid", "Date of expiry is a real date", FAIL, f"'{expiry}' is not a real date."))
    else:
        if born and expires <= born:
            c.append(Check("dates", "mrz.expiry_after_birth", "Expiry is after birth", FAIL,
                           "The expiry date is before the date of birth."))
        c.append(Check("dates", "mrz.not_expired", "Document has not expired", PASS if expires >= today else FAIL,
                       f"Valid until {nice(expires)}." if expires >= today else f"Expired on {nice(expires)}."))
    c.append(Check("data_format", "mrz.sex", "Sex code", PASS if sex in "MFX<" else FAIL,
                   "Valid code." if sex in "MFX<" else f"'{sex}' is not M, F, X or <."))
    codes_ok = all(re.fullmatch(r"[A-Z<]{3}", v) for v in (state, nationality))
    note = " UTO is ICAO's fictional specimen state, used on sample documents." if SPECIMEN_STATE in (state, nationality) else ""
    c.append(Check("data_format", "mrz.state_codes", "Country codes", PASS if codes_ok else FAIL,
                   ("Issuing state and nationality are three-letter codes." if codes_ok else
                    "Issuing state or nationality is not a three-letter code.") + note))
    c.append(Check("data_format", "mrz.surname_present", "Surname present", PASS if surname else FAIL,
                   "Present." if surname else "The name field has no surname before '<<'."))
    if truncated:
        c.append(Check("data_format", "mrz.name_truncated", "Name fits the field", REVIEW,
                       "The name fills the whole field, so it may have been shortened. Compare with the printed name."))


def _td3(result: MrzResult, l: list[str], today: date):
    l1, l2 = l
    result.segments = [
        {"line": 1, "start": 0, "end": 2, "field": "document_type"}, {"line": 1, "start": 2, "end": 5, "field": "issuing_state"},
        {"line": 1, "start": 5, "end": 44, "field": "name"},
        {"line": 2, "start": 0, "end": 9, "field": "document_number"}, {"line": 2, "start": 9, "end": 10, "field": "check"},
        {"line": 2, "start": 10, "end": 13, "field": "nationality"}, {"line": 2, "start": 13, "end": 19, "field": "birth_date"},
        {"line": 2, "start": 19, "end": 20, "field": "check"}, {"line": 2, "start": 20, "end": 21, "field": "sex"},
        {"line": 2, "start": 21, "end": 27, "field": "expiry_date"}, {"line": 2, "start": 27, "end": 28, "field": "check"},
        {"line": 2, "start": 28, "end": 42, "field": "optional_data"}, {"line": 2, "start": 42, "end": 43, "field": "check"},
        {"line": 2, "start": 43, "end": 44, "field": "check"},
    ]
    composite_ok = lambda n: check_digit(n + l2[9] + l2[13:20] + l2[21:43]) == l2[43]
    _common(result, confirm=composite_ok, doc_type=l1[0:2], state=l1[2:5], names=l1[5:44], number=l2[0:9], number_digit=l2[9],
            number_pos=[(2, 1), (2, 10)], nationality=l2[10:13], birth=l2[13:19], birth_digit=l2[19],
            birth_pos=[(2, 14), (2, 20)], sex=l2[20], expiry=l2[21:27], expiry_digit=l2[27],
            expiry_pos=[(2, 22), (2, 28)], today=today)
    optional = l2[28:42]
    result.fields["optional_data"] = {"label": "Personal number / optional data", "value": optional.replace("<", ""),
                                      "display": optional.replace("<", "") or "None"}
    _check_digit(result, "mrz.check_digit.optional_data", "Optional data check digit", optional, l2[42],
                 [(2, 29), (2, 43)], allow_filler=True)
    _check_digit(result, "mrz.check_digit.composite", "Composite check digit",
                 result.number + l2[9] + l2[13:20] + l2[21:43], l2[43], [(2, 44)])
    if not l1.startswith("P"):
        result.checks.append(Check("parsing", "mrz.document_type", "Passport type code", REVIEW,
                                   f"A 44-character MRZ normally starts with P; this starts with {l1[0]}."))


def _td2(result: MrzResult, l: list[str], today: date):
    l1, l2 = l
    result.segments = [
        {"line": 1, "start": 0, "end": 2, "field": "document_type"}, {"line": 1, "start": 2, "end": 5, "field": "issuing_state"},
        {"line": 1, "start": 5, "end": 36, "field": "name"},
        {"line": 2, "start": 0, "end": 9, "field": "document_number"}, {"line": 2, "start": 9, "end": 10, "field": "check"},
        {"line": 2, "start": 10, "end": 13, "field": "nationality"}, {"line": 2, "start": 13, "end": 19, "field": "birth_date"},
        {"line": 2, "start": 19, "end": 20, "field": "check"}, {"line": 2, "start": 20, "end": 21, "field": "sex"},
        {"line": 2, "start": 21, "end": 27, "field": "expiry_date"}, {"line": 2, "start": 27, "end": 28, "field": "check"},
        {"line": 2, "start": 28, "end": 35, "field": "optional_data"}, {"line": 2, "start": 35, "end": 36, "field": "check"},
    ]
    composite_ok = lambda n: check_digit(n + l2[9] + l2[13:20] + l2[21:35]) == l2[35]
    _common(result, confirm=composite_ok, doc_type=l1[0:2], state=l1[2:5], names=l1[5:36], number=l2[0:9], number_digit=l2[9],
            number_pos=[(2, 1), (2, 10)], nationality=l2[10:13], birth=l2[13:19], birth_digit=l2[19],
            birth_pos=[(2, 14), (2, 20)], sex=l2[20], expiry=l2[21:27], expiry_digit=l2[27],
            expiry_pos=[(2, 22), (2, 28)], today=today)
    result.fields["optional_data"] = {"label": "Optional data", "value": l2[28:35].replace("<", ""),
                                      "display": l2[28:35].replace("<", "") or "None"}
    _check_digit(result, "mrz.check_digit.composite", "Composite check digit",
                 result.number + l2[9] + l2[13:20] + l2[21:35], l2[35], [(2, 36)])


def _td1(result: MrzResult, l: list[str], today: date):
    l1, l2, l3 = l
    number, digit, optional1 = l1[5:14], l1[14], l1[15:30]
    number_pos = [(1, 6), (1, 15)]
    if digit == "<" and optional1.strip("<"):
        # Long document numbers continue in the optional field; the last character before "<" is the check digit.
        rest = optional1.split("<", 1)[0]
        number, digit = number + rest[:-1], rest[-1]
        number_pos = [(1, 6), (1, 16 + len(rest) - 1)]
        optional1 = optional1[len(rest):]
    result.segments = [
        {"line": 1, "start": 0, "end": 2, "field": "document_type"}, {"line": 1, "start": 2, "end": 5, "field": "issuing_state"},
        {"line": 1, "start": 5, "end": 14, "field": "document_number"}, {"line": 1, "start": 14, "end": 15, "field": "check"},
        {"line": 1, "start": 15, "end": 30, "field": "optional_data"},
        {"line": 2, "start": 0, "end": 6, "field": "birth_date"}, {"line": 2, "start": 6, "end": 7, "field": "check"},
        {"line": 2, "start": 7, "end": 8, "field": "sex"}, {"line": 2, "start": 8, "end": 14, "field": "expiry_date"},
        {"line": 2, "start": 14, "end": 15, "field": "check"}, {"line": 2, "start": 15, "end": 18, "field": "nationality"},
        {"line": 2, "start": 18, "end": 29, "field": "optional_data"}, {"line": 2, "start": 29, "end": 30, "field": "check"},
        {"line": 3, "start": 0, "end": 30, "field": "name"},
    ]
    _common(result, doc_type=l1[0:2], state=l1[2:5], names=l3, number=number, number_digit=digit,
            number_pos=number_pos, nationality=l2[15:18], birth=l2[0:6], birth_digit=l2[6], birth_pos=[(2, 1), (2, 7)],
            sex=l2[7], expiry=l2[8:14], expiry_digit=l2[14], expiry_pos=[(2, 9), (2, 15)], today=today)
    optional = (optional1 + l2[18:29]).replace("<", "")
    result.fields["optional_data"] = {"label": "Optional data", "value": optional, "display": optional or "None"}
    _check_digit(result, "mrz.check_digit.composite", "Composite check digit",
                 l1[5:30] + l2[0:7] + l2[8:15] + l2[18:29], l2[29], [(2, 30)])
