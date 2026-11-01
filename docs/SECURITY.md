# DocumentLab security

What DocumentLab does to protect accounts and personal data, what it deliberately doesn't do, and how to
connect an SSN verification provider if your organisation is authorised to use one.

## What DocumentLab is, and isn't

DocumentLab makes **technical checks**: barcodes decode, check digits add up, dates are real, printed text
matches encoded data. It never says a document is genuine, and it never generates identity documents or
identity barcodes. The Barcode Generator refuses data laid out like a licence, ID card or passport.

## Accounts and roles

| Role | Can do |
|---|---|
| Administrator | Everything, including users, the audit log and security status |
| Analyst | Barcode and document analysis; sees their own identity records |
| Reviewer | Analysis, plus reviewing other people's results; sees all identity records |
| Developer | Barcode tools and the Testing Laboratory; **no** access to identity documents |
| Read-only | Views results; can't change anything |

- **Passwords**: at least 10 characters, not common, not all digits, not similar to the username.
- **Sign-in limits**: 5 attempts a minute from one computer, and 5 failed attempts lock that account for
  15 minutes (`LOGIN_LOCKOUT_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES`). The message is the same whether or not
  the account exists, so the lock can't be used to discover usernames. Trade-off: anyone who knows a
  username can lock that account for 15 minutes by guessing wrongly. An administrator can still sign in
  with a different account.
- **Sessions**: signed out after 30 minutes without activity (`SESSION_IDLE_MINUTES`), after 8 hours in
  any case, and when the browser closes. Cookies are `HttpOnly`, `SameSite=Lax`, and HTTPS-only in production.
- **CSRF**: every change, including sign-in, needs Django's CSRF token.
- **Four eyes**: nobody can review their own analysis.

## Identity data

- Only administrators, analysts and reviewers can open Document Analysis.
- Names, numbers, dates, recognised text and images are **deleted after 30 days**
  (`DOCUMENT_RETENTION_DAYS`) or sooner on request. Only the reference and check results remain.
- Lists show only a surname initial and the last three characters of a number.
- SSNs: only the last four digits are ever stored. The full number leaves the screen as soon as it's checked.
- The **audit log** records that something happened (who, when, which record), never the content.
  Sensitive keys are redacted before anything is written, and the same filter runs on the server log
  (`backend\logs\documentlab.log`).
- **PDF reports** of a document carry a CONFIDENTIAL banner and the deletion date. Summary reports
  contain counts only.
- **Test fixtures** must be synthetic. Identity barcodes and documents from any state other than ICAO's
  fictional specimen state (UTO) are refused.
- **Not encrypted at rest by DocumentLab**: uploaded files, the database and backups are ordinary files
  on disk. Use BitLocker (or equivalent) on the server's drives and on wherever backups are copied.

## The web server

In production (`config.settings.prod`):

- Debug pages are off. Errors show a plain message; details go to the redacted log.
- The secret key must be set and long; the server refuses to start with a missing or development key.
- HTTPS is enforced (redirect, secure cookies, HSTS) unless `DJANGO_ALLOW_HTTP=true` is set for local trials.
- Every response, including the website's own files, carries:
  `Content-Security-Policy` (only this site's own scripts, styles, images and connections; no framing),
  `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`,
  `Permissions-Policy` (no camera, microphone, location, payment or USB) and
  `Cross-Origin-Opener-Policy`/`-Resource-Policy: same-origin`.
- Uploads: at most 10 MB; the type is decided by the file's content, not its name; images over
  40 megapixels and PDFs over 10 pages are refused or cut short, to stop oversized "bomb" files.
- Rate limits: 30 requests a minute when signed out, 300 when signed in, 30 uploads a minute.

The Settings page's *Security and readiness* panel checks all of this against the running server.
`python manage.py check --deploy` does the same from the command line.

## Connecting an SSN verification provider

DocumentLab can only check an SSN's **format**. Whether a number was issued to a particular person can
only be confirmed by a provider with access to the Social Security Administration's records, such as
SSA's **eCBSV** service. That access is restricted by law and contract:

- eCBSV is open only to financial institutions and their contracted service providers ("permitted
  entities") with a US employer identification number, a signed user agreement and fees;
- every check needs the number holder's **written consent** (wet or electronic signature);
- SSA's free SSNVS service is only for employers checking employees' wage reports, not identity checks.

DocumentLab ships **no** provider. Until one is configured, the *Issued to this person* check shows
**Unavailable**. Only connect a provider your organisation is authorised to use, for a purpose the
person consented to.

### What DocumentLab guarantees around a provider

- It never contacts a provider without a recorded consent: method, form reference, date signed and purpose.
- It sends only the number, first name, last name and date of birth.
- It stores the masked number, the consent details and the answer: match, no match (naming the fields,
  never their values), or unavailable. It never stores the full number, name or date of birth sent.
- A timeout, an error or an answer it doesn't understand counts as **Unavailable**, never as a match.
- A match is described as "the provider's records match these details". It doesn't prove who is
  presenting the number.
- The same roles as Document Analysis can use it.

### Writing an adapter

An adapter is a small Python class in your own module (for example `backend\adapters\myprovider.py`)
that implements `core.verification.base.SsnVerificationProvider`:

```python
import os
from core.verification.base import MATCH, NO_MATCH, ERROR, ProviderResult, SsnRequest, SsnVerificationProvider


class MyProvider(SsnVerificationProvider):
    name = "My Provider"
    timeout_seconds = 20

    def __init__(self):
        self.api_key = os.environ["MYPROVIDER_API_KEY"]  # credentials come from .env, never from code

    def verify_ssn(self, request: SsnRequest) -> ProviderResult:
        # Call the provider's API over HTTPS with request.number, request.first_name, request.last_name,
        # request.birth_date and the consent details it requires (request.consent).
        # Return ProviderResult(MATCH), ProviderResult(NO_MATCH, mismatched=["last_name"]), or
        # ProviderResult(ERROR, message="...") for anything that isn't a clear answer. Don't raise.
        ...
```

Then in `backend\.env`:

```ini
SSN_VERIFICATION_PROVIDER=adapters.myprovider.MyProvider
MYPROVIDER_API_KEY=...
```

Restart DocumentLab. The Settings page shows whether the adapter loaded; Document Analysis → *SSN format
check* then offers *Check with provider*. Test the adapter against the provider's test environment
first. `backend\tests\fake_provider.py` shows the shape DocumentLab's own tests use.

## Reporting a problem

If you find a security problem, don't open a public GitHub issue. Contact the project owner directly
with the steps to reproduce it.
