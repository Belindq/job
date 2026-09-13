$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectDir
New-Item -ItemType Directory -Force logs | Out-Null

function Invoke-JobProfile {
    param(
        [string]$Name,
        [string]$Config,
        [string]$Resume,
        [string]$Output,
        [string]$State,
        [string]$EmailEnv,
        [string]$LogSuffix
    )

    New-Item -ItemType Directory -Force $Output, (Join-Path $Output "pdf"), (Split-Path -Parent $State) | Out-Null
    & py -3 .\src\job_hunter.py --config $Config --resume $Resume --output $Output --state $State *>> ".\logs\job-hunter$LogSuffix.log"
    if ($LASTEXITCODE -ne 0) {
        throw "Job collection failed for profile: $Name"
    }

    if (Test-Path $EmailEnv) {
        & py -3 .\scripts\email_report.py `
            --env $EmailEnv `
            --jobs (Join-Path $Output "jobs.json") `
            --pdf (Join-Path $Output "pdf\job-report.pdf") `
            --sent-state ((Split-Path -Parent $State) + "\email-sent.json") `
            --profile-name $Name `
            *>> ".\logs\email$LogSuffix.log"
        if ($LASTEXITCODE -ne 0) {
            throw "Email delivery failed for profile: $Name"
        }
    }
}

Invoke-JobProfile `
    -Name "Primary" `
    -Config ".\config.json" `
    -Resume ".\profile\resume.txt" `
    -Output ".\output" `
    -State ".\state\jobs.json" `
    -EmailEnv ".\config\email.env" `
    -LogSuffix ""

if (Test-Path ".\profiles") {
    Get-ChildItem ".\profiles" -Directory | ForEach-Object {
        $Profile = $_
        $Config = Join-Path $Profile.FullName "config.json"
        $Resume = Join-Path $Profile.FullName "resume.txt"
        if (-not (Test-Path $Config) -or -not (Test-Path $Resume)) {
            Write-Warning "Skipping incomplete profile: $($Profile.Name)"
            return
        }
        Invoke-JobProfile `
            -Name $Profile.Name `
            -Config $Config `
            -Resume $Resume `
            -Output ".\output\profiles\$($Profile.Name)" `
            -State ".\state\profiles\$($Profile.Name)\jobs.json" `
            -EmailEnv (Join-Path $Profile.FullName "email.env") `
            -LogSuffix "-$($Profile.Name)"
    }
}
