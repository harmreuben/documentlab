"""Test-suite view of the specimens: the shared synthetic data plus a fixed date and licence sample."""
from datetime import date

from core.testlab.specimens import TD1, TD2, TD3, TD3_VALID, letter_image, passport_image  # noqa: F401

TODAY = date(2026, 11, 1)  # fixed so expiry results don't change as time passes

LICENCE_PAYLOAD = ("@\n\x1e\rANSI 636000080002DL00410278DLDAQT64235789\nDCSERIKSSON\nDACANNA\nDADMARIA\n"
                   "DBB08121974\nDBA08122031\nDBC2")
