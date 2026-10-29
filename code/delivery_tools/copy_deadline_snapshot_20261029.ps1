# Delivery only: copies the EC2-verified reports ZIP; no scientific computation.
$ErrorActionPreference = 'Stop'
$delivery = 'D:\LAMOST_Overall_EC2_Handoff_20261023\delivery'
$target = [DateTimeOffset]::Parse('2026-10-29T10:45:00Z')
$cutoff = [DateTimeOffset]::Parse('2026-10-29T11:20:00Z')
$log = Join-Path $delivery 'deadline_copy_20261029.log'
$receiptPath = Join-Path $delivery 'deadline_laptop_delivery_receipt_20261029.json'
$remoteRead = 'echo ZnJvbSBwYXRobGliIGltcG9ydCBQYXRoCmltcG9ydCBqc29uCnA9UGF0aCgnL2hvbWUvdWJ1bnR1L2xhbW9zdF9lMV9taWdyYXRpb25fMjAyNjEwMjMvcnVudGltZV8yMDI2MTAyNS9sb2dzL29wZXJhdGlvbmFsL2RlYWRsaW5lX3NuYXBzaG90X3RpbWVyXzIwMjYxMDI5Lmpzb24nKQp0cnk6ZD1qc29uLmxvYWRzKHAucmVhZF90ZXh0KCkpCmV4Y2VwdCAoT1NFcnJvcixWYWx1ZUVycm9yKTpkPXt9Cno9ZC5nZXQoJ3ppcF9yZWNlaXB0Jykgb3Ige30KcHJpbnQoanNvbi5kdW1wcyh7J3JlYWR5JzpkLmdldCgnemlwX3ZlcmlmaWVkJykgaXMgVHJ1ZSBhbmQgZC5nZXQoJ3N0YXR1cycpPT0ndmVyaWZpZWRfcGFja2FnZScsJ3N0YXR1cyc6ZC5nZXQoJ3N0YXR1cycpLCd6aXBfcGF0aCc6ei5nZXQoJ3ppcF9wYXRoJyksJ3ppcF9ieXRlcyc6ei5nZXQoJ3ppcF9ieXRlcycpLCd6aXBfc2hhMjU2Jzp6LmdldCgnemlwX3NoYTI1NicpLCdjcmNfdGVzdCc6ei5nZXQoJ2NyY190ZXN0Jyl9KSkK | base64 -d | python3'
$mutex = New-Object System.Threading.Mutex($false, 'Local\LAMOSTDeadlineCopy20261029')
if (-not $mutex.WaitOne(0)) { exit 3 }
function Record-Event([string]$message) {
    Add-Content -LiteralPath $log -Value (([DateTimeOffset]::UtcNow.ToString('o')) + ' ' + $message) -Encoding UTF8
}
function Save-Receipt($value) {
    $tmp = $receiptPath + '.tmp.' + $PID
    $value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $tmp -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $receiptPath -Force
}
try {
    $sshExe = (Get-Command ssh.exe -ErrorAction Stop).Source
    $scpExe = (Get-Command scp.exe -ErrorAction Stop).Source
    Record-Event 'Delivery watcher started; target 16:15 IST, cutoff 16:50 IST.'
    while ([DateTimeOffset]::UtcNow -lt $target) { Start-Sleep -Seconds 20 }
    $attempt = 0
    while ([DateTimeOffset]::UtcNow -lt $cutoff) {
        $err = Join-Path $delivery 'deadline_copy_receipt_ssh_20261029.stderr'
        $savedPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $raw = & $sshExe -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 w7-ec2 $remoteRead 2> $err
        $sshExit = $LASTEXITCODE
        $ErrorActionPreference = $savedPreference
        if ($sshExit -ne 0) {
            Record-Event 'Receipt SSH observation failed; no ZIP assumed ready.'
            Start-Sleep -Seconds 20
            continue
        }
        try { $info = ($raw -join [Environment]::NewLine) | ConvertFrom-Json } catch {
            Record-Event 'Receipt JSON unavailable; waiting.'
            Start-Sleep -Seconds 20
            continue
        }
        if (-not $info.ready) { Start-Sleep -Seconds 20; continue }
        $remoteZip = [string]$info.zip_path
        $expectedHash = ([string]$info.zip_sha256).ToLowerInvariant()
        $expectedBytes = [Int64]$info.zip_bytes
        if ($info.crc_test -ne 'passed' -or
            $remoteZip -notmatch '^/home/ubuntu/lamost_e1_migration_20261023/(?:runtime_20261025/)?packages/[A-Za-z0-9_.-]+\.zip$' -or
            $expectedHash -notmatch '^[a-f0-9]{64}$' -or $expectedBytes -le 0 -or $expectedBytes -gt 500000000) {
            throw 'Remote delivery receipt failed path, hash, size, or CRC guards.'
        }
        $leaf = ($remoteZip -split '/')[-1]
        $localZip = Join-Path $delivery $leaf
        $base = [IO.Path]::GetFullPath($delivery) + [IO.Path]::DirectorySeparatorChar
        if (-not [IO.Path]::GetFullPath($localZip).StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Delivery target escaped the established directory.'
        }
        if (Test-Path -LiteralPath $localZip) {
            $existing = Get-Item -LiteralPath $localZip
            $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $localZip).Hash.ToLowerInvariant()
            if ($existing.Length -ne $expectedBytes -or $hash -ne $expectedHash) {
                throw 'Existing delivery filename has different bytes; preserved without overwrite.'
            }
            Save-Receipt ([ordered]@{status='verified_existing_delivery';observed_utc=[DateTimeOffset]::UtcNow.ToString('o');path=$localZip;bytes=$expectedBytes;sha256=$hash;ec2_crc='passed';remote_path=$remoteZip})
            Record-Event 'Existing matching ZIP verified.'
            exit 0
        }
        $attempt++
        if ($attempt -gt 2) { throw 'Two delivery transfer attempts exhausted; partial files preserved.' }
        $partial = $localZip + '.partial.' + $PID + '.' + $attempt
        $stderr = Join-Path $delivery ('deadline_copy_scp_20261029_' + $attempt + '.stderr')
        $source = 'w7-ec2:' + $remoteZip
        $child = Start-Process -FilePath $scpExe -ArgumentList @('-q','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3',$source,$partial) -WindowStyle Hidden -PassThru -RedirectStandardError $stderr
        Record-Event ('Started owned SCP child ' + $child.Id + ', attempt ' + $attempt)
        $started = [DateTimeOffset]::UtcNow
        while (-not $child.HasExited) {
            if (([DateTimeOffset]::UtcNow - $started).TotalSeconds -ge 360 -or [DateTimeOffset]::UtcNow -ge $cutoff) {
                $child.Kill()
                Record-Event 'Stopped own timed-out SCP handle; partial file preserved.'
                break
            }
            Start-Sleep -Seconds 1
            $child.Refresh()
        }
        $child.WaitForExit()
        if (-not (Test-Path -LiteralPath $partial) -or (Get-Item -LiteralPath $partial).Length -ne $expectedBytes) {
            Record-Event ('SCP exit ' + $child.ExitCode + '; exact expected byte count not present.')
            Start-Sleep -Seconds 10
            continue
        }
        $file = Get-Item -LiteralPath $partial
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $partial).Hash.ToLowerInvariant()
        if ($file.Length -ne $expectedBytes -or $hash -ne $expectedHash) {
            throw 'Transferred ZIP size/hash mismatch; partial preserved.'
        }
        if (Test-Path -LiteralPath $localZip) { throw 'Destination appeared during transfer; both files preserved.' }
        Move-Item -LiteralPath $partial -Destination $localZip
        Save-Receipt ([ordered]@{status='verified_delivery';observed_utc=[DateTimeOffset]::UtcNow.ToString('o');path=$localZip;bytes=$expectedBytes;sha256=$hash;ec2_crc='passed';remote_path=$remoteZip;attempt=$attempt;transfer_exit_code=$child.ExitCode;verification_basis='Exact expected byte size and SHA-256; ExitCode may be unavailable on PowerShell'})
        Record-Event ('Verified delivery complete: ' + $leaf)
        exit 0
    }
    throw 'No verified delivery completed by 16:50 IST; previous verified package remains available.'
} catch {
    Record-Event ('Delivery stopped: ' + $_.Exception.Message)
    Save-Receipt ([ordered]@{status='delivery_incomplete';observed_utc=[DateTimeOffset]::UtcNow.ToString('o');reason=$_.Exception.Message;previous_verified_packages_preserved=$true})
    exit 1
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
