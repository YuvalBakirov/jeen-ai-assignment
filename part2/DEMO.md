# Customer support demo

Open **Jeen Customer Support** in Langflow. On the canvas, follow the chat input
to the orchestrator and response agent. The orchestrator can call the analysis
agent for a database lookup. The response agent can request a Gmail action.

## Playground

Start one session and send these messages in order. Use a test email address
you control and approve the send only after checking the recipient, subject,
and body.

| Message | What to look for |
| --- | --- |
| `Hello` | A greeting without an SQL query or an email send. |
| `What is the status of Sarah Cohen's request?` | The SQL lookup returns `In Progress`. |
| `What is its priority?` | The flow uses the conversation to identify the request and returns `Medium`. |
| `Send an email to <your test address> with subject Support update and body This is a test of the support flow.` | Gmail waits for approval. After approval, check for a successful send. |
| `What details do you need to send an email?` | The flow explains what it needs without sending anything. |
| `What is the status of the request for Alice Nobody?` | The flow reports that it could not find a matching request. |

## Traces

Open the trace for the question about Sarah. Expand `analyze_support_request`
and look for `run_sql_query`. The tool input contains the query and the output
contains the matching record. In the email trace, open the `send_email` tool
call to see the approved fields and the message ID returned by Gmail.

Compare those runs with the greeting trace. That run has neither a
`run_sql_query` call nor a `send_email` call. Tool components can appear in the
trace when Langflow sets up the flow, even when their actions are never called.

## HTTP POST

From `part2`, run the following in PowerShell. Copy the UUID from the imported
flow's address, after `/flow/`, and replace `YOUR_FLOW_ID`. The script reads the
local Langflow login settings from `.env` and removes its temporary API key
after the run.

```powershell
.\http-demo-local.ps1 -FlowId YOUR_FLOW_ID
```

The script sends the Sarah status question, prints the job ID and polls for the
result. A successful run shows `completed` and returns `In Progress`. Use
`-Question` to try a different question. For the separate API steps and approval
requests, see [Running and checking](README.md#running-and-checking).
