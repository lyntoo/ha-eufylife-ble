"""Body composition metrics calculator for EufyLife BLE scales.

Formulas calibrated against the EufyLife official app using empirical data.
Uses weight (kg), bioelectrical impedance (Ohms from Eufy scale), and
user profile (age, height, sex) to estimate body composition metrics.

The core LBM (lean body mass) formula uses standard BIA approach
(height^2 / impedance) with coefficients calibrated to match Eufy app output.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UserProfile:
    """User profile for body composition calculations."""

    age: int
    height: float  # cm
    sex: str  # "male" or "female"


@dataclass(frozen=True)
class BodyCompositionResult:
    """Result of body composition calculations."""

    bmi: float
    body_fat: float
    muscle_mass: float
    bone_mass: float
    water_percentage: float
    visceral_fat: float
    bmr: float
    metabolic_age: int
    protein_percentage: float
    ideal_weight: float
    body_type: str
    lean_body_mass: float


# Body type classification based on fat percentage and muscle mass
BODY_TYPES = [
    "Obese",
    "Overweight",
    "Thick-set",
    "Lack-exercise",
    "Balanced",
    "Balanced-muscular",
    "Skinny",
    "Balanced-skinny",
    "Skinny-muscular",
]


class BodyMetricsCalculator:
    """Calculate body composition metrics from weight, impedance, and user profile."""

    def __init__(
        self, weight: float, impedance: float, profile: UserProfile
    ) -> None:
        """Initialize the calculator."""
        self.weight = weight
        self.impedance = impedance
        self.height = profile.height
        self.age = profile.age
        self.sex = profile.sex

    def get_bmi(self) -> float:
        """Calculate BMI."""
        return self.weight / ((self.height / 100) ** 2)

    def get_ideal_weight(self) -> float:
        """Calculate ideal weight using BMI 22."""
        return 22 * ((self.height / 100) ** 2)

    def get_lean_body_mass(self) -> float:
        """Calculate lean body mass (kg) calibrated for Eufy impedance scale.

        Uses height^2/impedance (standard BIA approach) with coefficients
        calibrated against EufyLife app output.
        """
        h_sq = (self.height / 100) ** 2

        if self.sex == "male":
            lbm = 45.0 * h_sq / self.impedance + 0.40 * self.weight - 0.05 * self.age + 27.0
        else:
            lbm = 55.0 * h_sq / self.impedance + 0.35 * self.weight - 0.05 * self.age + 20.0

        return max(lbm, self.weight * 0.25)

    def get_fat_percentage(self) -> float:
        """Calculate body fat percentage from lean body mass."""
        lbm = self.get_lean_body_mass()
        fat_percentage = ((self.weight - lbm) / self.weight) * 100
        return round(max(3.0, min(60.0, fat_percentage)), 1)

    def get_muscle_mass(self) -> float:
        """Calculate muscle mass in kg."""
        lbm = self.get_lean_body_mass()
        bone = self.get_bone_mass()
        muscle_mass = lbm - bone
        return round(max(10.0, muscle_mass), 1)

    def get_bone_mass(self) -> float:
        """Calculate bone mass in kg."""
        lbm = self.get_lean_body_mass()

        if self.sex == "male":
            bone_mass = lbm * 0.049
        else:
            bone_mass = lbm * 0.048

        return round(max(0.5, min(8.0, bone_mass)), 1)

    def get_water_percentage(self) -> float:
        """Calculate water percentage."""
        fat_pct = self.get_fat_percentage()
        water_percentage = (100 - fat_pct) * 0.7126
        return round(max(35.0, min(75.0, water_percentage)), 1)

    def get_visceral_fat(self) -> float:
        """Calculate visceral fat rating."""
        if self.sex == "male":
            vfal = 0.3 * self.weight - 0.09 * self.height + 0.10 * self.age + 1.0
        else:
            vfal = 0.3 * self.weight - 0.09 * self.height + 0.08 * self.age - 1.0

        return round(max(1.0, min(50.0, vfal)), 1)

    def get_bmr(self) -> float:
        """Calculate Basal Metabolic Rate (kcal/day).

        Uses Katch-McArdle formula (LBM-based) with age adjustment,
        calibrated against EufyLife app output.
        """
        lbm = self.get_lean_body_mass()

        if self.sex == "male":
            bmr = 360 + 21.6 * lbm - 1.5 * self.age
        else:
            bmr = 340 + 21.6 * lbm - 1.5 * self.age

        return round(max(500, min(3000, bmr)))

    def get_metabolic_age(self) -> int:
        """Calculate metabolic age."""
        fat_pct = self.get_fat_percentage()

        if self.sex == "male":
            ideal_fat = 20.0
        else:
            ideal_fat = 25.0

        metabolic_age = self.age + (fat_pct - ideal_fat) * 0.88

        return round(max(15, min(90, metabolic_age)))

    def get_protein_percentage(self) -> float:
        """Calculate protein percentage."""
        muscle = self.get_muscle_mass()
        protein_percentage = (muscle / self.weight) * 100 * 0.189
        return round(max(5.0, min(25.0, protein_percentage)), 1)

    def get_body_type(self) -> str:
        """Determine body type based on fat percentage and muscle mass."""
        fat = self.get_fat_percentage()
        muscle = self.get_muscle_mass()

        if self.sex == "male":
            if fat < 15.0:
                fat_level = 0  # low fat
            elif fat < 25.0:
                fat_level = 1  # normal fat
            else:
                fat_level = 2  # high fat
            if muscle < self.weight * 0.40:
                muscle_level = 0  # low muscle
            elif muscle < self.weight * 0.48:
                muscle_level = 1  # normal muscle
            else:
                muscle_level = 2  # high muscle
        else:
            if fat < 22.0:
                fat_level = 0
            elif fat < 32.0:
                fat_level = 1
            else:
                fat_level = 2
            if muscle < self.weight * 0.33:
                muscle_level = 0
            elif muscle < self.weight * 0.40:
                muscle_level = 1
            else:
                muscle_level = 2

        body_type_index = fat_level * 3 + muscle_level
        return BODY_TYPES[body_type_index]

    def calculate_all(self) -> BodyCompositionResult:
        """Calculate all body composition metrics."""
        return BodyCompositionResult(
            bmi=round(self.get_bmi(), 1),
            body_fat=self.get_fat_percentage(),
            muscle_mass=self.get_muscle_mass(),
            bone_mass=self.get_bone_mass(),
            water_percentage=self.get_water_percentage(),
            visceral_fat=self.get_visceral_fat(),
            bmr=self.get_bmr(),
            metabolic_age=self.get_metabolic_age(),
            protein_percentage=self.get_protein_percentage(),
            ideal_weight=round(self.get_ideal_weight(), 1),
            body_type=self.get_body_type(),
            lean_body_mass=round(self.get_lean_body_mass(), 1),
        )
