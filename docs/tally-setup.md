# Tally Setup Guide

## Enabling the TallyPrime HTTP Server

TallyBridge communicates with TallyPrime over its built-in HTTP server. Follow these steps to enable it.

### Step 1: Open TallyPrime

Launch TallyPrime and open the company you want to connect to.

### Step 2: Enable Connectivity

1. Press **F1** (Help) to open the Settings menu.
2. Navigate to **Settings > Connectivity**.
3. Set **TallyPrime acts as** to **Server**.
4. Set the **Port** to **9000** (this is the default port TallyBridge expects).
5. Enable **Enable ODBC / Enable HTTP** if present.
6. Accept and save the settings.

### Step 3: Verify the Connection

Open a browser or terminal and send a test request:

```
curl -X POST http://localhost:9000 \
  -H "Content-Type: text/xml" \
  -d '<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export Data</TALLYREQUEST><TYPE>Collection</TYPE><ID>Ping</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="Ping" ISMODIFY="No"><TYPE>Company</TYPE><FETCH>NAME</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>'
```

If Tally is running correctly, you will receive an XML response listing open company names.

### Step 4: Configure TallyBridge

Set environment variables in your `.env` file:

```env
TALLYBRIDGE_TALLY_HOST=localhost
TALLYBRIDGE_TALLY_PORT=9000
TALLYBRIDGE_TALLY_COMPANY=Your Company Name
```

If TallyPrime is on a different machine, replace `localhost` with the IP address of that machine and ensure the firewall allows traffic on port **9000**.

### Troubleshooting

| Problem | Solution |
|---|---|
| Connection refused | TallyPrime is not running or the HTTP server is not enabled. Re-check Step 2. |
| Empty response | Ensure a company is open in TallyPrime. |
| Wrong company data | Set `TALLYBRIDGE_TALLY_COMPANY` to the exact company name as shown in Tally. |
| Port conflict | Change the port in both TallyPrime settings and the `TALLYBRIDGE_TALLY_PORT` env var. |

### Important Notes

- The HTTP server port **must be 9000** unless you override `TALLYBRIDGE_TALLY_PORT`.
- TallyPrime must remain open with the company loaded while TallyBridge is running.
- The HTTP server does not require authentication by default, but only supports connections from the local network.
