# HYF Impact Dashboard (tabs version)

Same dashboard as `hyf-dashboard-app`, with the code split into one file per tab. It looks and works exactly the same.

One codebase, two environments:

| Environment | Data | Who uses it | GitHub branch | Login |
|---|---|---|---|---|
| **dev** | `data/mock/`: fictional, safe to share | You, for testing changes | `dev` | Optional |
| **prod** | `data/real/`: real counts only, groups under 5 hidden | Manager, team, funders | `main` | **Required** (the app refuses to start without one) |

The variable **`APP_ENV`** (`dev` or `prod`) tells the app which environment it is. That one setting decides the data folder and the "fictional data" banner, and makes the login mandatory in prod.

## Folder layout

```
app.py                    the app: login, sidebar and the main tabs
impact.py                 the Impact dashboard: loads the data, draws the filters, opens the tabs A–I
dashboard/common.py       shared parts: settings, definitions, the filters (Sel), cards, chart style, privacy rules
dashboard/tab_a_overview.py    A · Impact overview
dashboard/tab_b_programme.py   B · Programme & inclusion
dashboard/tab_c_employment.py  C · Employment
dashboard/tab_d_historic.py    D · Historic programme
dashboard/tab_e_org.py         E · Organisation & community
dashboard/tab_f_finance.py     F · Finance
dashboard/tab_g_partners.py    G · Partners
dashboard/tab_h_volunteers.py  H · Volunteers
dashboard/tab_i_visibility.py  I · Visibility
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

## How the filters reach every tab

1. `render()` in `impact.py` draws the filters (years, months, cohorts, audience).
2. Your choices become one object, `sel`.
3. Every tab is called with the same data `d` and the same `sel`, for example `page_employment(d, sel, …)`.
4. Inside a tab, each chart keeps only the matching rows: `sel.ymask(...)` for years, `sel.cmask(...)` for cohorts.

Streamlit runs the script again from the top after every filter change, so every tab is redrawn with the new `sel`.
To change one tab, edit only its `dashboard/tab_….py` file.

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

1. Open the HYF Google Sheet and choose **File → Download → Microsoft Excel (.xlsx)**. The file keeps the tabs `trainees.csv`, `employement`, `Volunteers` and `Organisations`.
2. Run:

   ```bash
   python tools/update_from_sheet.py "path/to/HYF data.xlsx"
   ```

   | Tab | Becomes (counts only) |
   |---|---|
   | Trainee_details | `impact_summary`, `impact_countries`: the Impact overview (graduates, jobs, countries, gender). Only the columns id, gender, country_of_origin, learning_status, type and company_name are read |
   | trainees.csv | `historic`, `historic_gender`, `origin` (historic up to 2025) + Build-tab tables |
   | employement | `employers`: hires per company. The company comes from `companyName`; when that is empty, it is read from the sentence in `employmentInfo.comments` |
   | Volunteers | `volunteers` (active, by main volunteer type) and `team.active_volunteers`, for the current half-year |
   | Organisations | `partners`: active partners this year, and hiring partners / graduates hired per year (hires at active partner organisations) |

3. Read what the script prints (status values, how many companies were found). Open the `…_employers_review.csv` file it saves next to your download, check the companies, and add spelling variants to `ALIASES` in `tools/extract_employers.py` if needed.
4. Upload `data/real/HYF_indicators.xlsx` and `data/real/HYF_counts.xlsx` to the **dev** branch, check dev, then merge to main.

Finance, targets, community, visibility, inclusion and outcomes are still filled in by hand in `HYF_indicators.xlsx`.

**Only real data is shown in prod.** Rows marked `is_sample = TRUE` are placeholders: the dev app shows them (demo), the prod app leaves them out, and a page or section with no real data is hidden. Fill in real rows (with `is_sample = FALSE`) and the page appears. To force a setting, set the variable `SHOW_SAMPLE_DATA` to `true` or `false`. Exception: the tabs listed in `SAMPLE_TABS` (default `community,finance,visibility`) keep their placeholder rows in prod, with a yellow "sample data" warning, until real figures are filled in. Remove a tab from `SAMPLE_TABS` (Railway/Streamlit variable) once it has real data, or set it to an empty value to hide all placeholders.

Never upload the Google Sheet download, a Dojo export, the review file or any other file with one row per person.

You can also run the parts separately: `tools/make_cloud_data.py` (trainees only) and `tools/extract_employers.py` (employment only).

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
