# PowerShell script to fix Git secrets issue
# Run this script in your Git repository directory

Write-Host "Fixing Git secrets issue..." -ForegroundColor Green

# Step 1: Remove .env from current staging area and commit
Write-Host "Step 1: Removing .env from Git tracking..." -ForegroundColor Yellow
git rm --cached .env
git commit -m "Remove .env file from tracking to fix secret detection"

# Step 2: Remove .env from Git history using git filter-repo (recommended)
Write-Host "Step 2: Removing .env from Git history..." -ForegroundColor Yellow
if (Get-Command git-filter-repo -ErrorAction SilentlyContinue) {
    git filter-repo --path .env --invert-paths --force
    Write-Host "Used git-filter-repo to clean history" -ForegroundColor Green
} else {
    Write-Host "git-filter-repo not found, using git filter-branch..." -ForegroundColor Yellow
    git filter-branch --force --index-filter 'git rm --cached --ignore-unmatch .env' --prune-empty --tag-name-filter cat -- --all
    
    # Clean up filter-branch refs
    git for-each-ref --format="%(refname)" refs/original/ | ForEach-Object { git update-ref -d $_ }
    git reflog expire --expire=now --all
    git gc --prune=now
}

# Step 3: Force push to origin
Write-Host "Step 3: Force pushing cleaned history..." -ForegroundColor Yellow
git push --force-set-upstream origin main

Write-Host "Done! Your repository should now be clean of secrets." -ForegroundColor Green
Write-Host "Make sure to:" -ForegroundColor Cyan
Write-Host "1. Copy .env.example to .env" -ForegroundColor Cyan
Write-Host "2. Fill in your actual credentials in .env" -ForegroundColor Cyan
Write-Host "3. Never commit .env again (it's in .gitignore)" -ForegroundColor Cyan