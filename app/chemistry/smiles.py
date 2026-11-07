"""A SMILES parser that produces an explicit molecular graph.

This implements the subset of the OpenSMILES specification that covers drug-like
small molecules: organic subset atoms, bracket atoms with charges/isotopes/
explicit hydrogens, aromatic lowercase symbols, ring-closure bonds, branches,
multiple and aromatic bonds, dot-disconnected fragments, and stereochemistry
markers (parsed but retained as annotations only -- this engine does not do
3D stereodescriptor assignment).

Anything outside that subset raises `SmilesError` with the character offset, so
a user pasting a malformed structure gets told exactly where it broke instead
of a generic failure.

The parser is deterministic and has no dependencies beyond the standard
library, which is the whole point: the numbers this project reports must be
reproducible from the source without trusting a black box.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .elements import (
    AROMATIC_LOWER,
    DEFAULT_VALENCE,
    ORGANIC_SUBSET,
)

# Bond types, stored numerically so ordering and comparison behave predictably.
BOND_SINGLE = 1.0
BOND_DOUBLE = 2.0
BOND_TRIPLE = 3.0
BOND_AROMATIC = 1.5

BOND_SYMBOLS: dict[float, str] = {
    BOND_SINGLE: "-",
    BOND_DOUBLE: "=",
    BOND_TRIPLE: "#",
    BOND_AROMATIC: ":",
}


class SmilesError(ValueError):
    """Raised when a SMILES string cannot be parsed.

    Carries the zero-based character offset so the caller can point at the
    offending position in the input.
    """

    def __init__(self, message: str, position: int) -> None:
        self.position = position
        super().__init__(f"{message} (at character {position + 1})")


@dataclass
class Atom:
    """One atom in the parsed graph.

    `bracket_hydrogens` is the H count written inside brackets (or -1 when the
    atom was written outside brackets, meaning "infer from valence").
    `implicit_hydrogens` is filled in by `_assign_hydrogens`.
    """

    index: int
    symbol: str
    aromatic: bool = False
    charge: int = 0
    isotope: int | None = None
    bracket_hydrogens: int = -1
    chiral: str | None = None
    implicit_hydrogens: int = 0
    is_wildcard: bool = False

    @property
    def total_hydrogens(self) -> int:
        return self.implicit_hydrogens


@dataclass
class Bond:
    """An undirected bond between two atom indices."""

    a: int
    b: int
    order: float

    def other(self, index: int) -> int:
        return self.b if index == self.a else self.a


@dataclass
class Molecule:
    """A parsed molecule: atoms, bonds, and the original SMILES string."""

    smiles: str
    atoms: list[Atom] = field(default_factory=list)
    bonds: list[Bond] = field(default_factory=list)

    def adjacency(self) -> list[list[tuple[int, float]]]:
        """Return neighbour lists as (neighbour_index, bond_order) pairs."""
        adj: list[list[tuple[int, float]]] = [[] for _ in self.atoms]
        for bond in self.bonds:
            adj[bond.a].append((bond.b, bond.order))
            adj[bond.b].append((bond.a, bond.order))
        return adj

    def bond_order_sum(self, index: int) -> float:
        return sum(order for _, order in self.adjacency()[index])

    def formula_counts(self) -> dict[str, int]:
        """Element counts including implicit and explicit hydrogens."""
        counts: dict[str, int] = {}
        for atom in self.atoms:
            if atom.is_wildcard:
                continue
            counts[atom.symbol] = counts.get(atom.symbol, 0) + 1
            if atom.total_hydrogens:
                counts["H"] = counts.get("H", 0) + atom.total_hydrogens
        return counts

    def heavy_atom_count(self) -> int:
        return sum(1 for atom in self.atoms if not atom.is_wildcard)


class _Parser:
    """Single-use recursive-descent-ish parser driven by an index cursor."""

    def __init__(self, smiles: str) -> None:
        self.smiles = smiles
        self.pos = 0
        self.atoms: list[Atom] = []
        self.bonds: list[Bond] = []
        # Ring-closure bonds keyed by ring number -> (atom_index, bond_order,
        # position) so we can report where an unmatched ring digit came from.
        self.open_rings: dict[int, tuple[int, float, int]] = {}
        self.pending_bond: float | None = None
        self.prev_atom: int | None = None
        # Atoms whose aromaticity was written in brackets or lowercase.
        self.aromatic_flags: list[bool] = []

    # -- token helpers ---------------------------------------------------

    def _peek(self) -> str:
        return self.smiles[self.pos] if self.pos < len(self.smiles) else ""

    def _advance(self, count: int = 1) -> None:
        self.pos += count

    # -- atom parsing ----------------------------------------------------

    def _parse_atom(self) -> int:
        char = self._peek()
        if char == "[":
            return self._parse_bracket_atom()
        if char in AROMATIC_LOWER:
            return self._parse_aromatic_atom()
        return self._parse_organic_atom()

    def _parse_organic_atom(self) -> int:
        start = self.pos
        char = self._peek()
        symbol = ""

        # Two-letter organic symbols (Cl, Br) must be tried first.
        two = self.smiles[self.pos : self.pos + 2]
        if two in ("Cl", "Br"):
            symbol = two
            self._advance(2)
        elif char in ORGANIC_SUBSET:
            symbol = char
            self._advance(1)
        else:
            raise SmilesError(f"unexpected character {char!r} where an atom was expected", start)

        index = len(self.atoms)
        self.atoms.append(Atom(index=index, symbol=symbol, bracket_hydrogens=-1))
        self.aromatic_flags.append(False)
        return index

    def _parse_aromatic_atom(self) -> int:
        char = self._peek()
        symbol = AROMATIC_LOWER[char]
        self._advance(1)

        index = len(self.atoms)
        self.atoms.append(Atom(index=index, symbol=symbol, aromatic=True, bracket_hydrogens=-1))
        self.aromatic_flags.append(True)
        return index

    def _parse_bracket_atom(self) -> int:
        start = self.pos
        self._advance(1)  # consume '['

        isotope = None
        isotope_digits = ""
        while self._peek().isdigit():
            isotope_digits += self._peek()
            self._advance(1)
        if isotope_digits:
            isotope = int(isotope_digits)

        aromatic = False
        symbol = ""
        char = self._peek()
        if char in AROMATIC_LOWER:
            symbol = AROMATIC_LOWER[char]
            aromatic = True
            self._advance(1)
        elif char.isupper():
            two = self.smiles[self.pos : self.pos + 2]
            if len(two) == 2 and two[0].isupper() and two[1].islower() and two in DEFAULT_SET:
                symbol = two
                self._advance(2)
            else:
                symbol = char
                self._advance(1)
        elif char == "*":
            symbol = "*"
            self._advance(1)
        else:
            raise SmilesError("bracket atom is missing an element symbol", start)

        # Chirality: @ or @@
        chiral = None
        if self._peek() == "@":
            chiral = "@"
            self._advance(1)
            if self._peek() == "@":
                chiral = "@@"
                self._advance(1)

        # Explicit hydrogens: H followed by an optional count.
        bracket_h = 0
        if self._peek() == "H":
            self._advance(1)
            digits = ""
            while self._peek().isdigit():
                digits += self._peek()
                self._advance(1)
            bracket_h = int(digits) if digits else 1

        # Charge: '+', '-', '++', '--', '+2', '-3'
        charge = 0
        char = self._peek()
        # `char` must be tested for emptiness first: in Python `"" in "+-"` is
        # True, so an unclosed bracket would enter this branch, advance nothing,
        # and spin forever.
        if char and char in "+-":
            sign = 1 if char == "+" else -1
            self._advance(1)
            digits = ""
            while self._peek().isdigit():
                digits += self._peek()
                self._advance(1)
            if digits:
                charge = sign * int(digits)
            else:
                repeats = 1
                while self._peek() == char:
                    repeats += 1
                    self._advance(1)
                charge = sign * repeats

        # Atom class (e.g. [C:1]) -- accepted and ignored.
        if self._peek() == ":":
            self._advance(1)
            while self._peek().isdigit():
                self._advance(1)

        if self._peek() != "]":
            raise SmilesError("bracket atom is not closed with ']'", self.pos)
        self._advance(1)

        index = len(self.atoms)
        self.atoms.append(
            Atom(
                index=index,
                symbol=symbol,
                aromatic=aromatic,
                charge=charge,
                isotope=isotope,
                bracket_hydrogens=bracket_h,
                chiral=chiral,
                is_wildcard=(symbol == "*"),
            )
        )
        self.aromatic_flags.append(aromatic)
        return index

    # -- bond parsing ----------------------------------------------------

    def _parse_bond(self) -> float | None:
        char = self._peek()
        if char == "-":
            self._advance(1)
            return BOND_SINGLE
        if char == "=":
            self._advance(1)
            return BOND_DOUBLE
        if char == "#":
            self._advance(1)
            return BOND_TRIPLE
        if char == ":":
            self._advance(1)
            return BOND_AROMATIC
        if char == "/":
            self._advance(1)
            return BOND_SINGLE
        if char == "\\":
            self._advance(1)
            return BOND_SINGLE
        return None

    # -- graph assembly --------------------------------------------------

    def _connect(self, a: int, b: int, order: float) -> None:
        if a == b:
            raise SmilesError("an atom cannot bond to itself", self.pos)
        for bond in self.bonds:
            if {bond.a, bond.b} == {a, b}:
                raise SmilesError("two atoms are connected by more than one bond", self.pos)
        self.bonds.append(Bond(a=a, b=b, order=order))

    def _handle_ring_closure(self, number: int, order: float | None, atom: int | None) -> None:
        """Open or close a ring bond from `atom`.

        `atom` is the atom the ring digit follows -- the parser's current parent,
        not a separately tracked "previous atom", so a ring digit after a branch
        closes from the branch's last atom as the specification requires.
        """
        if atom is None:
            raise SmilesError("ring closure digit with no preceding atom", self.pos)

        if number in self.open_rings:
            other, stored_order, _opened_at = self.open_rings.pop(number)
            if order is not None and stored_order != BOND_SINGLE and order != stored_order:
                raise SmilesError(
                    f"ring closure {number} specifies two different bond orders", self.pos
                )
            if order is not None:
                effective = order
            elif stored_order != BOND_SINGLE:
                effective = stored_order
            elif self.atoms[other].aromatic and self.atoms[atom].aromatic:
                # Both ends are aromatic and neither digit specified an order:
                # this is an aromatic ring bond, exactly as it would be in the
                # linear case. Without this the ring closes as a single bond and
                # every carbon in it gains a spurious hydrogen.
                effective = BOND_AROMATIC
            else:
                effective = BOND_SINGLE
            self._connect(other, atom, effective)
        else:
            self.open_rings[number] = (
                atom,
                order if order is not None else BOND_SINGLE,
                self.pos,
            )

    def parse(self) -> Molecule:
        if not self.smiles or not self.smiles.strip():
            raise SmilesError("the SMILES string is empty", 0)

        # A leading bond symbol is legal in SMILES but meaningless here.
        leading = self._parse_bond()
        if leading is not None:
            self.pending_bond = leading

        # `parent` is the atom the next atom will bond to. A branch `(` pushes
        # the current atom and starts a new branch from it; `)` pops back, so
        # the main chain resumes from where the branch started. Without this a
        # string like CC(=O)O bonds O to O instead of branching off the carbonyl
        # carbon.
        parent: int | None = None
        branch_stack: list[tuple[int | None, float | None]] = []

        while self.pos < len(self.smiles):
            char = self._peek()
            position_before = self.pos

            if char == "(":
                self._advance(1)
                branch_stack.append((parent, self.pending_bond))
                self.pending_bond = None
                continue
            if char == ")":
                if not branch_stack:
                    raise SmilesError("unmatched ')' with no open branch", self.pos)
                self._advance(1)
                parent, _saved_bond = branch_stack.pop()
                self.pending_bond = None
                continue
            if char.isspace():
                # Whitespace is not legal inside a SMILES string, but silently
                # skipping it is friendlier than failing, and it must advance
                # the cursor or the loop spins.
                self._advance(1)
                continue
            if char in "-=#:/\\":
                order = self._parse_bond()
                if order is not None:
                    self.pending_bond = order
                continue
            if char == ".":
                # Must be tested before the bond-symbol branch: '.' is not a
                # bond, and _parse_bond would return None without advancing the
                # cursor, spinning forever.
                self._advance(1)
                parent = None
                self.pending_bond = None
                continue
            if char.isdigit() or char == "%":
                ring_number = self._parse_ring_number()
                order = self.pending_bond
                self.pending_bond = None
                self._handle_ring_closure(ring_number, order, parent)
                continue
            if char == ">":
                # Reaction SMILES are out of scope; say so explicitly.
                raise SmilesError(
                    "reaction SMILES (containing '>') are not supported by this parser",
                    self.pos,
                )

            # Otherwise it must be an atom.
            atom_index = self._parse_atom()

            if parent is not None:
                order = self.pending_bond
                if order is None:
                    # Aromatic-aromatic bonds default to aromatic; everything
                    # else defaults to a single bond.
                    if self.atoms[atom_index].aromatic and self.atoms[parent].aromatic:
                        order = BOND_AROMATIC
                    else:
                        order = BOND_SINGLE
                self._connect(parent, atom_index, order)

            parent = atom_index
            self.pending_bond = None

            # Safety net: every branch above must consume at least one
            # character. If one ever does not, fail loudly instead of hanging
            # the request -- an infinite loop in a parser is far worse than an
            # error, because it takes the whole worker down with it.
            if self.pos == position_before:
                raise SmilesError(f"parser made no progress at {char!r}; this is a bug", self.pos)

        if branch_stack:
            raise SmilesError(f"{len(branch_stack)} unclosed branch(es) -- missing ')'", self.pos)

        if self.open_rings:
            numbers = ", ".join(str(n) for n in sorted(self.open_rings))
            raise SmilesError(f"unclosed ring bond(s): {numbers}", self.pos)

        molecule = Molecule(smiles=self.smiles, atoms=self.atoms, bonds=self.bonds)
        _assign_hydrogens(molecule)
        return molecule

    def _parse_ring_number(self) -> int:
        char = self._peek()
        if char == "%":
            self._advance(1)
            digits = self.smiles[self.pos : self.pos + 2]
            if len(digits) != 2 or not digits.isdigit():
                raise SmilesError("% ring numbers need exactly two digits", self.pos)
            self._advance(2)
            return int(digits)
        self._advance(1)
        return int(char)


def _assign_hydrogens(molecule: Molecule) -> None:
    """Fill in `implicit_hydrogens` for every atom.

    Bracket atoms keep the count written by the user. Organic-subset atoms get
    hydrogens equal to (target valence - sum of bond orders), floored at zero,
    with the target adjusted for charge and aromaticity:

    * Aromatic carbon in an aromatic ring: bond-order sum is 3 (one double,
      one single) so a bare aromatic carbon correctly gets 1 hydrogen.
    * Aromatic nitrogen written lowercase ordinarily gets 0 (pyridine-like),
      unless it is written as [nH].
    * Charged atoms shift the target by the charge for the common cases
      (quaternary N gets 4, carboxylate O gets 0, etc.).
    """
    adjacency = molecule.adjacency()

    for atom in molecule.atoms:
        if atom.bracket_hydrogens >= 0:
            atom.implicit_hydrogens = 0
            continue

        if atom.is_wildcard:
            atom.implicit_hydrogens = 0
            continue

        valence = DEFAULT_VALENCE.get(atom.symbol)
        if valence is None:
            atom.implicit_hydrogens = 0
            continue

        bond_sum = sum(order for _, order in adjacency[atom.index])

        if atom.aromatic:
            if atom.symbol == "C":
                target = 4
                # An aromatic carbon already carries ~3 in bond orders; the
                # remainder is its one hydrogen.
                h = max(0, round(target - bond_sum))
                atom.implicit_hydrogens = h
                continue
            if atom.symbol in ("N", "P"):
                atom.implicit_hydrogens = 0
                continue
            if atom.symbol in ("O", "S"):
                atom.implicit_hydrogens = 0
                continue
            atom.implicit_hydrogens = max(0, round(valence - bond_sum))
            continue

        target = valence
        if atom.charge != 0:
            if atom.symbol == "N":
                target = 4 if atom.charge > 0 else 2
            elif atom.symbol == "O":
                target = 1 if atom.charge > 0 else 1
            elif atom.symbol == "C":
                target = 3 if atom.charge != 0 else 4
            elif atom.symbol == "S":
                target = valence

        hydrogens = round(target - bond_sum)
        atom.implicit_hydrogens = max(0, hydrogens)


# Element symbols with a lowercase second letter, used to disambiguate
# bracket atoms such as [Cl] from [C] followed by 'l'.
DEFAULT_SET = frozenset(
    {
        "He",
        "Li",
        "Be",
        "Ne",
        "Na",
        "Mg",
        "Al",
        "Si",
        "Cl",
        "Ar",
        "Ca",
        "Sc",
        "Ti",
        "Cr",
        "Mn",
        "Fe",
        "Co",
        "Ni",
        "Cu",
        "Zn",
        "Ga",
        "Ge",
        "As",
        "Se",
        "Br",
        "Kr",
        "Rb",
        "Sr",
        "Zr",
        "Nb",
        "Mo",
        "Ru",
        "Rh",
        "Pd",
        "Ag",
        "Cd",
        "In",
        "Sn",
        "Sb",
        "Te",
        "Xe",
        "Cs",
        "Ba",
        "La",
        "Ce",
        "Pr",
        "Nd",
        "Sm",
        "Eu",
        "Gd",
        "Tb",
        "Dy",
        "Ho",
        "Er",
        "Tm",
        "Yb",
        "Lu",
        "Hf",
        "Ta",
        "Re",
        "Os",
        "Ir",
        "Pt",
        "Au",
        "Hg",
        "Tl",
        "Pb",
        "Bi",
        "Th",
        "U",
    }
)


def parse_smiles(smiles: str) -> Molecule:
    """Parse a SMILES string into a `Molecule`.

    Raises:
        SmilesError: with a character offset describing what went wrong.
    """
    return _Parser(smiles).parse()
