"""Which DocumentLab modules exist yet. Update a module's status when its phase is finished.

The dashboard and the frontend sidebar read this, so nothing is ever shown as working
before it is built and tested.
"""

AVAILABLE = "available"
PLANNED = "planned"

MODULES = [
    {"key": "dashboard", "name": "Dashboard", "phase": 4, "status": AVAILABLE},
    {"key": "generator", "name": "Barcode Generator", "phase": 5, "status": AVAILABLE},
    {"key": "analyzer", "name": "Barcode Analyzer", "phase": 6, "status": AVAILABLE},
    {"key": "documents", "name": "Document Analysis", "phase": 7, "status": AVAILABLE},
    {"key": "test_lab", "name": "Testing Laboratory", "phase": 8, "status": AVAILABLE},
    {"key": "rules", "name": "Validation Rules", "phase": 9, "status": PLANNED},
    {"key": "reports", "name": "Reports", "phase": 9, "status": PLANNED},
    {"key": "audit", "name": "Audit Logs", "phase": 3, "status": AVAILABLE},
    {"key": "users", "name": "User Management", "phase": 3, "status": AVAILABLE},
    {"key": "settings", "name": "Settings", "phase": 4, "status": AVAILABLE},
]
