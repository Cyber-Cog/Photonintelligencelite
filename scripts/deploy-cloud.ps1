<#
.SYNOPSIS
  Neon → Render → Vercel deploy helper for PIC Lite (free tier).

.DESCRIPTION
  Reads secrets from env vars or .deploy-secrets/*.txt (gitignored).
  Does NOT invent secrets. Does NOT commit or push secrets.

  Required files/env (any one of each pair):
    DATABASE_URL              or Neon create via NEON_API_KEY
    RENDER_API_KEY            (or Blueprint already applied in dashboard + RENDER_SERVICE_ID)
    SESSION_SECRET            (default: .deploy-secrets/SESSION_SECRET.txt if present)
    PIC_SUPERADMIN_EMAIL
    PIC_SUPERADMIN_PASSWORD

  Optional:
    NEON_API_KEY              — create project "pic-lite" and fetch pooled URL
    CORS_ORIGINS / PUBLIC_APP_URL — placeholder until Vercel URL known
    VERCEL_ORG_ID / team      — uses current `vercel whoami` login

.EXAMPLE
  # After pasting secrets into .deploy-secrets/ or env:
  pwsh -File scripts/deploy-cloud.ps1
#>
[CmdletBinding()]
param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$SecretsDir = "",
  [string]$NeonProjectName = "pic-lite",
  [string]$RenderServiceName = "pic-lite-api",
  [string]$VercelProjectName = "photonintelligencelite",
  [string]$GitRepo = "https://github.com/Cyber-Cog/Photonintelligencelite",
  [switch]$SkipNeon,
  [switch]$SkipRender,
  [switch]$SkipVercel,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
if (-not $SecretsDir) { $SecretsDir = Join-Path $RepoRoot ".deploy-secrets" }

function Read-Secret([string]$Name) {
  $envVal = [Environment]::GetEnvironmentVariable($Name)
  if ($envVal) { return $envVal.Trim() }
  $file = Join-Path $SecretsDir "$Name.txt"
  if (Test-Path $file) {
    return (Get-Content -Raw $file).Trim()
  }
  return $null
}

function Require-Secret([string]$Name) {
  $v = Read-Secret $Name
  if (-not $v) {
    throw "Missing secret: $Name (set env or create $SecretsDir\$Name.txt)"
  }
  return $v
}

function Write-Step([string]$msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

# --- Load secrets ---
$sessionSecret = Read-Secret "SESSION_SECRET"
if (-not $sessionSecret) {
  throw "SESSION_SECRET missing. Expected $SecretsDir\SESSION_SECRET.txt (generate with: python -c `"import secrets; print(secrets.token_hex(32))`")"
}
$adminEmail = Require-Secret "PIC_SUPERADMIN_EMAIL"
$adminPass = Require-Secret "PIC_SUPERADMIN_PASSWORD"
if ($adminPass.Length -lt 8) { throw "PIC_SUPERADMIN_PASSWORD must be at least 8 characters" }

$databaseUrl = Read-Secret "DATABASE_URL"
$neonKey = Read-Secret "NEON_API_KEY"
$renderKey = Read-Secret "RENDER_API_KEY"
$renderServiceId = Read-Secret "RENDER_SERVICE_ID"

# Placeholder origins until Vercel URL is known (updated in pass 2)
$corsOrigins = Read-Secret "CORS_ORIGINS"
$publicAppUrl = Read-Secret "PUBLIC_APP_URL"
if (-not $corsOrigins) { $corsOrigins = "https://placeholder.vercel.app" }
if (-not $publicAppUrl) { $publicAppUrl = $corsOrigins }

# ========== 1. Neon ==========
if (-not $SkipNeon) {
  Write-Step "Neon: DATABASE_URL"
  if ($databaseUrl) {
    Write-Host "Using provided DATABASE_URL (pooled)."
  } elseif ($neonKey) {
    Write-Host "Creating Neon project '$NeonProjectName' via API..."
    if ($DryRun) {
      Write-Host "[dry-run] would POST https://console.neon.tech/api/v2/projects"
    } else {
      $headers = @{ Authorization = "Bearer $neonKey"; "Content-Type" = "application/json"; Accept = "application/json" }
      $body = @{ project = @{ name = $NeonProjectName; pg_version = 16 } } | ConvertTo-Json -Depth 5
      $created = Invoke-RestMethod -Method Post -Uri "https://console.neon.tech/api/v2/projects" -Headers $headers -Body $body
      $projectId = $created.project.id
      $dbName = $created.databases[0].name
      $roleName = $created.roles[0].name
      $uriResp = Invoke-RestMethod -Method Get -Uri "https://console.neon.tech/api/v2/projects/$projectId/connection_uri?database_name=$dbName&role_name=$roleName&pooled=true" -Headers $headers
      $databaseUrl = $uriResp.uri
      if (-not $databaseUrl) { $databaseUrl = $uriResp.connection_uri }
      if (-not $databaseUrl -and $created.connection_uris) {
        # Prefer pooler host from create response
        $params = $created.connection_uris[0].connection_parameters
        if ($params.pooler_host) {
          $databaseUrl = "postgresql://$($params.role):$($params.password)@$($params.pooler_host)/$($params.database)?sslmode=require"
        } else {
          $databaseUrl = $created.connection_uris[0].connection_uri
        }
      }
      if (-not $databaseUrl) { throw "Neon create succeeded but no connection URI returned" }
      Set-Content -Path (Join-Path $SecretsDir "DATABASE_URL.txt") -Value $databaseUrl -NoNewline
      Set-Content -Path (Join-Path $SecretsDir "NEON_PROJECT_ID.txt") -Value $projectId -NoNewline
      Write-Host "Neon project $projectId ready; pooled URL saved to .deploy-secrets/DATABASE_URL.txt"
    }
  } else {
    throw "Need DATABASE_URL or NEON_API_KEY"
  }
}

# ========== 2. Render ==========
if (-not $SkipRender) {
  Write-Step "Render: API service $RenderServiceName"
  if (-not $renderKey) {
    Write-Host @"
RENDER_API_KEY not set. Preferred path (dashboard):
  1. https://dashboard.render.com → New → Blueprint
  2. Connect GitHub repo Cyber-Cog/Photonintelligencelite
  3. Apply render.yaml (service: pic-lite-api)
  4. Set env vars (sync: false):
       DATABASE_URL, SESSION_SECRET, PIC_SUPERADMIN_EMAIL, PIC_SUPERADMIN_PASSWORD
       CORS_ORIGINS=$corsOrigins
       PUBLIC_APP_URL=$publicAppUrl
  5. Paste RENDER_SERVICE_ID (srv-…) and optional RENDER_API_KEY, then re-run with -SkipNeon

Aborting Render CLI/API steps until key or service id is available.
"@
    if (-not $renderServiceId) { throw "Missing RENDER_API_KEY (or apply Blueprint and set RENDER_SERVICE_ID)" }
  } else {
    $env:RENDER_API_KEY = $renderKey
    $rHeaders = @{ Authorization = "Bearer $renderKey"; Accept = "application/json"; "Content-Type" = "application/json" }

    # Find existing service by name
    if (-not $renderServiceId) {
      $services = Invoke-RestMethod -Method Get -Uri "https://api.render.com/v1/services?limit=50" -Headers $rHeaders
      foreach ($item in $services) {
        $svc = if ($item.service) { $item.service } else { $item }
        if ($svc.name -eq $RenderServiceName) { $renderServiceId = $svc.id; break }
      }
    }

    if (-not $renderServiceId) {
      Write-Host "No existing service named $RenderServiceName. Creating Docker web service from GitHub..."
      if ($DryRun) {
        Write-Host "[dry-run] would POST /v1/services"
      } else {
        $createBody = @{
          type = "web_service"
          name = $RenderServiceName
          repo = $GitRepo
          branch = "main"
          runtime = "docker"
          plan = "free"
          dockerfilePath = "./backend/Dockerfile"
          dockerContext = "."
          healthCheckPath = "/api/health"
          envVars = @(
            @{ key = "PIC_LITE_FREE_TIER"; value = "true" }
            @{ key = "JOB_ROOT"; value = "/tmp/pic-lite-jobs" }
            @{ key = "LOG_LEVEL"; value = "INFO" }
            @{ key = "MAX_CONCURRENT_JOBS"; value = "1" }
            @{ key = "COOKIE_SECURE"; value = "true" }
            @{ key = "AUTH_AUTO_VERIFY"; value = "true" }
            @{ key = "DATABASE_URL"; value = $databaseUrl }
            @{ key = "CORS_ORIGINS"; value = $corsOrigins }
            @{ key = "PUBLIC_APP_URL"; value = $publicAppUrl }
            @{ key = "SESSION_SECRET"; value = $sessionSecret }
            @{ key = "PIC_SUPERADMIN_EMAIL"; value = $adminEmail }
            @{ key = "PIC_SUPERADMIN_PASSWORD"; value = $adminPass }
          )
        } | ConvertTo-Json -Depth 8
        $createdSvc = Invoke-RestMethod -Method Post -Uri "https://api.render.com/v1/services" -Headers $rHeaders -Body $createBody
        $svc = if ($createdSvc.service) { $createdSvc.service } else { $createdSvc }
        $renderServiceId = $svc.id
        Set-Content -Path (Join-Path $SecretsDir "RENDER_SERVICE_ID.txt") -Value $renderServiceId -NoNewline
        Write-Host "Created Render service $renderServiceId"
      }
    } else {
      Write-Host "Updating env vars on $renderServiceId ..."
      if ($DryRun) {
        Write-Host "[dry-run] would PUT env vars on $renderServiceId"
      } else {
        $envBody = @(
          @{ key = "PIC_LITE_FREE_TIER"; value = "true" }
          @{ key = "JOB_ROOT"; value = "/tmp/pic-lite-jobs" }
          @{ key = "LOG_LEVEL"; value = "INFO" }
          @{ key = "MAX_CONCURRENT_JOBS"; value = "1" }
          @{ key = "COOKIE_SECURE"; value = "true" }
          @{ key = "AUTH_AUTO_VERIFY"; value = "true" }
          @{ key = "DATABASE_URL"; value = $databaseUrl }
          @{ key = "CORS_ORIGINS"; value = $corsOrigins }
          @{ key = "PUBLIC_APP_URL"; value = $publicAppUrl }
          @{ key = "SESSION_SECRET"; value = $sessionSecret }
          @{ key = "PIC_SUPERADMIN_EMAIL"; value = $adminEmail }
          @{ key = "PIC_SUPERADMIN_PASSWORD"; value = $adminPass }
        ) | ConvertTo-Json -Depth 6
        Invoke-RestMethod -Method Put -Uri "https://api.render.com/v1/services/$renderServiceId/env-vars" -Headers $rHeaders -Body $envBody | Out-Null
        Invoke-RestMethod -Method Post -Uri "https://api.render.com/v1/services/$renderServiceId/deploys" -Headers $rHeaders -Body "{}" | Out-Null
        Write-Host "Env updated; deploy triggered."
      }
    }

    # Resolve public URL
    if ($renderServiceId -and -not $DryRun) {
      $detail = Invoke-RestMethod -Method Get -Uri "https://api.render.com/v1/services/$renderServiceId" -Headers $rHeaders
      $svc = if ($detail.service) { $detail.service } else { $detail }
      $apiBase = if ($svc.serviceDetails.url) { $svc.serviceDetails.url.TrimEnd("/") } `
        elseif ($svc.serviceDetails.uri) { $svc.serviceDetails.uri.TrimEnd("/") } `
        else { "https://$RenderServiceName.onrender.com" }
      Set-Content -Path (Join-Path $SecretsDir "RENDER_API_URL.txt") -Value $apiBase -NoNewline
      Write-Host "Render API URL: $apiBase"
    }
  }
}

$apiBase = Read-Secret "RENDER_API_URL"
if (-not $apiBase) { $apiBase = "https://$RenderServiceName.onrender.com" }

# ========== 3. Vercel ==========
if (-not $SkipVercel) {
  Write-Step "Vercel: project $VercelProjectName"
  $vercel = Get-Command vercel -ErrorAction SilentlyContinue
  if (-not $vercel) { throw "vercel CLI not found (npm i -g vercel)" }

  Push-Location $RepoRoot
  try {
    if ($DryRun) {
      Write-Host "[dry-run] vercel link / env / --prod"
    } else {
      # Link or create project from repo root (vercel.json builds frontend/)
      $who = & vercel whoami 2>$null
      Write-Host "Logged in as: $who"
      & vercel link --yes --project $VercelProjectName 2>&1 | Out-Host
      # Remove stale var if present, then add (vercel env add reads value from stdin)
      & vercel env rm VITE_API_BASE_URL production --yes 2>$null | Out-Null
      $apiBase | & vercel env add VITE_API_BASE_URL production 2>&1 | Out-Host
      & vercel --prod --yes 2>&1 | Out-Host
      Write-Host "After deploy, copy the Production URL and set Render CORS_ORIGINS + PUBLIC_APP_URL to that exact origin, then redeploy Render."
    }
  } finally {
    Pop-Location
  }
}

Write-Step "Done (or blocked on missing cloud access). Next: health-check Render, login via Vercel, wire CORS pass 2."
Write-Host @"

Verify:
  GET $apiBase/api/health
  Open Vercel URL → login as $adminEmail
"@
