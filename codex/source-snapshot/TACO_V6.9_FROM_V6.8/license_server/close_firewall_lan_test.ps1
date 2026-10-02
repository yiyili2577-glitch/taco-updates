$ruleName = 'TACO License Server LAN Test 5000'
Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Write-Host "Removed firewall rule (if it existed): $ruleName"
