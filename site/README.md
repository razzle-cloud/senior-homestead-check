# Decatur Homestead Check (website)

A small public website built on the `decatur-exemptions` Supabase database.

| Page | What it does | Data |
|---|---|---|
| `index.html` | Address check: type an address, see exemptions on file at both offices and what's worth applying for | `lookup` edge function (public, rate-limited) |
| `findings.html` | Findings, charts and a neighborhood map | Built in from `share` summary views (no live queries) |
| `apply.html` | Where, when and how to apply | Static |
| `about.html` | Sources, methods, limits, privacy | Static |
| `partners.html` | Outreach list with names and mailing addresses, CSV download | `outreach` edge function: sign-in required, email must be on `app.outreach_users`, every view logged in `app.access_log` |

## Folders

- `public/` — the site itself (plain HTML/CSS/JS, no build step). Deploy this folder.
- `build/` — `build.py` regenerates the pages from `findings.json` and `geo.json` (refresh those from Supabase after the analysis is rebuilt).
- `functions/` — source of the two Supabase edge functions (already deployed).
- `sql/` — migration `06_website_api` (already applied): `app` schema, address index, `site_lookup` and `site_outreach` functions.

## Deploy

Option A (Vercel connector): reconnect Vercel in claude.ai Settings → Connectors with access to your projects, then ask Claude to deploy.

Option B (your Terminal):
```
brew install node        # once, if `node -v` says command not found
cd ~/Documents/Decatur-Senior-Exemptions/website/public
npx vercel deploy        # first time: log in and accept the defaults; gives a preview link
npx vercel deploy --prod # when you're happy, publishes the public link
```

## Partner accounts

1. Supabase dashboard → Authentication → Users → Add user → Create new user (email + password, tick "Auto confirm").
2. Approve the email for the outreach list, in the SQL editor:
   ```sql
   insert into app.outreach_users (email, name, org) values ('person@example.org', 'Name', 'Organization');
   ```
3. To remove access: `update app.outreach_users set active = false where email = 'person@example.org';`
4. See who looked at the list: `select * from app.access_log order by at desc;`

Recommended: in Authentication → Sign In / Providers, turn off "Allow new users to sign up", so only accounts you create can sign in.

## After a data refresh

1. Rebuild the analysis tables (ask Claude).
2. `select app.refresh_lookup_index();` in the SQL editor.
3. Refresh `build/findings.json` and `build/geo.json`, run `python3 build/build.py`, redeploy.
