# HYF Impact Dashboard

One codebase, two environments:

| Environment | Data | Who uses it | GitHub branch | Login |
|---|---|---|---|---|
| **dev** | `data/mock/`: fictional, safe to share | You, for testing changes | `dev` | Optional |
| **prod** | `data/real/`: real counts only, groups under 5 hidden | Manager, team, funders | `main` | **Required** (the app refuses to start without one) |

The variable **`APP_ENV`** (`dev` or `prod`) tells the app which environment it is. That one setting decides the data folder and the "fictional data" banner, and makes the login mandatory in prod.

## Folder layout

```
app.py, impact.py         the app
requirements.txt          Python packages
Dockerfile                how Railway builds the app
railway-start.sh          how Railway starts the app
.streamlit/config.toml    theme colours and settings
brand.py                  HYF colours, logo and header (change the brand here)
assets/                   HYF logo files and browser-tab icon
tools/make_cloud_data.py  turns a Dojo export into counts-only files
data/mock/                fictional data (dev)
data/real/                real counts-only data (prod)
```

## Set up GitHub (once)

1. Upload everything to a **private** repository. This makes the `main` branch.
2. Create the `dev` branch: on the repository page, click the branch button (it says **main**), type `dev` and click **Create branch: dev from main**.

## Set up Railway (once)

1. **New Project → Deploy from GitHub repo** and pick the repository. This is the **production** environment.
2. In the service's **Settings → Source**, check the branch is **main**.
3. Under **Variables**, add:
   - `APP_ENV` = `prod`
   - `ENABLE_ASK` = `false`
   - `APP_PASSWORD` = a strong password (or the Google login variables, see below)
4. **Settings → Networking → Generate Domain**, and pick an EU region under **Settings → Region**.
5. Create the dev environment: open the environment menu at the top (it says **production**), choose **New Environment**, name it `dev`, and duplicate production.
6. In the **dev** environment:
   - **Settings → Source**: set the branch to **dev**.
   - **Variables**: `APP_ENV` = `dev`. You can remove `APP_PASSWORD` here, because dev only holds fictional data.
   - **Generate Domain**, so dev gets its own link.

You now have two links: one for dev, one for prod.

## Making a change (every time)

1. **Change it in dev:** on GitHub, switch to the **dev** branch (branch button at the top left), then upload or edit files there. Railway rebuilds the **dev** app in a few minutes.
2. **Check it on the dev link.**
3. **Move it to prod:** on GitHub click **Pull requests → New pull request**, set **base: main ← compare: dev**, click **Create pull request**, then **Merge pull request**. Railway rebuilds the **prod** app.

Never upload straight to `main`. Everything goes through dev first.

## Updating the real data (prod)

On your own laptop, never in the cloud:

```bash
python tools/make_cloud_data.py "path/to/dojo.trainees.xlsx"
```

This writes counts-only files into `data/real/`. Upload `data/real/HYF_indicators.xlsx` and `data/real/HYF_counts.xlsx` to the **dev** branch, check dev still works, then merge to main as above.

Never upload the Dojo export or any file with one row per person.

## Google login instead of a password (optional)

Set these variables in the **prod** environment instead of `APP_PASSWORD`:

| Variable | Value |
|---|---|
| `AUTH_CLIENT_ID` | from your Google OAuth client |
| `AUTH_CLIENT_SECRET` | from your Google OAuth client |
| `AUTH_REDIRECT_URI` | `https://YOUR-PROD-LINK/oauth2callback` |
| `AUTH_COOKIE_SECRET` | a long random text |
| `ALLOWED_EMAIL_DOMAINS` | `hackyourfuture.net` |

Create the OAuth client in the Google Cloud Console: **APIs & Services → OAuth consent screen** (user type *Internal*), then **Credentials → Create credentials → OAuth client ID → Web application**, with the redirect URI above.

## Running on your laptop

```bash
pip install -r requirements.txt
APP_ENV=dev streamlit run app.py     # fictional data
```

## Brand (logo and colours)

The app uses the HYF website colours: dark red `#5E1600`, light red `#B12900`, beige `#FAF5D9`, yellow `#FFF09E` and white.

- **Logo files** are in `assets/`. To change one, replace the file with a PNG of the same name (transparent background).
- **Colours** are set in two places: `brand.py` (charts, header, exported HTML) and `.streamlit/config.toml` (buttons, tabs, sidebar). Change both together.
