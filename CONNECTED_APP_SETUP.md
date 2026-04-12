# Connected App Setup Guide

This guide walks you through creating a Salesforce Connected App to authenticate
the Data Cloud MCP server. You need to do this **once per org**.

---

## Prerequisites

Before you begin, make sure you have:

- A Salesforce org with **Data Cloud** (Data 360) provisioned and enabled
- **System Administrator** access to the org
- The **Data Cloud Admin** or **Salesforce Data Cloud User** permission set assigned to your user

---

## Step 1 — Create the Connected App

1. Log in to your Salesforce org
2. Click the **gear icon** (top right) → **Setup**
3. In the Quick Find box, type **App Manager** and select it
4. Click **New Connected App** (top right)
5. Fill in the **Basic Information**:
   - **Connected App Name**: `Data Cloud MCP`
   - **API Name**: `DataCloud_MCP` (auto-fills)
   - **Contact Email**: your email address
6. Scroll down to **API (Enable OAuth Settings)**:
   - Check **Enable OAuth Settings**
   - **Callback URL**: enter exactly `http://localhost:55556/Callback`
   - **Selected OAuth Scopes** — click **Add** for each of the following:
     - `Access and manage your data (api)`
     - `Access and manage Data Cloud Ingestion API data (cdp_ingest_api)`
     - `Access and manage Data Cloud profile data (cdp_profile_api)`
     - `Perform ANSI SQL queries on Data Cloud data (cdp_query_api)`
   - Check **Require Proof Key for Code Exchange (PKCE)**
   - Optionally check **Enable Client Credentials Flow** (useful for future automation)
7. Click **Save**, then click **Continue** on the confirmation screen

> **Note**: It can take 2-10 minutes for the Connected App to become active after saving.

---

## Step 2 — Copy Your Credentials

1. After saving, you'll land on the Connected App detail page
2. Click **Manage Consumer Details** button
3. Salesforce will send you a verification code to your email — enter it
4. You'll see two values:
   - **Consumer Key** — copy this, it is your `SF_CLIENT_ID`
   - **Consumer Secret** — copy this, it is your `SF_CLIENT_SECRET`

> **Keep these safe.** You'll paste them into the Cursor MCP config in a later step.
> Never commit them to a public git repo.

---

## Step 3 — Grant the App Access to Data Cloud

1. In Setup, type **Connected Apps OAuth Usage** in the Quick Find box and select it
2. Find **Data Cloud MCP** in the list
3. Click **Install** if it shows as not installed
4. Go back to Setup → type **Permission Sets** in Quick Find
5. Find and open one of these permission sets:
   - **Data Cloud Admin** (full access)
   - **Salesforce Data Cloud User** (standard access)
6. Click **Manage Assignments** → **Add Assignments**
7. Select your user → click **Assign** → **Done**

> **Why this matters**: Without the Data Cloud permission set, the OAuth token
> won't have access to Data Cloud APIs even if the scopes are correct.

---

## Step 4 — Determine Your Login URL

| Org type | Login URL |
|----------|-----------|
| Production org | `login.salesforce.com` |
| Developer Edition | `login.salesforce.com` |
| Trailhead Playground | `login.salesforce.com` |
| Sandbox | `test.salesforce.com` |
| My Domain (recommended) | `your-domain.my.salesforce.com` |

You'll set this as `SF_LOGIN_URL` in the MCP config.

---

## Step 5 — Verify the Setup (Optional)

Before configuring Cursor, you can test that the Connected App works:

1. Open a terminal/PowerShell
2. Navigate to the project folder:
   ```
   cd C:\path\to\datacloud-mcp
   ```
3. Activate the virtual environment:
   ```
   # Windows
   .venv\Scripts\activate
   # macOS / Linux
   source .venv/bin/activate
   ```
4. Set the environment variables:
   ```
   # Windows PowerShell
   $env:SF_CLIENT_ID="your-consumer-key-here"
   $env:SF_CLIENT_SECRET="your-consumer-secret-here"
   $env:SF_LOGIN_URL="login.salesforce.com"
   
   # macOS / Linux
   export SF_CLIENT_ID="your-consumer-key-here"
   export SF_CLIENT_SECRET="your-consumer-secret-here"
   export SF_LOGIN_URL="login.salesforce.com"
   ```
5. Run the server:
   ```
   python server.py
   ```
6. A browser window will open — log in to Salesforce
7. After login you should see in the browser:
   ```
   Final Status: has_code=True
   You can close this window now
   ```
   And in the terminal:
   ```
   Successfully obtained access token
   ```

If you see errors, check:
- The Callback URL matches exactly: `http://localhost:55556/Callback`
- The OAuth scopes are all added
- Your user has the Data Cloud permission set
- The Connected App has had time to activate (wait 10 minutes after creation)

---

## Switching to a Different Org

To connect to a different Salesforce org:

1. Create a new Connected App in the new org (repeat Steps 1-3 above)
2. Copy the new Consumer Key and Consumer Secret
3. Update your Cursor MCP config (`mcp.json`) with the new credentials:
   - Replace `SF_CLIENT_ID` with the new Consumer Key
   - Replace `SF_CLIENT_SECRET` with the new Consumer Secret
   - Update `SF_LOGIN_URL` if the org type is different (production vs sandbox)
4. Restart the MCP in Cursor (Settings → MCP → toggle off → on)
5. The browser will open again for OAuth login to the new org

> **Tip**: You can have multiple MCP entries in `mcp.json` for different orgs:
> ```json
> {
>   "mcpServers": {
>     "datacloud-prod": { ... "SF_LOGIN_URL": "login.salesforce.com" ... },
>     "datacloud-sandbox": { ... "SF_LOGIN_URL": "test.salesforce.com" ... }
>   }
> }
> ```
> Only enable one at a time unless they use different server names.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "invalid_client" error | Consumer Key or Secret is wrong — re-copy from Connected App |
| "invalid_grant" error | User doesn't have Data Cloud permission set |
| Browser doesn't open | Check that port 55556 is not blocked by firewall |
| "OAUTH_APPROVAL_ERROR" | The Connected App hasn't activated yet — wait 10 minutes |
| "invalid_subject_token" on DC token exchange | Missing `cdp_query_api` or `cdp_profile_api` scope |
| "URL No Longer Exists" on metadata calls | Call `debug_auth()` to verify the c360a URL is correct |
| Token expires frequently | Tokens last ~110 minutes and auto-refresh — this is normal |
