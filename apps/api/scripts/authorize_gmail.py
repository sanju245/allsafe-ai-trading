"""One-time local OAuth setup for the Gmail account that sends notifications.

Run with a Google Cloud Desktop OAuth client JSON file and an output path outside
the repository. The output contains secrets; move its values into Render and
delete the file after the deployment is verified.
"""

from __future__ import annotations

import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

SCOPE = "https://www.googleapis.com/auth/gmail.send"


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorize Gmail send-only access")
    parser.add_argument("--credentials", required=True, type=Path, help="Downloaded Desktop OAuth client JSON")
    parser.add_argument("--output", required=True, type=Path, help="Secret JSON output outside the repository")
    parser.add_argument("--email", default="sanjay200123@gmail.com")
    args = parser.parse_args()

    client = json.loads(args.credentials.read_text(encoding="utf-8"))["installed"]
    client_id = client["client_id"]
    client_secret = client["client_secret"]
    state = secrets.token_urlsafe(32)
    result: dict[str, str] = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            query = parse_qs(urlsplit(self.path).query)
            if urlsplit(self.path).path != "/oauth/callback" or query.get("state") != [state]:
                self.send_error(400, "Invalid authorization response")
                return
            result["code"] = query.get("code", [""])[0]
            result["error"] = query.get("error", [""])[0]
            self.send_response(200 if result["code"] else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Authorization received. You may close this tab.")

        def log_message(self, format: str, *args: object) -> None:
            pass  # Do not log the one-time authorization code in the callback URL.

    server = HTTPServer(("127.0.0.1", 0), Callback)
    server.timeout = 180
    redirect_uri = f"http://127.0.0.1:{server.server_port}/oauth/callback"
    authorization_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "login_hint": args.email,
        "state": state,
    })
    print(f"Open this URL to authorize {args.email}:\n{authorization_url}", flush=True)
    server.handle_request()
    server.server_close()
    if not result.get("code"):
        raise SystemExit(f"Gmail authorization did not finish: {result.get('error', 'timed out')}")

    token_request = Request(
        "https://oauth2.googleapis.com/token",
        data=urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "code": result["code"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urlopen(token_request, timeout=15) as response:
        token = json.load(response)
    if not token.get("refresh_token") or SCOPE not in token.get("scope", "").split():
        raise SystemExit("Google did not return a refresh token with gmail.send permission.")

    if args.output.exists():
        raise SystemExit("Output file exists; choose a new path to avoid overwriting a secret.")
    args.output.write_text(json.dumps({
        "GMAIL_CLIENT_ID": client_id,
        "GMAIL_CLIENT_SECRET": client_secret,
        "GMAIL_REFRESH_TOKEN": token["refresh_token"],
        "GMAIL_FROM_EMAIL": args.email,
    }), encoding="utf-8")
    print(f"Gmail authorization saved to {args.output}. Move the values to Render and delete the file.")


if __name__ == "__main__":
    main()
