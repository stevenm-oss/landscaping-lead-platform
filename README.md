# Texas Yard Quotes – lead platform

City landing pages, quote form with texting consent, lead scoring, automatic routing,
contractor portal, owner dashboard and Stripe invoicing. Clean & Clear gets first pick of
sod, flowerbed, irrigation and wood fencing leads in its own cities. Everything else is sold.

## What's where

| Address | What it is |
|---|---|
| `/` | Home page with quote form |
| `/fort-worth-tx/` | City page (one per city) |
| `/fort-worth-tx/sod-installation/` | Landing page (one per city and service, 99 total) |
| `/portal` | Contractor portal: leads, won/lost, settings |
| `/admin` | Owner dashboard: all leads, coverage gaps, prices, contractors, billing |
| `/sitemap.xml` | Submit this to Google Search Console |

To add a city or service, edit `catalog.py` and redeploy. Pages, sitemap and form options update on their own.

## Launch checklist

### 1. Put the code online (about 30 minutes)
1. Create a free GitHub account if you don't have one, make a new **private** repository, and upload every file in this folder.
2. In Render, choose **New → Blueprint**, pick the repository, and approve. `render.yaml` creates the website and a PostgreSQL database together. (Starter web service plus Basic database, roughly $13–$15 a month. Check current pricing on Render.)
3. When Render asks for the blank settings, fill in at least:
   - `ADMIN_PASSWORD`: a long password only you know
   - `OWNER_EMAIL`: where alerts for unmatched leads go
   - `SITE_URL`: your domain, like `https://texasyardquotes.com` (use the `onrender.com` address until you have one)
4. Open `your-site/admin`, sign in, click **Contractors → Clean & Clear**, set your email, a password, your mobile number and your cities. Then sign in at `/portal/login` to see your own leads.

### 2. Domain (1 day)
Buy a domain (check that the name is free to use first), add it in Render under **Settings → Custom Domains**, and point the DNS records where Render tells you. Update `SITE_URL`.

### 3. Email (1 hour)
Make a free account at resend.com, verify your domain, create an API key, and set `RESEND_API_KEY` and `EMAIL_FROM` (for example `Texas Yard Quotes <leads@yourdomain.com>`). Until then, emails are logged but not sent.

### 4. Text messages (start now, approval takes 1–3 weeks)
1. Make a Twilio account and buy a local number.
2. Register for **A2P 10DLC** (Messaging → Regulatory Compliance). US carriers block business texts until this is approved. You'll need: your EIN, the website, the privacy and terms pages (`/privacy`, `/terms`), a description of the opt-in (the checkbox on the quote form), and sample messages like:
   *"Texas Yard Quotes: Thanks, Maria. North Texas Stone & Patio will contact you shortly about your hardscape project. Reply STOP to opt out."*
3. Create a Messaging Service with your number, then set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` and `TWILIO_MESSAGING_SERVICE_SID`. Twilio handles STOP and HELP replies on its own.

Until texting is approved, leads still arrive by email and in the portal.

### 5. Billing (1 hour)
Open a Stripe account, finish verification, and set `STRIPE_SECRET_KEY` (start with the test key `sk_test_...` and switch to live when ready). On **Billing** in the dashboard, **Create and send invoices** emails each contractor a Stripe invoice with a pay link, due in 7 days. Contractors on the monthly plan get the monthly fee plus any leads over their limit.

### 6. Contractors
Add each one under **Contractors** with a starting password and send them `your-site/portal/login`. Before you sell them leads, check their insurance and any license their trade needs, and have a short written agreement covering price, payment terms and your bad-lead credit policy (contractors can tap **Report a bad lead**, and you can **Credit** it from the dashboard).

### 7. Get found
- Submit `/sitemap.xml` in Google Search Console.
- Start with a small Google Ads budget on your best pages (sod and irrigation in Fort Worth) while the pages build ranking.
- The **Coverage gaps** box shows where leads came in with no contractor. That's your recruiting list.

### 8. Before taking real leads, have a lawyer look at
- The consent wording on the form, `/privacy` and `/terms` (federal texting and calling rules allow large per-message damages, so this is worth an hour of legal time)
- Whether Texas or Oklahoma telemarketing registration rules apply to your setup
- Your contractor agreement

The site stores the exact consent wording, time, IP address and browser for every lead, which is your proof if anyone ever disputes a text.

## Run it on your own computer (optional)
```
pip install -r requirements.txt
ADMIN_PASSWORD=test123 flask --app app run
```
Then open http://127.0.0.1:5000. It uses a local SQLite file instead of PostgreSQL.
