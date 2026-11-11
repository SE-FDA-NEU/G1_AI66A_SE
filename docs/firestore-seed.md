# Firestore demo documents

The application currently uses SQLite for its backend. This script creates a
small, separate Firestore demo dataset for the Firebase project
`mini-marketplace-se`; it does not migrate or replace the SQLite database.

## Setup

Create/download a Firebase service-account JSON file in the Firebase Console.
Keep it outside the repository and never commit it. Then install the optional
dependency and set the path:

```powershell
python -m pip install -r requirements-firebase.txt
$env:FIREBASE_SERVICE_ACCOUNT_JSON = 'C:\secure\mini-marketplace-se-service-account.json'
```

## Seed

```powershell
python scripts/seed_firestore.py
```

The script writes deterministic IDs to `users`, `categories`, `products`,
`orders`, and `notifications`. Re-running it updates those same documents, so
it does not create duplicate demo records. It writes no password hashes,
tokens, service-account data, or real customer information.

The script does not delete documents. Review the Firestore Console before
using it against a shared or production dataset.
