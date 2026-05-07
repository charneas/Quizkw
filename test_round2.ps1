# PowerShell script to test Round 2 endpoints
Write-Host "Starting Round 2 integration test..." -ForegroundColor Green

# Check if Python requests module is installed
Write-Host "Checking Python dependencies..." -ForegroundColor Yellow
try {
    python -c "import requests" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing requests module..." -ForegroundColor Yellow
        pip install requests
    }
} catch {
    Write-Host "Error checking Python: $_" -ForegroundColor Red
    exit 1
}

# Kill any existing server on port 8000
Write-Host "Checking for existing server on port 8000..." -ForegroundColor Yellow
$existingProcess = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | 
    Select-Object -ExpandProperty OwningProcess -Unique
if ($existingProcess) {
    Write-Host "Stopping existing process PID: $existingProcess" -ForegroundColor Yellow
    Stop-Process -Id $existingProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# Start backend server
Write-Host "Starting backend server..." -ForegroundColor Green
$serverJob = Start-Job -ScriptBlock {
    Set-Location "c:\Users\sebas\Quizkw\backend"
    python main.py
}

# Wait for server to start
Write-Host "Waiting for server to start (5 seconds)..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Test if server is responding
Write-Host "Testing server health..." -ForegroundColor Yellow
try {
    $healthResponse = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 5
    Write-Host "Server health check: $($healthResponse.status)" -ForegroundColor Green
} catch {
    Write-Host "Server not responding, trying to start with uvicorn..." -ForegroundColor Red
    # Try alternative startup
    Stop-Job $serverJob -Force
    Start-Sleep -Seconds 2
    
    $serverJob = Start-Job -ScriptBlock {
        Set-Location "c:\Users\sebas\Quizkw\backend"
        python -m uvicorn main:app --host 0.0.0.0 --port 8000
    }
    Start-Sleep -Seconds 5
    
    try {
        $healthResponse = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 5
        Write-Host "Server health check: $($healthResponse.status)" -ForegroundColor Green
    } catch {
        Write-Host "Failed to start server. Exiting." -ForegroundColor Red
        Stop-Job $serverJob -Force
        exit 1
    }
}

# Run the Python test script
Write-Host "Running Round 2 endpoint tests..." -ForegroundColor Green
Set-Location "c:\Users\sebas\Quizkw"
python test_round2.py

# Capture test results
$testExitCode = $LASTEXITCODE

# Clean up
Write-Host "Stopping backend server..." -ForegroundColor Yellow
Stop-Job $serverJob -Force
Remove-Job $serverJob -Force

# Exit with test result
if ($testExitCode -eq 0) {
    Write-Host "All tests passed!" -ForegroundColor Green
} else {
    Write-Host "Some tests failed." -ForegroundColor Red
}

exit $testExitCode