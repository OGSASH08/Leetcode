# 🚀 LeetCode + Striver Sync Setup Guide

## Bhai, iss enhanced version se tum dono platforms ko sync kar sakoge!

### 🎯 **What's New:**
- **Striver A2Z DSA Sheet** tracking
- **Platform identification** (LeetCode vs Striver)
- **Difficulty levels** tracking
- **Separate sync states** for both platforms

---

## 📋 **Environment Variables Setup**

### Create `.env` file:
```bash
# LeetCode Config
LEETCODE_USER=your_leetcode_username

# Striver Config  
STRIVER_USER=your_striver_username
STRIVER_SESSION_COOKIE=optional_for_authenticated_requests

# Google Sheets
GOOGLE_SHEET_ID=your_google_sheet_id
GOOGLE_CREDENTIALS_JSON=your_service_account_json

# Database
DATABASE_URL=your_postgresql_url
```

---

## 📊 **Google Sheet Setup**

### Required Columns (Order matters):
| Column | Description | Example |
|--------|-------------|---------|
| **Platform** | LeetCode या Striver A2Z | LeetCode |
| **Topic** | Problem category | Arrays, Strings |
| **Problem** | Problem name with hyperlink | Two Sum |
| **Difficulty** | Easy/Medium/Hard | Medium |
| **Confidence** | Your confidence level | High |
| **Last Visited** | Last solved date | 01/15/2025 |

### Sheet ka format:
```
Platform    | Topic      | Problem              | Difficulty | Confidence | Last Visited
------------|------------|---------------------|------------|------------|-------------
LeetCode    | Array      | Two Sum             | Easy       |            | 01/15/2025
Striver A2Z | LinkedList | Reverse Linked List | Medium     | High       | 01/16/2025
LeetCode    | String     | Valid Palindrome    | Easy       | Medium     | 01/17/2025
```

---

## 🛠 **Installation & Deployment**

### 1. Local Development:
```bash
# Install dependencies
pip install -r requirements.txt

# Run enhanced app
python enhanced_app.py
```

### 2. Render Deployment:
Update `Procfile`:
```bash
web: gunicorn enhanced_app:app
```

### 3. Vercel Deployment:
Update `vercel.json`:
```json
{
    "version": 2,
    "builds": [
        {
            "src": "./enhanced_app.py",
            "use": "@vercel/python"
        }
    ],
    "routes": [
        {
            "src": "/(.*)",
            "dest": "enhanced_app.py"
        }
    ]
}
```

---

## 🔗 **API Endpoints**

### 1. Health Check:
```bash
GET /
Response: {
  "status": "healthy",
  "platforms": ["LeetCode", "Striver A2Z"],
  "job_running": false
}
```

### 2. Trigger Sync:
```bash
GET /trigger-sync
Response: {
  "status": "success", 
  "message": "Enhanced sync triggered (LeetCode + Striver)"
}
```

### 3. Platform Status:
```bash
GET /platforms
Response: {
  "platforms": {
    "LeetCode": {"enabled": true, "user": "your_username"},
    "Striver": {"enabled": false, "user": null}
  }
}
```

---

## 🔍 **How Striver Integration Works**

### Current Implementation:
1. **Mock Data**: Demo ke liye mock submissions create kiya hai
2. **Topic Mapping**: A2Z DSA course ke topics mapped hain
3. **Future Enhancement**: Real API integration pending

### To Get Real Striver Data:
```javascript
// Browser console mein run karo Striver site pe
// This will help identify API endpoints
console.log('Fetching user progress...');
fetch('/api/user/progress')
  .then(res => res.json())
  .then(data => console.log(data));
```

### Manual Tracking Option:
```python
# enhanced_app.py mein modify karo
def fetch_striver_progress_manual():
    # Manually add completed problems
    return [
        {
            "platform": "Striver A2Z",
            "name": "Reverse Array", 
            "url": "https://takeuforward.org/...",
            "timestamp_utc": datetime.now(UTC),
            "topic_tags": ["Arrays"],
            "difficulty": "Easy"
        }
    ]
```

---

## 🚨 **Important Notes**

### Security:
- **STRIVER_SESSION_COOKIE** sirf trusted environments mein use karo
- Production mein proper authentication implement karo

### Rate Limiting:
- LeetCode API: 0.5 second delay between requests
- Striver: TBD based on actual API limits

### Database Schema:
```sql
-- Enhanced state table supports multiple platforms
CREATE TABLE coding_sync_state (
    key VARCHAR(255) PRIMARY KEY,          -- 'leetcode_timestamp' or 'striver_timestamp'  
    value TIMESTAMPTZ                      -- Last processed timestamp
);
```

---

## 🎉 **Testing the Setup**

### 1. Check Platform Status:
```bash
curl http://localhost:5000/platforms
```

### 2. Trigger Manual Sync:
```bash
curl http://localhost:5000/trigger-sync
```

### 3. Verify Sheet Updates:
- Open your Google Sheet
- Check for new "Platform" column
- Verify problems are tagged correctly

---

## 🔮 **Future Enhancements**

### Planned Features:
1. **CodeChef Integration**
2. **HackerRank Support** 
3. **InterviewBit Tracking**
4. **Custom Problem Addition**
5. **Progress Analytics Dashboard**

### Advanced Striver Integration:
1. **Real API Reverse Engineering**
2. **Problem Difficulty from Striver**
3. **Time Tracking per Problem**
4. **Streak Calculations**

---

## 🆘 **Troubleshooting**

### Common Issues:

1. **"Missing Platform Column"**
   - Solution: Script automatically adds missing headers

2. **"Striver User Not Found"**
   - Check STRIVER_USER environment variable
   - Verify username spelling

3. **"Duplicate Entries"**
   - Each platform-problem combination is unique
   - Same problem from different platforms will have separate entries

4. **"Sync Not Working"**
   - Check logs: `heroku logs --tail` (if on Heroku)
   - Verify environment variables
   - Test individual API endpoints

---

## 📞 **Support**

### Debug Commands:
```python
# Test LeetCode API
python -c "from enhanced_app import fetch_leetcode_submissions; print(len(fetch_leetcode_submissions(datetime.now())))"

# Test Google Sheets
python -c "from enhanced_app import get_gspread_client; client = get_gspread_client(); print('Connected!')"
```

### Contact:
- GitHub Issues ke through questions poocho
- Code review ke liye pull request banao

Happy Coding! 🚀✨