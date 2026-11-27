[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [guid]$FlowId,

    [ValidateNotNullOrEmpty()]
    [string]$Question = "What is Sarah Cohen's request status?"
)

$ErrorActionPreference = 'Stop'
$settings = @{}
Get-Content -LiteralPath (Join-Path $PSScriptRoot '.env') | ForEach-Object {
    if ($_ -match '^\s*([^#=\s]+)\s*=(.*)$') {
        $settings[$matches[1]] = $matches[2].Trim().Trim('"').Trim("'")
    }
}
$port = if ($settings['LANGFLOW_PORT']) { [int]$settings['LANGFLOW_PORT'] } else { 7860 }
$baseUrl = "http://localhost:$port"
$username = if ($settings['LANGFLOW_SUPERUSER']) { $settings['LANGFLOW_SUPERUSER'] } else { 'langflow' }
if (-not $settings['LANGFLOW_SUPERUSER_PASSWORD']) {
    throw 'Set LANGFLOW_SUPERUSER_PASSWORD in part2/.env before running the demo.'
}
Write-Host 'Creating a temporary Langflow API key...' -ForegroundColor Cyan
Invoke-RestMethod -Uri "$baseUrl/api/v1/login" -Method Post -Body @{username=$username; password=$settings['LANGFLOW_SUPERUSER_PASSWORD']} -SessionVariable loginSession | Out-Null
$key = Invoke-RestMethod -Uri "$baseUrl/api/v1/api_key/" -Method Post -WebSession $loginSession -ContentType 'application/json' -Body '{"name":"jeen-http-demo"}'
try {
    $headers = @{ 'x-api-key' = $key.api_key }
    $body = [ordered]@{
        flow_id = $FlowId.ToString()
        input_value = $Question
        session_id = 'http-demo-' + [guid]::NewGuid().ToString('N').Substring(0,8)
        mode = 'background'
    } | ConvertTo-Json
    Write-Host "`nPOST /api/v2/workflows with request:" -ForegroundColor Cyan
    Write-Host $body
    $job = Invoke-RestMethod -Uri "$baseUrl/api/v2/workflows" -Method Post -Headers $headers -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes($body))
    Write-Host "`nJob ID: $($job.job_id)" -ForegroundColor Cyan
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Seconds 2
        $result = Invoke-RestMethod -Uri "$baseUrl/api/v2/workflows?job_id=$($job.job_id)" -Method Get -Headers $headers
        if ($result.status -notin @('queued','in_progress','running','pending')) { break }
    }
    Write-Host "`nGET job status: $($result.status)" -ForegroundColor Cyan
    if ($result.status -ne 'completed' -or -not $result.output.text) {
        throw 'The job did not return an answer. Check the job status and Traces in Langflow.'
    }
    Write-Host "Answer: $($result.output.text)" -ForegroundColor Green
} finally {
    Invoke-RestMethod -Uri "$baseUrl/api/v1/api_key/$($key.id)" -Method Delete -WebSession $loginSession | Out-Null
    Write-Host 'Temporary API key removed.' -ForegroundColor DarkGray
}
