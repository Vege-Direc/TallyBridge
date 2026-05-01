# Tally Setup Guide

How to enable the TallyPrime HTTP server so TallyBridge can connect.

## Enable the HTTP Server

### Step 1: Open TallyPrime

Launch TallyPrime and open the company you want to connect to.

### Step 2: Enable Connectivity

**TallyPrime 7.0+:**

1. Press **F1** (Help) → **Settings** → **Advanced Configuration**
2. Set **TallyPrime acts as** → **Server** (or **Both**)
3. Set **Port** → **9000** (TallyBridge default)
4. Accept and save

**TallyPrime 6.x and earlier:**

1. Press **F1** → **Settings** → **Connectivity**
2. Set **TallyPrime acts as** → **Server** (or **Both**)
3. Set **Port** → **9000** (TallyBridge default)
4. Enable **Enable ODBC / Enable HTTP** if present
5. Accept and save

<details>
<summary>Can't find the Connectivity setting?</summary>

On some TallyPrime versions, press **F12** → **Product & Features** → **Advanced** → check **Enable ODBC/HTTP**. The HTTP server port is then configured under **F1** → **Settings** → **Connectivity**.
</details>

> **Tip:** Run `tallybridge setup` to auto-detect TallyPrime on common ports and configure everything interactively.

### Step 3: Verify the Connection

Open a terminal and send a test request:

```bash
curl -X POST http://localhost:9000 \
  -H "Content-Type: text/xml" \
  -d '<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>Ping</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="Ping" ISMODIFY="No"><TYPE>Company</TYPE><FETCH>NAME</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>'
```

If Tally is running correctly, you will receive an XML response listing open company names.

### Step 4: Configure TallyBridge

Set environment variables in your `.env` file:

```env
TALLYBRIDGE_TALLY_HOST=localhost
TALLYBRIDGE_TALLY_PORT=9000
TALLYBRIDGE_TALLY_COMPANY=Your Company Name
```

If TallyPrime is on a different machine, replace `localhost` with the IP address and ensure the firewall allows traffic on port **9000**.

### Step 5: Run the Doctor

```bash
tallybridge doctor
```

This checks Python version, Tally connectivity, database health, and TSS status.

## Troubleshooting

| Problem | Solution |
|---|---|
| Connection refused | TallyPrime is not running or the HTTP server is not enabled. Re-check Step 2. |
| Empty response | Ensure a company is open in TallyPrime. |
| Wrong company data | Set `TALLYBRIDGE_TALLY_COMPANY` to the exact company name as shown in Tally. |
| Port conflict | Change the port in both TallyPrime settings and `TALLYBRIDGE_TALLY_PORT`. |
| TSS expired warning | Local sync still works, but Connected GST and JSON API require active TSS. |

## Feature Compatibility Matrix

| Feature | Tally.ERP 9 | TallyPrime 1–3 | TallyPrime 4–6 | TallyPrime 7.0+ |
|---|:---:|:---:|:---:|:---:|
| XML Export (Collection) | ✓ | ✓ | ✓ | ✓ |
| XML Export (Object) | ✓ | ✓ | ✓ | ✓ |
| XML Export (Data/Report) | ✓ | ✓ | ✓ | ✓ |
| AlterID-based incremental sync | ✓ | ✓ | ✓ | ✓ |
| SVCURRENTCOMPANY | — | ✓ | ✓ | ✓ |
| Connected GST | — | — | ✓ | ✓ |
| Connected Banking | — | — | 6.x+ | ✓ |
| JSON API | — | — | — | ✓ |
| JSONEx format | — | — | — | ✓ |
| Base64 encoding (id-encoded) | — | — | — | ✓ |
| TallyDrive cloud backup | — | — | — | ✓ |
| GSTR-3B JSON export | — | — | — | ✓ |
| E-invoice/e-Way Bill fields | — | — | — | ✓ |

## Secure Remote Access (SSH Tunnel)

When TallyPrime is running on a remote machine, all HTTP data is transmitted **in plaintext**. This includes company names, ledger details, and financial amounts.

### SSH Tunnel Setup

Create an SSH tunnel from your local machine to the Tally server:

```bash
ssh -L 9000:localhost:9000 user@tally-server.example.com -N
```

Then configure TallyBridge to connect to `localhost:9000`:

```env
TALLYBRIDGE_TALLY_HOST=localhost
TALLYBRIDGE_TALLY_PORT=9000
```

All traffic between your machine and the Tally server is encrypted via SSH.

> **Warning:** When `TALLYBRIDGE_TALLY_HOST` is not `localhost`, data is sent unencrypted over the network. Use an SSH tunnel or VPN to protect financial data in transit. Never expose TallyPrime's HTTP port directly to the internet.

## API Explorer & Resources

- **TallyPrime API Explorer** — Available within TallyPrime under **F1 > Settings > Connectivity > API Explorer**. Test XML requests interactively and explore available TDL collections.
- **Online API Explorer** — [tallysolutions.com/tallyprime-api-explorer](https://tallysolutions.com/tallyprime-api-explorer/)
- **Integration Demo Samples** — Download from [Tally Solutions Developer Resources](https://tallysolutions.com/developers/) for working code examples in multiple languages.
- **JSON Integration Docs** — [help.tallysolutions.com/tally-prime-integration-using-json-1](https://help.tallysolutions.com/tally-prime-integration-using-json-1/)
