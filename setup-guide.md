# LeetCode Sync - Complete Setup Guide

## Required Services:

### 1. Database (FREE - Neon.tech)
- Go to: https://neon.tech
- Sign up and create database
- Copy DATABASE_URL

### 2. Google Sheets API
- Go to: https://console.cloud.google.com
- Create project: "LeetCode-Sync"
- Enable Google Sheets API
- Create Service Account
- Download JSON credentials
- Create Google Sheet and share with service account

### 3. Vercel Deployment
- Login to Vercel
- Deploy project
- Add environment variables

## Environment Variables needed:
```
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}
GOOGLE_SHEET_ID=your_sheet_id
DATABASE_URL=postgresql://...
LEETCODE_USER=Sarvesh-Shelgaonkar
```

## Quick Deploy Commands:
```bash
vercel
vercel --prod
```