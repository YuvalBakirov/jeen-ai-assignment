# Customer Support Flow

This is Part 2 of the assignment. It uses Langflow, Gemini, PostgreSQL, and
Gmail to handle a small customer support scenario. Import `support-flow.json`
to open the flow.

## Flow

- **Orchestrator:** understands the request and calls the analysis agent when
  support data is needed. It passes the request and any findings forward.
- **Analysis Agent:** queries the `support_requests` table using the SQL tool.
- **Response Agent:** writes the answer and can use the Gmail tool. The Gmail
  action has an approval step. After approval or rejection, the response agent
  reports the Gmail result directly, without another Gemini call.

The SQL tool is based on Langflow's SQL Database component. Its output is
formatted as JSON so that every returned column is visible to the agent, even
when a table display would shorten a row.

The orchestrator and response agent run for each message.
The routing instructions ask the orchestrator to use the analysis agent and SQL
tool only when support data is needed. The database user has read-only access
to the sample table.

This is a demo with sample data. It does not verify a customer's identity or
enforce per-customer access, so it should not be used with real customer data.
It reads existing requests; it does not create, edit, or delete requests. The
five supplied email addresses are examples. Use an address you control when
testing email.

## Relation to Part 1

The two parts are separate applications. Part 1 indexes documents and searches
their embeddings; this flow reads support requests and does not use those
documents or embeddings. Each part has its own configuration and database.
Part 2 uses Docker Compose for Langflow and its database. The parts can use
the same Gemini key, in which case they share its usage limits. They also
share the computer's resources. Part 1 exposes PostgreSQL on port 5432 by
default; Part 2 exposes Langflow on port 7860 and keeps its database internal.

## Local setup

Requirements: Docker Desktop with Compose, a Gemini API key, and a Google
Cloud project for the Gmail connection. This setup uses Langflow 1.13.3.
The image includes a small, version-specific fix for dependency ordering when
an approved or rejected run resumes. The build stops if the expected Langflow
source is different.

1. Copy `.env.example` to `.env` in this folder. Set the passwords and
   `GEMINI_API_KEY`. Use letters and numbers for `SUPPORT_READER_PASSWORD`,
   since it is included in a database URL. Keep this file private.
2. Generate a Fernet key with the following command and use the result for
   `LANGFLOW_SECRET_KEY`. Keep the key; changing it makes saved credentials
   unreadable.

   ```text
   python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
   ```

3. From `part2`, run `docker compose up -d --build`. PostgreSQL starts with the
   five sample support requests from the assignment. Open
   `http://localhost:7860` and sign in with the Langflow username and password
   from `.env`.
4. Import the flow JSON in Langflow. The flow uses the `GOOGLE_API_KEY` and
   `SUPPORT_DATABASE_URL` global variables loaded from the local environment.
   The flow uses a connection named `google/jeen_gmail`.

The database setup runs when its Docker volume is first created. Changing the
database passwords in `.env` later does not update an existing database user.

For Gmail, enable the Gmail API in Google Cloud, configure an OAuth consent
screen and add the Google account as a test user. Create an OAuth web client
with this redirect URI:

```text
http://localhost:7860/api/v1/connections/oauth/google/callback
```

Create a private `.env.oauth` file in this folder containing a
`LANGFLOW_CONNECTION_OAUTH_REGISTRATIONS` JSON value with a Google registration
named `google-jeen`. Use the client ID and secret from Google, the redirect URI
above, and only the `https://www.googleapis.com/auth/gmail.send` scope. Do not
add the file to Git or the flow export. Start the service with both files:

```text
LANGFLOW_CONNECTION_OAUTH_REGISTRATIONS={"google-jeen":{"provider":"google","owner":"customer","context":"self_managed","client_type":"confidential","client_id":"YOUR_CLIENT_ID","client_secret":"YOUR_CLIENT_SECRET","redirect_uri":"http://localhost:7860/api/v1/connections/oauth/google/callback","scopes":["https://www.googleapis.com/auth/gmail.send"]}}
```

Replace the placeholders locally. The entire value must stay on one line.

```text
docker compose --env-file .env --env-file .env.oauth -f compose.yaml -f compose.oauth.yaml up -d
```

Use this same command when starting the flow again so the Gmail registration
is included. Both commands use the `jeen-part2` Compose project.

In Langflow settings, create or authorize the `google/jeen_gmail` connection.
Google will ask for permission to send mail. Background use must be enabled on
the connection for Langflow's approval-resume worker. This permits background
flows in the same account to use the connection; review which flows have access
and keep the approval step enabled on the Gmail action.

If the Google OAuth app is in Testing status, a test user's authorization can
expire after seven days. Reauthorize the connection if needed. See Google's
[OAuth audience guidance](https://support.google.com/cloud/answer/15549945).

## Running and checking

Use Playground to chat with the flow. For an HTTP run, use Langflow's v2
Workflows API and a Langflow API key; the v1 run endpoint does not support the
approval step. The request body includes the flow ID, input text, session ID,
and `mode: background`. The response contains a job ID. Poll the job status,
and use the pending and resume endpoints when approval is needed. Never put the
API key in the flow JSON. Use the same session ID to keep the conversation
context and a new session ID for a separate conversation.

For example, create an API key in Langflow, set it as `LANGFLOW_API_KEY` in
your terminal, and replace the flow ID below with the ID of the imported flow.
This PowerShell example runs a greeting and checks the job status:

```powershell
$headers = @{ "x-api-key" = $env:LANGFLOW_API_KEY }
$body = @{
    flow_id = "YOUR_FLOW_ID"
    input_value = "Hello"
    session_id = "support-example-1"
    mode = "background"
} | ConvertTo-Json
$job = Invoke-RestMethod -Method Post -Uri "http://localhost:7860/api/v2/workflows" `
    -Headers $headers -ContentType "application/json" -Body $body
Invoke-RestMethod -Uri "http://localhost:7860/api/v2/workflows?job_id=$($job.job_id)" `
    -Headers $headers
```

If the job is still running, check its status again. A completed job has the
answer in `output.text`. The same message can be sent from Playground.

For email, Playground shows an approval card. With the API, get the pending
request from `GET /api/v2/workflows/pending?flow_id=YOUR_FLOW_ID` and match the
`job_id` to your run. Review the recipient, subject, and body. Send the
`request_id` and `decision` with `action_id` set to `approve` or `reject` to
`POST /api/v2/workflows/{job_id}/resume`, then check the job status again.

Open **Traces** in the flow editor to inspect either run. Open the SQL step
to see the query under Inputs and the returned records under Outputs. For an
approved email, open the Gmail step to see its input and the Gmail message ID.

In a real SQL test, asking for Sarah Cohen's request returned **In Progress**.
Asking for its priority in the same session returned **Medium**. A lookup for
an unknown customer returned a not-found message. Traces showed the SQL tool
for data questions and no tool call when the user asked what details are needed
to send an email. In a combined test, the flow looked up Sarah's request,
prepared a status email, waited for approval, and sent it to the test address.
The sent email was verified in Gmail. Tests also covered rejection, an
unavailable email connection, and a database connection failure.

Gemini can return a service or quota error while preparing a response. When
Gmail returns a message ID, the flow confirms the send. If the request is
declined, the flow says so. If Gmail does not confirm the send, check the tool
output in Traces or the Sent folder before trying again. The flow does not
automatically retry the Gmail tool. Each new send request requires approval.

Some useful checks in Playground are:

- `Hello` should receive a greeting without SQL or Gmail.
- `What is my request status?` should ask for an identifier if none is known.
- `What is Sarah Cohen's request status?` should use SQL and return
  `In Progress` with the supplied sample data.
- `How many requests are open?` should use SQL and return three.
- A request for an unknown customer should report that no record was found.
- An email request missing a subject or body should ask for the missing details.
- A complete email request should pause for approval before the Gmail action.

The wording may vary. Check the agent and tool steps in Traces, especially if
a response does not match the expected behavior.
