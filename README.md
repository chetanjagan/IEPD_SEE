# 🌿 VegNutri V3 — Personalised Vegetarian Nutrition Coach

Full-stack Flask app. No PostgreSQL, no Docker — just Python.

## 🚀 Quick Start (2 commands)

```bash
pip install flask anthropic
python app.py
# Open http://localhost:5000
```

---

## ✨ All Features (V3)

### Core
| | Feature |
|---|---|
| 👤 | User accounts — register, login, secure sessions |
| 📏 | Smart profile — BMR + TDEE → personalised calorie & protein targets |
| 🍽️ | 7-day meal planning — Indian vegetarian, auto-generated |
| 🔄 | One-click meal regeneration |
| 📖 | Recipe cards — full step-by-step for every meal |
| 📝 | Meal logging — food search, quick-add, daily log |
| 🛒 | Auto grocery list — printable, checkable |
| 📈 | 30-day progress charts — weight, protein, calories |

### New in V3
| | Feature |
|---|---|
| 💧 | **Water Tracker** — SVG ring gauge, quick-add buttons, 7-day chart, hydration tips |
| 🏅 | **Achievements** — 17 badges across 7 categories (streaks, logging, protein, water, weight, mood, custom foods) |
| 📅 | **Nutrition Calendar** — monthly colour-coded view (green = great day, yellow = logged, grey = missed) |
| 🍳 | **My Foods** — personal food library for home-cooked meals with custom nutrition values |
| 😊 | **Mood Tracker** — log daily mood + energy level, spot patterns with history charts |
| 📊 | **Body Stats & BMI** — BMI scale, ideal weight, nutrition targets, vegetarian health insights |
| 💡 | **Daily Nutrition Tips** — 20 rotating expert tips, one shown per day |
| 🤖 | **AI Coach** — chat with Claude, knows your real-time data (profile, today's intake, streak) |
| 🔥 | **Streak System** — daily protein streak with 6 badge levels (🌱→🔥→⚡→💫→💎→🏆) |

---

## 🤖 AI Coach Setup

1. Go to **https://console.anthropic.com** → sign up → API Keys → Create Key  
2. In the app: **AI Coach** → paste key → Save  
3. Ask: *"What should I eat for dinner?"* · *"How do I hit my protein goal?"* · *"Give me a palak paneer recipe"*

The coach knows your profile, today's calories/protein eaten, meal plan, and streak.

---

## 🏅 Achievement Badges

| Category | Examples |
|---|---|
| 🔥 Streak | 3d Sprouting → 7d On Fire → 14d Unstoppable → 30d Diamond |
| 📝 Logging | First Log → 10 meals → 50 meals → 100 meals Centurion |
| 💪 Protein | First protein goal day → 7 days → 30 days Master |
| 💧 Water | First sip → 7 days hitting 2L goal |
| ⚖️ Weight | First weigh-in → 10 consistent logs |
| 😊 Mood | 7 days mindful tracking |
| 🍳 Custom | Add first personal food |

---

## 📁 Project Structure

```
vegnutri/
├── app.py              ← All routes, data, logic (1350+ lines)
├── requirements.txt    ← flask + anthropic
├── nutrition.db        ← SQLite (auto-created on first run)
├── templates/          ← 14 HTML templates
│   ├── base.html       dashboard.html  meal_plan.html
│   ├── log_meal.html   water.html      achievements.html
│   ├── calendar.html   my_foods.html   mood.html
│   ├── body_stats.html ai_coach.html   progress.html
│   ├── grocery.html    setup_profile.html  index.html
│   ├── login.html      register.html
└── static/
    ├── css/style.css   ← 1000+ lines, fully responsive
    └── js/main.js
```

---

## 🛠 Tech Stack
**Backend:** Python 3.9+ · Flask · SQLite  
**AI:** Anthropic Claude API (optional)  
**Frontend:** HTML5 · CSS3 · Vanilla JS · Chart.js  
**No npm, no build step, no Docker required**
