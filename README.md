# 🌿 NutriSage AI — IBM Watsonx.ai Nutrition Agent

> An AI-powered Nutrition Agent built with **Python Flask** + **IBM Watsonx.ai (Granite models)**.  
> Features: Chat UI · Meal Planner · BMI Calculator · Family Profiles · Meal Analyzer · Dark Mode

---

## Live Website
👉 https://nutrition-agent-lo0o.onrender.com


## 📁 Project Structure

```
nutrition/
├── app.py                  ← Flask backend + AGENT_INSTRUCTIONS + API routes
├── requirements.txt        ← Python dependencies
├── .env.example            ← Environment variable template
├── .env                    ← Your actual keys (never commit this!)
├── templates/
│   └── index.html          ← Main HTML (Bootstrap 5, responsive)
└── static/
    ├── css/
    │   └── style.css       ← Custom styles, dark mode, animations
    └── js/
        └── app.js          ← All frontend logic (chat, BMI, tabs, etc.)
```

---

## 🚀 Quick Start

### 1. Clone / download and enter the project folder
```bash
cd nutrition
```

### 2. Create a Python virtual environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure IBM Watsonx credentials
```bash
cp .env.example .env
```
Edit `.env` and fill in your values:
```env
IBM_API_KEY=<your IBM Cloud API Key>
IBM_PROJECT_ID=<your Watsonx.ai project ID>
IBM_REGION=us-south
FLASK_SECRET_KEY=change-this-to-something-random
```

> **How to get credentials:**
> 1. Log in to [IBM Cloud](https://cloud.ibm.com)
> 2. Go to **Manage → Access (IAM) → API Keys** → Create
> 3. Open [IBM Watsonx.ai](https://dataplatform.cloud.ibm.com) → Projects → your project → Manage → copy Project ID

### 5. Run the app
```bash
c
```
Open **http://localhost:5000** in your browser.

---

## 🤖 Customising the Agent (AGENT_INSTRUCTIONS)

Open `app.py` and look for the `AGENT_INSTRUCTIONS` block at the top of the file.  
You can freely edit:

| Setting | What it controls |
|---|---|
| `AGENT_NAME` | Display name of the AI persona |
| `DEFAULT_DIET_TYPE` | `balanced` · `keto` · `vegan` · `diabetic` |
| `DEFAULT_CUISINE` | `Indian` · `Mediterranean` · `Global` |
| `CALORIE_MODEL` | `mifflin-st-jeor` (default) or `harris-benedict` |
| `TEMPERATURE` | Creativity: `0.0` = factual, `1.0` = creative |
| `RESPONSE_MAX_TOKENS` | Max tokens in each AI response |
| `SYSTEM_PROMPT` | Full system prompt injected into every conversation |

---

## 🌐 API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Main application UI |
| GET | `/api/status` | Health check + Watsonx connection status |
| POST | `/api/chat` | General chat with the nutrition agent |
| POST | `/api/nutrition-plan` | Generate personalised 7-day meal plan |
| POST | `/api/bmi` | Calculate BMI + TDEE + AI tips |
| POST | `/api/family-plan` | Generate shared family meal plan |
| POST | `/api/analyze-meal` | Analyse nutritional content of a meal |

### `/api/chat` — Request body
```json
{
  "message": "Create a 1800 kcal vegetarian meal plan",
  "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
  "family_context": { "members": [] }
}
```

### `/api/nutrition-plan` — Request body
```json
{
  "weight": 65, "height": 170, "age": 30,
  "gender": "female", "activity": "moderate",
  "goal": "weight_loss", "diet_type": "vegetarian",
  "cuisine": "Indian", "allergies": "nuts"
}
```

### `/api/bmi` — Request body
```json
{ "weight": 70, "height": 175, "age": 28, "gender": "male", "activity": "light" }
```

### `/api/family-plan` — Request body
```json
{
  "members": [
    {"name": "Raj", "age": 40, "gender": "male", "diet": "balanced", "goals": "maintenance"},
    {"name": "Priya", "age": 35, "gender": "female", "diet": "vegetarian", "goals": "weight_loss"},
    {"name": "Aryan", "age": 10, "gender": "male", "diet": "balanced", "goals": "growth"}
  ]
}
```

### `/api/analyze-meal` — Request body
```json
{ "meal": "2 roti, 1 katori dal, sabzi, curd", "portion": "full plate" }
```

---

## ☁️ Deployment

### Option A — Gunicorn (production server)
```bash
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

### Option B — Docker
```dockerfile
# Dockerfile (place in project root)
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]
```
```bash
docker build -t nutrisage-ai .
docker run -p 5000:5000 --env-file .env nutrisage-ai
```

### Option C — IBM Code Engine (serverless)
```bash
# Build and push image
docker build -t us.icr.io/<namespace>/nutrisage-ai:latest .
docker push us.icr.io/<namespace>/nutrisage-ai:latest

# Deploy
ibmcloud ce application create \
  --name nutrisage-ai \
  --image us.icr.io/<namespace>/nutrisage-ai:latest \
  --port 5000 \
  --env-from-secret nutrisage-secrets
```

### Option D — Railway / Render / Fly.io
Set environment variables (`IBM_API_KEY`, `IBM_PROJECT_ID`, etc.) in the platform dashboard and deploy the repo directly. The `gunicorn` start command is `gunicorn app:app`.

---

## 🛡️ Security Notes

- **Never commit `.env`** — it is already in `.gitignore` by default
- Rotate your IBM API key periodically in IBM Cloud IAM
- In production, set `FLASK_DEBUG=False`
- Add rate-limiting (`flask-limiter`) for public deployments

---

## 🔧 Troubleshooting

| Problem | Solution |
|---|---|
| `Status: Demo Mode` badge | Add `IBM_API_KEY` and `IBM_PROJECT_ID` to `.env` |
| `ModuleNotFoundError: ibm_watsonx_ai` | Run `pip install -r requirements.txt` |
| `401 Unauthorized` from Watsonx | Check API key is valid and not expired |
| `404 Project not found` | Verify `IBM_PROJECT_ID` matches your Watsonx project |
| Slow responses | Normal — Granite inference takes 5–15s for long plans |
| CORS error in browser | Ensure you access via `http://localhost:5000`, not file:// |
| `Failed to build 'pandas'` during `pip install` | `pandas` is a transitive dep of `ibm-watsonx-ai`; the pinned wheel in `requirements.txt` (`pandas==2.2.3`) fixes it. If the error persists, upgrade pip first: `python -m pip install --upgrade pip` |

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `flask` | Web framework |
| `flask-cors` | Cross-origin request support |
| `python-dotenv` | Load secrets from `.env` |
| `ibm-watsonx-ai` | Official IBM Watsonx SDK |
| `gunicorn` | Production WSGI server |

---

## 📄 License

MIT — free to use, modify, and deploy.

---

<p align="center">Made with ❤️ using IBM Watsonx.ai · Granite · Flask · Bootstrap 5</p>
