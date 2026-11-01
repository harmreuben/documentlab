"""ICAO Doc 9303 specimen data and synthetic images, used by the Testing Laboratory and the test suite.

Every value here is ICAO's published fictional specimen ("Utopia", state code UTO) or invented
test data. The images are plain renderings labelled SPECIMEN, for testing OCR and MRZ reading only.
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

TD3 = ["P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<", "L898902C36UTO7408122F1204159ZE184226B<<<<<10"]
TD2 = ["I<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<", "D231458907UTO7408122F1204159<<<<<<<6"]
TD1 = ["I<UTOD231458907<<<<<<<<<<<<<<<", "7408122F1204159UTO<<<<<<<<<<<6", "ERIKSSON<<ANNA<MARIA<<<<<<<<<<"]

# A specimen that is still valid: same person, expiry moved to 2031 with its check digits recomputed.
TD3_VALID = None  # filled in below


def _valid_td3():
    from core.identity.mrz import check_digit
    l2 = list(TD3[1])
    expiry = "310415"
    l2[21:27] = expiry
    l2[27] = check_digit(expiry)
    l2 = "".join(l2)
    composite = check_digit(l2[0:10] + l2[13:20] + l2[21:43])
    return [TD3[0], l2[:43] + composite]


TD3_VALID = _valid_td3()

def _font(size: int):
    import barcode
    return ImageFont.truetype(os.path.join(os.path.dirname(barcode.__file__), "fonts", "DejaVuSansMono.ttf"), size)


def passport_image(mrz_lines=None, printed_given="ANNA MARIA", printed_number="L898902C3",
                   birth="12 AUG 1974", expiry="15 APR 2031", blur=0.0):
    """A plain specimen data page: printed details above, MRZ at the bottom."""
    mrz_lines = mrz_lines or TD3_VALID
    width, height = 1250, 880
    image = Image.new("RGB", (width, height), (236, 240, 238))
    d = ImageDraw.Draw(image)
    d.text((40, 30), "UTOPIA  SPECIMEN  PASSPORT", font=_font(34), fill="black")
    rows = [("Surname", "ERIKSSON"), ("Given names", printed_given), ("Passport No.", printed_number),
            ("Date of birth", birth), ("Date of expiry", expiry)]
    for i, (label, value) in enumerate(rows):
        d.text((420, 120 + i * 70), label, font=_font(22), fill=(80, 80, 80))
        d.text((420, 148 + i * 70), value, font=_font(34), fill="black")
    for i, line in enumerate(mrz_lines):
        d.text((40, height - 170 + i * 60), line, font=_font(40), fill="black")
    return image.filter(ImageFilter.GaussianBlur(blur)) if blur else image


def letter_image(text="Order reference TEST-0042\nDelivered 3 March 2026\nThank you"):
    image = Image.new("RGB", (1000, 600), "white")
    d = ImageDraw.Draw(image)
    for i, line in enumerate(text.splitlines()):
        d.text((60, 80 + i * 60), line, font=_font(36), fill="black")
    return image
