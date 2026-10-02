$ErrorActionPreference = 'Stop'
$ruleName = 'TACO License Server LAN Test 5000'
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Firewall rule already exists: $ruleName"
    exit 0
}
New-NetFirewallRule `
    -DisplayName $ruleName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort 5000 `
    -Profile Private `
    -RemoteAddress LocalSubnet | Out-Null
Write-Host "Created Private-profile / LocalSubnet-only rule: $ruleName"
