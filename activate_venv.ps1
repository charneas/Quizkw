# PowerShell script to activate the Quizkw backend virtual environment
# Place this script in the project root and run: .\activate_venv.ps1

$backendPath = "backend"

# Check if we're in the right directory
if (Test-Path $backendPath) {
    $venvPath = Join-Path $backendPath "venv"
    
    if (Test-Path $venvPath) {
        $activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
        
        if (Test-Path $activateScript) {
            Write-Host "Activating Quizkw virtual environment..." -ForegroundColor Green
            & $activateScript
            
            # Verify activation
            $pythonPath = (Get-Command python).Source
            Write-Host "Python path: $pythonPath" -ForegroundColor Cyan
            
            if ($pythonPath -match "venv") {
                Write-Host "✅ Virtual environment activated successfully!" -ForegroundColor Green
                Write-Host "You should see '(venv)' in your prompt." -ForegroundColor Yellow
            } else {
                Write-Host "⚠️  Warning: Python path doesn't appear to be in venv" -ForegroundColor Yellow
            }
        } else {
            Write-Host "Error: Activation script not found at $activateScript" -ForegroundColor Red
        }
    } else {
        Write-Host "Error: Virtual environment not found at $venvPath" -ForegroundColor Red
        Write-Host "Run: python -m venv backend\venv" -ForegroundColor Yellow
    }
} else {
    Write-Host "Error: Backend directory not found. Make sure you're in the project root." -ForegroundColor Red
}