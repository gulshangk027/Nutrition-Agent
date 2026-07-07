"""
=============================================================================
  AI-POWERED NUTRITION AGENT — IBM Watsonx.ai + Flask
  Powered by Granite Models
=============================================================================

AGENT_INSTRUCTIONS
------------------
Customize the nutrition agent's behavior, tone, and specialization here.
All settings in this block are injected into every prompt sent to Watsonx.ai.

PERSONA & TONE:
  - Name      : NutriSage AI
  - Tone      : Warm, professional, encouraging — never preachy or alarmist
  - Language  : English (can code-switch to Hindi phrases for Indian users)
  - Response  : Concise yet thorough; use bullet points for meal plans

DIET SPECIALIZATION:
  - Primary focus : Indian cuisine (North, South, East, West regional foods)
  - Secondary     : Mediterranean, Keto, Vegan, Diabetic-friendly
  - Avoid         : Recommending foods without checking family restrictions
  - Highlight     : Seasonal ingredients, local superfoods (moringa, turmeric, etc.)

INDIAN FOOD PREFERENCES:
  - Favour dal, sabzi, roti, rice, idli, dosa, poha, upma as base meals
  - Include regional varieties (e.g., Rajasthani dal baati, Bengali fish curry)
  - Respect religious/cultural restrictions (Jain, Sattvic, Halal, Vegan)
  - Use Indian measurements: katori (150 ml), medium roti (~30g), glass (~240 ml)

SAFETY RULES (do NOT override these):
  1. Never diagnose medical conditions or replace professional medical advice
  2. Always recommend consulting a doctor for health issues or clinical diets
  3. Do not suggest supplements beyond standard food sources
  4. Flag if user inputs extreme calorie goals (<1000 or >4000 kcal/day)
  5. Do not store or repeat sensitive personal health data unnecessarily
  6. If a user shows signs of distress, respond empathetically and suggest help

PERSONALIZATION KNOBS (edit values freely):
  DEFAULT_DIET_TYPE   = "balanced"          # balanced | keto | vegan | diabetic
  DEFAULT_CUISINE     = "Indian"            # Indian | Mediterranean | Global
  CALORIE_MODEL       = "mifflin-st-jeor"   # mifflin-st-jeor | harris-benedict
  MAX_FAMILY_MEMBERS  = 8
  RESPONSE_MAX_TOKENS = 900
  TEMPERATURE         = 0.7                 # 0.0=deterministic, 1.0=creative

=============================================================================
"""

import os
import json
import math
import time
import logging
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from dotenv import load_dotenv

# ── IBM Watsonx.ai SDK (optional — we also support direct REST fallback) ──────
try:
    from ibm_watsonx_ai import APIClient, Credentials
    from ibm_watsonx_ai.foundation_models import ModelInference
    from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams
    WATSONX_AVAILABLE = True
except ImportError:
    WATSONX_AVAILABLE = False
    logging.warning("ibm-watsonx-ai not installed — will use REST fallback")

# ── Bootstrap ─────────────────────────────────────────────────────────────────
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "nutrisage-dev-secret-2024")
CORS(app)

# ── Watsonx Config (from .env) ─────────────────────────────────────────────────
IBM_API_KEY    = os.getenv("IBM_API_KEY", "").strip()
IBM_PROJECT_ID = os.getenv("IBM_PROJECT_ID", "").strip()
IBM_REGION     = os.getenv("IBM_REGION", "us-south").strip()
WATSONX_URL    = os.getenv("WATSONX_URL", f"https://{IBM_REGION}.ml.cloud.ibm.com").strip()

# ── Agent Behavior Constants (mirrors AGENT_INSTRUCTIONS above) ───────────────
AGENT_NAME           = "NutriSage AI"
DEFAULT_DIET_TYPE    = "balanced"
DEFAULT_CUISINE      = "Indian"
CALORIE_MODEL        = "mifflin-st-jeor"
MAX_FAMILY_MEMBERS   = 8
RESPONSE_MAX_TOKENS  = 900
TEMPERATURE          = 0.7
# Models tried in order — first successful one wins
CANDIDATE_MODELS     = [
    "meta-llama/llama-3-3-70b-instruct",
    "meta-llama/llama-3-1-8b",
    "ibm/granite-3-1-8b-base",
    "ibm/granite-4-h-small",
    "mistralai/mistral-small-3-1-24b-instruct-2503",
]
GRANITE_MODEL_ID     = CANDIDATE_MODELS[0]   # updated at runtime by _probe_working_combo()

# Watsonx URLs to probe in order (au-syd first since that's where new instances are)
CANDIDATE_URLS       = [
    "https://au-syd.ml.cloud.ibm.com",
    "https://us-south.ml.cloud.ibm.com",
    "https://eu-de.ml.cloud.ibm.com",
    "https://jp-tok.ml.cloud.ibm.com",
]

SYSTEM_PROMPT = f"""You are {AGENT_NAME}, a warm and professional AI nutrition assistant \
specializing in {DEFAULT_CUISINE} cuisine and personalized diet planning. \

Guidelines:
- Provide practical, science-backed nutrition advice tailored to Indian lifestyles
- Use Indian food measurements (katori, roti, glass) and favour local ingredients
- For meal plans, use a clear structured format with breakfast, lunch, dinner, snacks
- Always mention approximate calories for each meal suggestion
- Respect religious/cultural restrictions (Jain, Sattvic, Halal, Vegan) if mentioned
- Include regional Indian dishes relevant to the user's preference
- Be encouraging and positive; never shame or alarm the user
- SAFETY: Never diagnose conditions. Recommend consulting a doctor for medical issues
- SAFETY: Flag extreme calorie goals (<1000 or >4000 kcal/day) as potentially unsafe
- Keep responses concise yet complete; use bullet points and headings where helpful
"""


# ── IAM + Watsonx state ────────────────────────────────────────────────────────
_iam_token        = None
_iam_token_expiry = 0.0
_watsonx_init_error = None
_working_project  = None   # project ID confirmed working at startup
_working_model    = None   # model ID confirmed working at startup

PLACEHOLDER_VALUES = {"", "your_ibm_cloud_api_key_here", "your_watsonx_project_id_here"}


def _is_configured() -> bool:
    return IBM_API_KEY not in PLACEHOLDER_VALUES


def _get_iam_token() -> str | None:
    """Return a cached (or fresh) IAM bearer token."""
    global _iam_token, _iam_token_expiry
    if _iam_token and time.time() < _iam_token_expiry - 60:
        return _iam_token
    try:
        resp = requests.post(
            "https://iam.cloud.ibm.com/identity/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=f"grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey={IBM_API_KEY}",
            timeout=15,
        )
        resp.raise_for_status()
        d = resp.json()
        _iam_token        = d["access_token"]
        _iam_token_expiry = time.time() + int(d.get("expires_in", 3600))
        logger.info("✅ IAM token refreshed")
        return _iam_token
    except Exception as exc:
        logger.error(f"❌ IAM token error: {exc}")
        return None


def _try_chat(token: str, project_id: str, model_id: str, test: bool = False) -> dict | None:
    """
    POST to /ml/v1/text/chat. Returns parsed JSON on HTTP 200, None otherwise.
    If test=True uses a minimal 5-token payload (for probing only).
    """
    payload = {
        "model_id":   model_id,
        "project_id": project_id,
        "messages":   [{"role": "user", "content": "hi"}],
        "parameters": {"max_new_tokens": 5},
    } if test else None   # replaced by caller for real calls

    resp = requests.post(
        f"{WATSONX_URL}/ml/v1/text/chat?version=2024-05-01",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30 if test else 90,
    )
    return resp.json() if resp.status_code == 200 else None


def _list_projects(token: str) -> list[str]:
    """Return all project IDs accessible with this token."""
    try:
        r = requests.get(
            "https://api.dataplatform.cloud.ibm.com/v2/projects?limit=20",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if r.status_code == 200:
            return [p.get("metadata", {}).get("guid", "")
                    for p in r.json().get("resources", []) if p.get("metadata", {}).get("guid")]
    except Exception:
        pass
    return []


def _probe_working_combo() -> bool:
    """
    Try every (url, project, model) combination until one succeeds.
    Sets _working_project, _working_model, WATSONX_URL as side-effects.
    Returns True if a working combo was found.
    """
    global _working_project, _working_model, _watsonx_init_error, GRANITE_MODEL_ID, WATSONX_URL

    if not _is_configured():
        _watsonx_init_error = "IBM_API_KEY not set in .env"
        return False

    token = _get_iam_token()
    if not token:
        _watsonx_init_error = "Failed to obtain IAM token — check IBM_API_KEY"
        return False

    # Build project list: .env value first, then auto-discovered ones
    projects = []
    if IBM_PROJECT_ID not in PLACEHOLDER_VALUES:
        projects.append(IBM_PROJECT_ID)
    projects += [p for p in _list_projects(token) if p not in projects]

    # Build URL list: .env WATSONX_URL first, then region fallbacks
    urls = [WATSONX_URL] if WATSONX_URL else []
    for u in CANDIDATE_URLS:
        if u not in urls:
            urls.append(u)

    logger.info(f"Probing {len(urls)} URL(s) × {len(projects)} project(s) × {len(CANDIDATE_MODELS)} model(s)…")

    for url in urls:
        for pid in projects:
            for mid in CANDIDATE_MODELS:
                try:
                    resp = requests.post(
                        f"{url}/ml/v1/text/chat?version=2024-05-01",
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                        json={
                            "model_id":   mid,
                            "project_id": pid,
                            "messages":   [{"role": "user", "content": "hi"}],
                            "parameters": {"max_new_tokens": 5},
                        },
                        timeout=25,
                    )
                    if resp.status_code == 200:
                        _working_project    = pid
                        _working_model      = mid
                        GRANITE_MODEL_ID    = mid
                        WATSONX_URL         = url
                        _watsonx_init_error = None
                        logger.info(f"✅ Watsonx live — url={url} project={pid[:8]}… model={mid}")
                        return True
                    else:
                        err = resp.json().get("errors", [{}])[0].get("message", "")[:80]
                        logger.debug(f"  skip url={url.split('.')[1]} pid={pid[:8]} model={mid.split('/')[-1]} err={err}")
                except Exception as exc:
                    logger.debug(f"  error {url}: {exc}")

    _watsonx_init_error = "All URL/project/model combos failed — check WML service on IBM Cloud"
    logger.error(f"❌ {_watsonx_init_error}")
    return False


# Run probe once at import time (non-blocking — any error is caught)
try:
    _probe_working_combo()
except Exception:
    pass


def call_watsonx(messages: list[dict]) -> str:
    """Call Watsonx using the confirmed working project + model."""
    global _watsonx_init_error

    if not _working_project or not _working_model:
        # Try re-probe once (handles token expiry / transient errors)
        if not _probe_working_combo():
            return _demo_response(messages)

    token = _get_iam_token()
    if not token:
        return _demo_response(messages)

    payload = {
        "model_id":   _working_model,
        "project_id": _working_project,
        "messages":   messages,
        "parameters": {
            "max_new_tokens":     RESPONSE_MAX_TOKENS,
            "temperature":        TEMPERATURE,
            "top_p":              0.9,
            "repetition_penalty": 1.1,
        },
    }
    try:
        resp = requests.post(
            f"{WATSONX_URL}/ml/v1/text/chat?version=2024-05-01",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=90,
        )
        if resp.status_code != 200:
            logger.error(f"❌ Watsonx {resp.status_code}: {resp.text[:300]}")
            _watsonx_init_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            return _demo_response(messages)

        data    = resp.json()
        choices = data.get("choices") or data.get("results") or []
        if choices:
            choice = choices[0]
            if "message" in choice:
                return choice["message"].get("content", "").strip()
            return (choice.get("text") or choice.get("generated_text") or "").strip()

        _watsonx_init_error = "Unexpected response shape from API"
        return _demo_response(messages)

    except Exception as exc:
        logger.error(f"❌ call_watsonx: {exc}")
        _watsonx_init_error = str(exc)
        return _demo_response(messages)


def get_watsonx_model():
    """Return truthy if a working combo is known, else None (for /api/status)."""
    return _working_model or None


def _demo_response(messages: list[dict]) -> str:
    """Fallback demo responses when Watsonx is unavailable."""
    user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    low = user_msg.lower()
    if "bmi" in low:
        return ("⚠️ **Demo Mode** — Watsonx not connected.\n\n"
                "BMI interpretation: 18.5–24.9 is healthy. For a personalised plan, "
                "connect your IBM API key in the .env file.")
    if "meal" in low or "plan" in low:
        return ("⚠️ **Demo Mode** — Watsonx not connected.\n\n"
                "**Sample Indian Meal Plan (1800 kcal)**\n\n"
                "🌅 **Breakfast:** 2 roti + sabzi + 1 glass milk (~400 kcal)\n"
                "🌞 **Lunch:** 1 cup dal + rice + salad + curd (~550 kcal)\n"
                "🌆 **Snack:** Sprouts chaat + green tea (~150 kcal)\n"
                "🌙 **Dinner:** 2 roti + paneer sabzi + soup (~550 kcal)\n\n"
                "💡 *Connect IBM Watsonx for fully personalised plans.*")
    return ("⚠️ **Demo Mode** — Watsonx not connected.\n\n"
            "I'm NutriSage AI, your personal nutrition assistant. "
            "Please add your IBM API Key and Project ID to the .env file to unlock full AI capabilities. "
            "I can help with meal plans, calorie tracking, BMI analysis, and family diet recommendations.")


# ── BMI & Calorie Helpers ─────────────────────────────────────────────────────
def calculate_bmi(weight_kg: float, height_cm: float) -> dict:
    h_m = height_cm / 100
    bmi = round(weight_kg / (h_m ** 2), 1)
    if bmi < 18.5:
        category, color = "Underweight", "#3b82f6"
    elif bmi < 25.0:
        category, color = "Healthy Weight", "#22c55e"
    elif bmi < 30.0:
        category, color = "Overweight", "#f59e0b"
    else:
        category, color = "Obese", "#ef4444"
    return {"bmi": bmi, "category": category, "color": color}


def calculate_tdee(weight_kg: float, height_cm: float, age: int,
                   gender: str, activity: str) -> dict:
    """Mifflin–St Jeor BMR → TDEE with activity multiplier."""
    if gender.lower() in ("male", "m"):
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

    multipliers = {
        "sedentary": 1.2, "light": 1.375,
        "moderate": 1.55, "active": 1.725, "very_active": 1.9
    }
    mult = multipliers.get(activity.lower(), 1.55)
    tdee = round(bmr * mult)
    return {
        "bmr":           round(bmr),
        "tdee":          tdee,
        "weight_loss":   tdee - 500,
        "weight_gain":   tdee + 500,
        "maintenance":   tdee
    }


# ─────────────────────────────────────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", agent_name=AGENT_NAME)


@app.route("/api/chat", methods=["POST"])
def chat():
    data        = request.get_json(silent=True) or {}
    user_msg    = (data.get("message") or "").strip()
    family_ctx  = data.get("family_context", {})
    history     = data.get("history", [])          # [{role, content}, ...]

    if not user_msg:
        return jsonify({"error": "Message cannot be empty"}), 400

    # Build messages list for Watsonx chat API
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Inject family context if provided
    if family_ctx:
        ctx_lines = ["**Current family profile:**"]
        for member in family_ctx.get("members", []):
            ctx_lines.append(
                f"- {member.get('name','?')} | Age {member.get('age','?')} | "
                f"{member.get('gender','?')} | {member.get('diet','?')} diet | "
                f"Goals: {member.get('goals','?')}"
            )
        messages.append({"role": "system", "content": "\n".join(ctx_lines)})

    # Append conversation history (last 8 turns to stay within token budget)
    for turn in history[-8:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": user_msg})

    response_text = call_watsonx(messages)

    return jsonify({
        "response": response_text,
        "timestamp": datetime.utcnow().isoformat(),
        "model": GRANITE_MODEL_ID
    })


@app.route("/api/nutrition-plan", methods=["POST"])
def nutrition_plan():
    data = request.get_json(silent=True) or {}
    required = ["weight", "height", "age", "gender", "activity", "goal"]
    missing  = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    weight   = float(data["weight"])
    height   = float(data["height"])
    age      = int(data["age"])
    gender   = data["gender"]
    activity = data["activity"]
    goal     = data["goal"]
    diet     = data.get("diet_type", DEFAULT_DIET_TYPE)
    cuisine  = data.get("cuisine", DEFAULT_CUISINE)
    allergies = data.get("allergies", "none")

    bmi_data  = calculate_bmi(weight, height)
    tdee_data = calculate_tdee(weight, height, age, gender, activity)

    target_calories = {
        "weight_loss":   tdee_data["weight_loss"],
        "weight_gain":   tdee_data["weight_gain"],
        "maintenance":   tdee_data["maintenance"],
        "muscle_gain":   tdee_data["weight_gain"],
    }.get(goal, tdee_data["maintenance"])

    prompt = f"""Create a detailed 7-day {diet} meal plan for:
- Age: {age} | Gender: {gender} | Weight: {weight}kg | Height: {height}cm
- BMI: {bmi_data['bmi']} ({bmi_data['category']})
- Daily Calorie Target: {target_calories} kcal | Goal: {goal.replace('_',' ')}
- Cuisine Preference: {cuisine}
- Allergies/Restrictions: {allergies}

Provide:
1. Daily meal plan for Day 1–7 (breakfast, lunch, snack, dinner) with calories
2. Weekly grocery list (grouped by category)
3. 3 key nutrition tips for the goal
4. Daily water intake recommendation

Use Indian food measurements and include local seasonal ingredients where possible."""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt}
    ]
    plan_text = call_watsonx(messages)

    return jsonify({
        "plan":           plan_text,
        "bmi":            bmi_data,
        "tdee":           tdee_data,
        "target_calories": target_calories,
        "goal":           goal
    })


@app.route("/api/bmi", methods=["POST"])
def bmi_route():
    data = request.get_json(silent=True) or {}
    try:
        weight = float(data["weight"])
        height = float(data["height"])
        age    = int(data.get("age", 25))
        gender = data.get("gender", "male")
        activity = data.get("activity", "moderate")
    except (KeyError, ValueError) as exc:
        return jsonify({"error": f"Invalid input: {exc}"}), 400

    bmi_data  = calculate_bmi(weight, height)
    tdee_data = calculate_tdee(weight, height, age, gender, activity)

    # Ask Watsonx for personalised advice
    prompt = (f"My BMI is {bmi_data['bmi']} ({bmi_data['category']}), "
              f"age {age}, {gender}, activity level {activity}. "
              "Give me 5 specific, actionable nutrition tips to improve or maintain my health. "
              "Keep each tip short (1–2 sentences). Use Indian food examples.")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt}
    ]
    tips = call_watsonx(messages)

    return jsonify({**bmi_data, **tdee_data, "ai_tips": tips})


@app.route("/api/family-plan", methods=["POST"])
def family_plan():
    data    = request.get_json(silent=True) or {}
    members = data.get("members", [])
    if not members:
        return jsonify({"error": "No family members provided"}), 400
    if len(members) > MAX_FAMILY_MEMBERS:
        return jsonify({"error": f"Maximum {MAX_FAMILY_MEMBERS} family members allowed"}), 400

    family_desc = "\n".join([
        f"- {m.get('name','?')}: Age {m.get('age','?')}, {m.get('gender','?')}, "
        f"{m.get('diet','balanced')} diet, Goal: {m.get('goals','healthy eating')}"
        for m in members
    ])
    prompt = f"""Create a unified weekly family meal plan for these members:\n{family_desc}

Requirements:
1. One shared meal plan that accommodates all dietary needs
2. Note any modifications for specific members (e.g., less spice for children)
3. Include calorie ranges per meal per member group (children / adults / seniors)
4. Indian cuisine preference with easy-to-cook meals
5. Weekend special meal suggestions
6. Family shopping list for the week"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt}
    ]
    plan_text = call_watsonx(messages)

    return jsonify({"family_plan": plan_text, "member_count": len(members)})


@app.route("/api/analyze-meal", methods=["POST"])
def analyze_meal():
    data    = request.get_json(silent=True) or {}
    meal    = (data.get("meal") or "").strip()
    portion = data.get("portion", "1 serving")
    if not meal:
        return jsonify({"error": "Meal description required"}), 400

    prompt = (f"Analyze the nutritional content of: '{meal}' (portion: {portion}).\n"
              "Provide:\n"
              "1. Estimated calories\n"
              "2. Macros: protein, carbs, fats (in grams)\n"
              "3. Key micronutrients (top 3)\n"
              "4. Healthiness rating (1–10) with brief reason\n"
              "5. One healthier Indian alternative with similar taste\n"
              "Format the numbers clearly.")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt}
    ]
    analysis = call_watsonx(messages)
    return jsonify({"analysis": analysis, "meal": meal, "portion": portion})


@app.route("/api/status", methods=["GET"])
def status():
    model_ready = get_watsonx_model() is not None
    return jsonify({
        "status":            "running",
        "agent":             AGENT_NAME,
        "model":             GRANITE_MODEL_ID,
        "watsonx_connected": model_ready,
        "mode":              "live" if model_ready else "demo",
        "error":             _watsonx_init_error if not model_ready else None,
        "timestamp":         datetime.utcnow().isoformat()
    })


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port  = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    logger.info(f"Starting {AGENT_NAME} on port {port} (debug={debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
