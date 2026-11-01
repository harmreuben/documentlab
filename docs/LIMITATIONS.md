# Known limitations

DocumentLab is honest about what it can't do. This list is part of the product: read it before relying
on a result, and update it when something changes.

## What a result means

- **No result is proof of authenticity.** DocumentLab checks structure and consistency: check digits,
  dates, formats, printed text versus encoded data. A well-made forgery with correct check digits passes
  every check. Security features (holograms, UV ink, microprint, the chip in an e-passport) aren't examined.
- **"Pass" means "consistent", not "true".** A passport MRZ that passes says nothing about whether it
  belongs to the person presenting it.
- **A confirmed review isn't a pass.** It records that a person compared the flagged items with the
  original and found them correct.
- **SSNs: format only.** A valid format doesn't show that a number was issued, or to whom. Ownership needs an
  authorised provider (`docs/SECURITY.md`), and none is included.

## Reading documents

- **Text recognition (Tesseract)** works on clear, flat, printed Latin text. Handwriting, curved or creased
  pages, glare, heavy patterns behind text and very small print are unreliable. Every recognised word comes
  with a confidence score; low-confidence words are listed for checking.
- **Tested on synthetic specimens only.** The built-in fixtures render ICAO's fictional "Utopia" documents
  in a plain monospaced font, not the OCR-B font and security printing of real documents. Accuracy on real
  documents hasn't been measured.
- **MRZ layouts**: TD1 (ID cards, 3 × 30), TD2 (2 × 36) and TD3 (passports, 2 × 44). Visa layouts (MRV-A,
  MRV-B) aren't specifically supported.
- **OCR corrections**: letters and digits that OCR confuses (O/0, I/1, S/5, B/8) are corrected only where the
  field allows just one kind. Corrections in names and country codes can't be confirmed by a check digit, so
  they always need review.
- **Licence barcodes**: only a few fields are read (number, names, dates, sex) for comparison.
  Jurisdiction-specific rules aren't checked and are always reported as *Unavailable*. The Testing
  Laboratory deliberately has no licence fixtures, so these rules are tested only by the automated test suite.
- **Name comparison** across documents treats names as "nearly the same" from 85% similarity. This is a rule
  of thumb: it can't tell a typing error from a different person, which is why near matches need review.

## Images and barcodes

- **Image-quality thresholds are rules of thumb**, not standards. Reviewed in Phase 10 against the
  Testing Laboratory's fixtures:
  - every clean fixture passes (sharpness 500–1,600, contrast range 0.9–1.0);
  - heavy blur (sharpness 0.3) and very low contrast (range 0.12) are both flagged;
  - very low contrast also lowers the sharpness score, so it's reported as blurred *and* low-contrast;
  - a blank page used to be reported as "blurred". Since 0.10.0 it's reported as blank.

  They haven't been checked against real phone photos, so tune them (in `core/imaging/quality.py`) once you
  have real samples. The Validation Rules page always shows the values in use.
- **Glare isn't detected.** A simple brightness rule mistook white label backgrounds for glare and was removed.
- **Formats analysed**: QR Code, Code 128, Code 39, EAN-13, EAN-8, UPC-A and PDF417. Other formats the
  decoder reads are reported as *Not supported*.
- **Damaged or tiny codes** may not be found at all; the result then says no barcode could be read, never
  that the image is fine.

## Testing and rules

- **Rule coverage has gaps.** On the standard fixture set, about a dozen rules are never produced by any
  fixture, for example *Name fits the field*, *Expiry is after birth* and the licence rules. The Validation
  Rules page lists them under *Not tested*. Adding fixtures for them is the most useful next step.
- **One test run at a time.** A run happens in a background thread inside the server; restarting the server
  interrupts it, and it's then marked *Interrupted*.

## Running the server

- **SQLite is for one person on one PC.** Use PostgreSQL for several users (`docs/DEPLOYMENT.md`, step 8).
- **Rate limits and the sign-in limit are counted per server process** and reset when the server restarts.
  The per-account lock is counted from the audit log, so it survives restarts.
- **Account lock trade-off**: someone who knows a username can lock that account for 15 minutes.
- **No two-factor sign-in, and no password reset by email.** An administrator resets passwords.
- **Nothing is encrypted at rest by DocumentLab.** Uploaded files, the database and backups are ordinary
  files. Use BitLocker on the server and on backup drives.
- **Times** are shown in East Africa Time (Africa/Nairobi); change `TIME_ZONE` in `config/settings/base.py`
  for another zone.
