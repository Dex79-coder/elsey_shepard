from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, List, Dict, Any
import json

# -----------------------------
# Date helpers (stdlib only)
# -----------------------------
DATE_FORMATS = [
    "%Y-%m-%d",  # 2025-08-30
    "%d/%m/%Y",  # 30/08/2025 (BR)
    "%d-%m-%Y",  # 30-08-2025
    "%Y/%m/%d",  # 2025/08/30
    "%m/%d/%Y",  # 08/30/2025 (US)
]

def parse_date(s: Optional[str]) -> Optional[date]:
    """Parse many common date formats. Returns None if missing/invalid.
    IMPORTANT: If only a year is provided (e.g., "1890"), we return None
    to avoid guessing months/days—so ages won't be computed without full dates.
    """
    if not s:
        return None
    s = s.strip()
    if s.isdigit() and len(s) == 4:
        return None  # don't guess
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def years_between(start: date, end: date) -> int:
    years = end.year - start.year
    if (end.month, end.day) < (start.month, start.day):
        years -= 1
    return years

def safe_age(birth: Optional[date], event: Optional[date]) -> Optional[int]:
    if birth and event and event >= birth:
        return years_between(birth, event)
    return None

# -----------------------------
# Core data structures
# -----------------------------
@dataclass
class DeathRecord:
    name: str
    death_date: Optional[date] = None
    death_place: Optional[str] = None
    age_at_death: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "death_date": self.death_date.isoformat() if self.death_date else None,
            "death_place": self.death_place,
            "age_at_death": self.age_at_death,
        }

@dataclass
class SpouseRecord:
    """A spouse is a distinct person to avoid mixing data.
    We keep their own birth/death so computations stay coherent.
    """
    name: str
    birth_date: Optional[date] = None
    birth_place: Optional[str] = None
    death: Optional[DeathRecord] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "birth_date": self.birth_date.isoformat() if self.birth_date else None,
            "birth_place": self.birth_place,
            "death": self.death.to_dict() if self.death else None,
        }

@dataclass
class Marriage:
    spouse: SpouseRecord
    marriage_date: Optional[date] = None
    marriage_place: Optional[str] = None
    estimated_children: Optional[int] = None
    age_person_at_marriage: Optional[int] = None
    age_spouse_at_marriage: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spouse": self.spouse.to_dict(),
            "marriage_date": self.marriage_date.isoformat() if self.marriage_date else None,
            "marriage_place": self.marriage_place,
            "estimated_children": self.estimated_children,
            "age_person_at_marriage": self.age_person_at_marriage,
            "age_spouse_at_marriage": self.age_spouse_at_marriage,
        }

@dataclass
class Person:
    # Identificação e nascimento
    name: str
    birth_date: Optional[date] = None
    birth_place: Optional[str] = None

    # Filiação
    father_name: Optional[str] = None
    mother_name: Optional[str] = None

    # Casamentos
    marriages: List[Marriage] = field(default_factory=list)

    # Óbito
    death: Optional[DeathRecord] = None

    # ---- Factories / Mutators ----
    @staticmethod
    def from_raw(
        name: str,
        birth_date: Optional[str] = None,
        birth_place: Optional[str] = None,
        father_name: Optional[str] = None,
        mother_name: Optional[str] = None,
    ) -> "Person":
        return Person(
            name=name.strip(),
            birth_date=parse_date(birth_date),
            birth_place=(birth_place or None),
            father_name=(father_name or None),
            mother_name=(mother_name or None),
        )

    def add_marriage(
        self,
        spouse_name: str,
        spouse_birth_date: Optional[str] = None,
        spouse_birth_place: Optional[str] = None,
        marriage_date: Optional[str] = None,
        marriage_place: Optional[str] = None,
        estimated_children: Optional[int] = None,
    ) -> Marriage:
        spouse = SpouseRecord(
            name=spouse_name.strip(),
            birth_date=parse_date(spouse_birth_date),
            birth_place=(spouse_birth_place or None),
        )
        mdate = parse_date(marriage_date)
        marriage = Marriage(
            spouse=spouse,
            marriage_date=mdate,
            marriage_place=(marriage_place or None),
            estimated_children=estimated_children,
        )
        # Idade dos noivos ao casar
        marriage.age_person_at_marriage = safe_age(self.birth_date, mdate)
        marriage.age_spouse_at_marriage = safe_age(spouse.birth_date, mdate)
        self.marriages.append(marriage)
        return marriage

    def set_death(self, death_date: Optional[str] = None, death_place: Optional[str] = None):
        ddate = parse_date(death_date)
        self.death = DeathRecord(
            name=self.name,
            death_date=ddate,
            death_place=(death_place or None),
            age_at_death=safe_age(self.birth_date, ddate),
        )

    def set_spouse_death(self, spouse_index: int, death_date: Optional[str] = None, death_place: Optional[str] = None):
        """Registra o óbito de uma esposa específico pela posição na lista de casamentos."""
        if spouse_index < 0 or spouse_index >= len(self.marriages):
            raise IndexError("spouse_index fora do intervalo")
        marriage = self.marriages[spouse_index]
        ddate = parse_date(death_date)
        marriage.spouse.death = DeathRecord(
            name=marriage.spouse.name,
            death_date=ddate,
            death_place=(death_place or None),
            age_at_death=safe_age(marriage.spouse.birth_date, ddate),
        )

    # ---- Serialization ----
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "birth_date": self.birth_date.isoformat() if self.birth_date else None,
            "birth_place": self.birth_place,
            "father_name": self.father_name,
            "mother_name": self.mother_name,
            "marriages": [m.to_dict() for m in self.marriages],
            "death": self.death.to_dict() if self.death else None,
        }

# -----------------------------
# Utilities
# -----------------------------

def collect_deaths(people: List[Person]) -> List[DeathRecord]:
    """Lista todos os óbitos (pessoa e esposas) em ordem cronológica (mais antigo → mais recente)."""
    deaths: List[DeathRecord] = []
    for p in people:
        if p.death and p.death.death_date:
            deaths.append(p.death)
        for m in p.marriages:
            if m.spouse.death and m.spouse.death.death_date:
                deaths.append(m.spouse.death)
    deaths.sort(key=lambda d: d.death_date)
    return deaths

def validate_coherence(people: List[Person]) -> List[str]:
    """Regras básicas para não misturar dados e manter coerência temporal."""
    issues: List[str] = []
    for p in people:
        # birth/death order
        if p.death and p.birth_date and p.death.death_date and p.death.death_date < p.birth_date:
            issues.append(f"Death before birth for {p.name}")
        for idx, m in enumerate(p.marriages):
            # casamento não pode ser antes do nascimento (pessoa ou cônjuge)
            if m.marriage_date and p.birth_date and m.marriage_date < p.birth_date:
                issues.append(f"Marriage before birth for {p.name} (marriage #{idx+1})")
            if m.marriage_date and m.spouse.birth_date and m.marriage_date < m.spouse.birth_date:
                issues.append(f"Marriage before birth for spouse {m.spouse.name} (marriage #{idx+1})")
            # casamento não pode ser após óbito
            if p.death and m.marriage_date and p.death.death_date and m.marriage_date > p.death.death_date:
                issues.append(f"Marriage after death for {p.name} (marriage #{idx+1})")
            if m.spouse.death and m.marriage_date and m.spouse.death.death_date and m.marriage_date > m.spouse.death.death_date:
                issues.append(f"Marriage after spouse death for {m.spouse.name} (marriage #{idx+1})")
    return issues

def export_json(people: List[Person], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([p.to_dict() for p in people], f, ensure_ascii=False, indent=2)

# -----------------------------
# Demo de uso (execute este arquivo no PyCharm)
# -----------------------------
if __name__ == "__main__":
    # Pessoa de exemplo
    william = Person.from_raw(
        name="William R Shepard",
        birth_date="1823-03-01",
        birth_place="Smyth County, Virginia, USA",
        father_name="John Shepherd",
        mother_name="Cecelia Scoggins",
    )

    # Casamento 1 (exemplo com cônjuge e cálculo de idade ao casar)
    m1 = william.add_marriage(
        spouse_name="Asseneth Lucinda Chenault",
        spouse_birth_date="1822-06-01",
        spouse_birth_place="Virginia, USA",
        marriage_date="1844-06-01",
        marriage_place="Rich Valley, Smyth County, Virginia, USA",
        estimated_children=8,
    )

    # Óbitos (pessoa e cônjuge), com cálculo automático de idade ao falecer
    william.set_death("1890-01-01", "Tazewell County, Virginia, USA")
    william.set_spouse_death(0, "1899-01-01", "Tazewell County, Virginia, USA")

    # Conjunto de pessoas
    people = [william]

    # Validação de coerência
    issues = validate_coherence(people)
    if issues:
        print("Coherence warnings:")
        for msg in issues:
            print(" -", msg)

    # Lista de óbitos em ordem cronológica
    print("\nDeaths (oldest to most recent):")
    for d in collect_deaths(people):
        print(f"{d.name} — {d.death_date} — {d.death_place} — age {d.age_at_death}")

    # Exporta JSON normalizado
    export_json(people, "people_export.json")
    print("\nExported to people_export.json")