# Connected App Setup Guide

This guide walks you through creating a Salesforce Connected App to authenticate
the Data Cloud MCP server.

## Step 1 — Create the Connected App

1. In your Salesforce org, go to **Setup → App Manager → New Connected App**.
2. Fill in:
  - **Connected App Name**: `Data Cloud MCP`
  - **API Name**: `DataCloud_MCP`
  - **Contact Email**: your email
3. Under **API (Enable OAuth Settings)**:
  - Check **Enable OAuth Settings**
  - **Callback URL**: `http://localhost:55556/Callback`
  *(must match `SF_CALLBACK_URL` env var — default is `http://localhost:55556/Callback`)*
  - **Selected OAuth Scopes** — add all of the following:
    - `Access and manage your data (api)`
    - `Access and manage Data Cloud Ingestion API data (cdp_ingest_api)`
    - `Access and manage Data Cloud profile data (cdp_profile_api)`
    - `Perform ANSI SQL queries on Data Cloud data (cdp_query_api)`
  - Check **Require Proof Key for Code Exchange (PKCE)**
  - Check **Enable Client Credentials Flow** (optional, for future use)
4. Click **Save**, then **Continue**.

## Step 2 — Copy Credentials

After saving, click **Manage Consumer Details** (you may need to verify via email).

Copy:

- **Consumer Key** → this is your `SF_CLIENT_ID`
- **Consumer Secret** → this is your `SF_CLIENT_SECRET`

## Step 3 — Grant the App Access to Data Cloud

1. In Setup, search for **Connected Apps OAuth Usage**.
2. Find **Data Cloud MCP** and click **Install** if not already installed.
3. Ensure the running user's Profile has the **Data Cloud** permission set or the
  **Salesforce Data Cloud User** or **Data Cloud Admin** permission set assigned.

## Step 4 — Sandbox orgs

For sandboxes, set:

```
SF_LOGIN_URL=test.salesforce.com
```

## Step 5 — Verify

Run the server once interactively to confirm OAuth works:

```bash
python server.py
```

A browser window will open for login. After successful login you should see
`Final Status: has_code=True` in the browser and `Successfully obtained access token`
in the console.