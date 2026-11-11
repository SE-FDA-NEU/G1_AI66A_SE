# Google sign-in

Google sign-in uses Google Identity Services in the browser and validates its ID
token on the backend before issuing the application's existing JWT. It is disabled
when `GOOGLE_CLIENT_ID` is empty; password login remains available.

## Setup

1. Configure the Google OAuth consent screen and create a **Web application**
   OAuth client in Google Cloud. Add each actual frontend origin to the client's
   authorized JavaScript origins, including the port for local development and
   the exact Firebase preview or production origin in use. If the consent screen
   is in testing mode, add the Google accounts used for testing as test users.
2. Set `GOOGLE_CLIENT_ID` to that client ID in the backend environment, then
   restart FastAPI. The client ID is public configuration, not a client secret.
   Never place an OAuth client secret or service-account key in the browser or Git.
3. Apply existing schema initialization (`python -m src.database`): it creates
   `google_identities` without rewriting existing users. Start the application
   and open `/login`. Use HTTPS for hosted frontend and API endpoints.

Follow Google's [setup instructions](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
for the current console steps. The Firebase frontend can call this endpoint after
the backend integration in #242 is merged and the Firebase origin is allowed by
both Google and backend CORS. No real Google credentials or deployed OAuth client
are provisioned by this repository change.

## Contract and account policy

- `GET /api/v1/auth/google/config` returns the public `client_id` or an empty
  string. `POST /api/v1/auth/google` accepts JSON `{ "credential": "..." }`
  and returns the same JWT and user shape as `/auth/login`.
- The server uses Google's library to verify signature, issuer, expiry and the
  configured audience; the stable Google `sub` identifies a returning user.
  A new identity must have a verified email and becomes a Buyer. The user cannot
  choose a privileged role during sign-in.
- An email belonging to an existing account is **not** automatically linked;
  the request returns 409 and directs the user to their existing sign-in method.
  An explicit authenticated linking flow is future work. Restricted accounts
  are rejected, and Google sign-in cannot reset an existing password.
- Invalid credentials return 401; an unavailable/disabled provider returns 503;
  account restrictions return 403. Failed registration rolls back both records.
  Never log Google credentials or application JWTs.

## Verification

Run `DEBUG=false python -m pytest tests/test_google_signin.py tests/test_auth.py
tests/test_database.py -q` and `node tests/google_signin_ui.mjs`. Automated tests
use local signing keys, fake claims and isolated test databases; they do not
prove that a Google Cloud client is configured correctly. Once a client and test
users exist, verify real Google sign-in on each authorized origin, first and
returning sign-in, email collision, blocked account and unavailable-network
feedback in a browser. Do not record user credentials or tokens in evidence.
