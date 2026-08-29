[CmdletBinding()]
param(
    [string]$FrontendBaseUrl = "http://127.0.0.1:8080"
)

$ErrorActionPreference = "Stop"
$baseUrl = $FrontendBaseUrl.TrimEnd("/")

function Assert-HttpGet {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [int]$ExpectedStatus,
        [switch]$RequireRequestId
    )

    $response = Invoke-WebRequest -Uri "$baseUrl$Path" -Method Get -UseBasicParsing
    if ($response.StatusCode -ne $ExpectedStatus) {
        throw "$Path returned $($response.StatusCode); expected $ExpectedStatus"
    }
    if ($RequireRequestId -and [string]::IsNullOrWhiteSpace($response.Headers["X-Request-ID"])) {
        throw "$Path did not return X-Request-ID"
    }
    Write-Host "PASS $Path ($($response.StatusCode))"
}

Assert-HttpGet -Path "/" -ExpectedStatus 200
Assert-HttpGet -Path "/api/health" -ExpectedStatus 200 -RequireRequestId
Assert-HttpGet -Path "/api/ready" -ExpectedStatus 200 -RequireRequestId
Assert-HttpGet -Path "/api/machines" -ExpectedStatus 200 -RequireRequestId
Assert-HttpGet -Path "/api/capabilities/models" -ExpectedStatus 200 -RequireRequestId

Write-Host "SentinelAI deployment smoke test passed through $baseUrl"
