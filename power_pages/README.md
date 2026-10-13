# my.afrp.org bridge page for Helper sign-in

Helper sends users to:

`https://my.afrp.org/afrp-helper-auth?client_id=...&redirect_uri=...&state=...&nonce=...`

If you see **Page Not Found**, that URL is not published yet. Helper cannot fix this from code — a portal admin must create the page.

Power Pages only accepts **POST** to `/_services/auth/token` (GET returns 404). The bridge page runs JavaScript on **my.afrp.org** to POST the token request, then redirects the browser back to Helper.

---

## Option A — Power Pages Design Studio (often easiest)

1. Go to [Power Pages](https://make.powerpages.microsoft.com/) → site **My AFRP** → **Edit**.
2. Left nav **Pages** → **+ Page** → **Start from blank** (or **Other ways to add a page** → blank layout).
3. Page name: `AFRP Helper Auth` (display name only).
4. Set the page **URL / slug** to exactly: `afrp-helper-auth`  
   - Must be one segment: no spaces, no `/`, use hyphens only.
   - Do **not** make it a subpage of Profile or My Subscriptions (that would change the URL).
5. On the blank page, add a **Custom code** / **Embed** / **HTML** component (wording varies by template).
6. Paste **only** the contents of [`afrp-helper-auth-bridge.html`](afrp-helper-auth-bridge.html) (the `<p>` and `<script>` — you can omit the HTML comment at the top).
7. **Save** the page, then **Sync** / **Publish** the site (top bar).
8. Optional: keep the page out of the main menu (under **Other pages**) — it does not need a nav link.

**Test (incognito):**  
https://my.afrp.org/afrp-helper-auth  
You must **not** see “Page Not Found”. A bare visit may show “Missing sign-in parameters”; that is OK.

---

## Option B — Portal Management app

1. Open **Power Pages Management** (from site **…** menu → Portal management).
2. **Content** → **Web Pages** → **New**.
3. **Name:** `AFRP Helper Auth`  
   **Website:** My AFRP  
   **Partial URL:** `afrp-helper-auth`  
   **Parent Page:** leave empty / root (not nested under another page)  
   **Publishing State:** **Published**  
   **Hidden from sitemap:** Yes (optional)
4. Open the **Content Snippets** / **Localized content** / **HTML** field for this page (depends on your template) and paste [`afrp-helper-auth-bridge.html`](afrp-helper-auth-bridge.html).
5. **Save & Close**.
6. Restart the site from Power Platform admin center if your team normally does that after content changes.

---

## Allowed return addresses

The bridge only sends tokens to URLs listed in `ALLOWED_REDIRECT_URIS` near the top of its script. When you add a Helper host or another app, add its exact callback URL there, update the page on the portal and publish. Otherwise the bridge shows "This sign-in return address is not allowed."

## After the page exists

Portal site setting (semicolon-separated):

```text
ImplicitGrantFlow/afrp-helper/RedirectUri =
  http://localhost:5066/auth/portal/callback;https://afrp.bonito-turtle.ts.net/auth/portal/callback
```

Helper `.env`:

```bash
PORTAL_OAUTH_REDIRECT_URI=http://localhost:5066/auth/portal/callback
PORTAL_AUTH_BRIDGE_PATH=/afrp-helper-auth
```

Recreate the container after `.env` changes: `docker compose up -d --force-recreate afrp-helper`

---

## Troubleshooting

| Symptom | Cause |
|--------|--------|
| Page Not Found on `/afrp-helper-auth` | Page not created, wrong slug, or not **Published** |
| URL is `/something/afrp-helper-auth` | Page is a **child** of another page — either move it to root or set `PORTAL_AUTH_BRIDGE_PATH` to the full path |
| Redirect back to Helper fails | `redirect_uri` not listed in `ImplicitGrantFlow/afrp-helper/RedirectUri` |
| “Could not obtain token” on bridge | Implicit grant cert / client id site settings; check `/_services/auth/publickey` |

To confirm the page from Portal Management: **Web Pages** → search `afrp-helper-auth` → **Partial URL** = `afrp-helper-auth`, **Publishing State** = Published.
