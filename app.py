from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3, os, json, hashlib, random
from datetime import datetime, date, timedelta

app = Flask(__name__)
app.secret_key = 'vegnutri_secret_key_2024_secure'
DATABASE = 'nutrition.db'

# ─────────────────────────────────────────────
#  DB HELPERS
# ─────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db(); c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE NOT NULL,
        age INTEGER, height REAL, weight REAL, gender TEXT,
        goal TEXT, activity_level TEXT, cuisine_preference TEXT,
        allergies TEXT, cooking_time INTEGER,
        daily_calories INTEGER, daily_protein INTEGER,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS meal_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        meal_name TEXT NOT NULL, meal_type TEXT NOT NULL,
        calories INTEGER, protein REAL,
        log_date DATE DEFAULT CURRENT_DATE,
        log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS weight_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        weight REAL NOT NULL, log_date DATE DEFAULT CURRENT_DATE,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS meal_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, plan_date DATE NOT NULL,
        breakfast TEXT, lunch TEXT, snack TEXT, dinner TEXT,
        total_calories INTEGER, total_protein REAL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_settings (
        user_id INTEGER PRIMARY KEY, gemini_api_key TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        role TEXT NOT NULL, content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    # ★ NEW TABLES v3
    c.execute('''CREATE TABLE IF NOT EXISTS water_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        amount_ml INTEGER NOT NULL, log_date DATE DEFAULT CURRENT_DATE,
        log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS custom_foods (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        name TEXT NOT NULL, calories INTEGER, protein REAL,
        carbs REAL DEFAULT 0, fat REAL DEFAULT 0,
        serving_size TEXT DEFAULT '1 serving',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS mood_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        mood TEXT NOT NULL, energy_level INTEGER DEFAULT 3,
        note TEXT DEFAULT '', log_date DATE DEFAULT CURRENT_DATE,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    # Migrate meal_logs: add carbs/fat if missing
    try:
        c.execute('ALTER TABLE meal_logs ADD COLUMN carbs REAL DEFAULT 0')
    except Exception: pass
    try:
        c.execute('ALTER TABLE meal_logs ADD COLUMN fat REAL DEFAULT 0')
    except Exception: pass
    conn.commit(); conn.close()

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

# ─────────────────────────────────────────────
#  NUTRITION CALCULATIONS
# ─────────────────────────────────────────────
def calculate_targets(age, height, weight, gender, goal, activity):
    bmr = (10*weight + 6.25*height - 5*age + 5) if gender == 'male' else (10*weight + 6.25*height - 5*age - 161)
    mult = {'sedentary':1.2,'light':1.375,'moderate':1.55,'active':1.725,'very_active':1.9}
    tdee = bmr * mult.get(activity, 1.2)
    if goal == 'fat_loss':     return int(tdee-500), int(weight*1.8)
    elif goal == 'muscle_gain': return int(tdee+300), int(weight*2.2)
    else:                       return int(tdee),     int(weight*1.6)

# ─────────────────────────────────────────────
#  FOOD DATABASE
# ─────────────────────────────────────────────
FOODS = {
    'Moong Dal (cooked, 1 cup)':   {'cal':212,'pro':14.2}, 'Toor Dal (cooked, 1 cup)':    {'cal':198,'pro':11.0},
    'Masoor Dal (cooked, 1 cup)':  {'cal':230,'pro':18.0}, 'Chana Dal (cooked, 1 cup)':   {'cal':270,'pro':15.0},
    'Urad Dal (cooked, 1 cup)':    {'cal':220,'pro':16.0}, 'Rajma (cooked, 1 cup)':        {'cal':225,'pro':15.4},
    'Chickpeas (cooked, 1 cup)':   {'cal':269,'pro':14.5}, 'Black Chana (cooked, 1 cup)': {'cal':250,'pro':15.0},
    'Paneer (100g)':               {'cal':265,'pro':18.3}, 'Tofu (100g)':                 {'cal':76, 'pro':8.0},
    'Curd / Yogurt (1 cup, 200g)': {'cal':122,'pro':7.0},  'Milk (1 glass, 250ml)':       {'cal':153,'pro':8.0},
    'Brown Rice (cooked, 1 cup)':  {'cal':216,'pro':5.0},  'White Rice (cooked, 1 cup)':  {'cal':200,'pro':4.2},
    'Roti / Chapati (1 piece)':    {'cal':80, 'pro':2.7},  'Oats (dry, 50g)':             {'cal':195,'pro':8.5},
    'Quinoa (cooked, 1 cup)':      {'cal':222,'pro':8.1},  'Peanuts (30g handful)':       {'cal':170,'pro':7.7},
    'Peanut Butter (2 tbsp)':      {'cal':200,'pro':8.0},  'Almonds (30g)':               {'cal':174,'pro':6.4},
    'Roasted Chana (50g)':         {'cal':180,'pro':10.0}, 'Sprouts (1 cup)':             {'cal':82, 'pro':8.7},
    'Spinach (cooked, 1 cup)':     {'cal':41, 'pro':5.4},  'Broccoli (cooked, 1 cup)':    {'cal':55, 'pro':3.7},
    'Green Peas (1 cup)':          {'cal':118,'pro':7.9},  'Potato (medium, boiled)':     {'cal':161,'pro':4.3},
    'Banana (1 medium)':           {'cal':89, 'pro':1.1},  'Apple (1 medium)':            {'cal':72, 'pro':0.4},
    'Greek Yogurt (150g)':         {'cal':100,'pro':17.0}, 'Moong Dal Chilla (2 pieces)': {'cal':220,'pro':12.0},
    'Idli (2 pieces) + Sambar':    {'cal':200,'pro':7.5},  'Masala Dosa + Sambar':        {'cal':350,'pro':8.0},
    'Upma (1 cup)':                {'cal':260,'pro':8.0},  'Poha (1 cup)':                {'cal':240,'pro':5.0},
    'Besan Cheela (2 pieces)':     {'cal':250,'pro':13.0}, 'Dal Tadka (1 cup)':           {'cal':180,'pro':10.0},
    'Palak Paneer (1 cup)':        {'cal':280,'pro':15.0}, 'Chana Masala (1 cup)':        {'cal':270,'pro':14.0},
    'Paneer Butter Masala (1 cup)':{'cal':300,'pro':16.0}, 'Vegetable Khichdi (1 bowl)':  {'cal':350,'pro':12.0},
}

# ─────────────────────────────────────────────
#  MEAL DATABASE
# ─────────────────────────────────────────────
MEALS = {
    'north_indian': {
        'breakfast': [
            {'name':'Moong Dal Chilla + Peanut Chutney + Fruit','cal':320,'pro':18,'mins':20},
            {'name':'Paneer Paratha (2) + Curd','cal':460,'pro':24,'mins':25},
            {'name':'Besan Cheela (2) + Green Chutney','cal':280,'pro':16,'mins':15},
            {'name':'Oats Upma + Peanuts + Chai','cal':360,'pro':15,'mins':15},
            {'name':'Poha + Sprouts + Peanuts','cal':340,'pro':13,'mins':15},
            {'name':'Stuffed Paratha + Curd + Pickle','cal':430,'pro':12,'mins':25},
            {'name':'Oatmeal + Banana + Peanut Butter','cal':400,'pro':14,'mins':10},
        ],
        'lunch': [
            {'name':'Dal Tadka + Brown Rice + Paneer Sabzi + Salad','cal':580,'pro':30,'mins':30},
            {'name':'Rajma Chawal + Raita + Salad','cal':530,'pro':23,'mins':35},
            {'name':'Chole + 2 Rotis + Onion Salad','cal':500,'pro':20,'mins':30},
            {'name':'Palak Paneer + 2 Rotis + Dal','cal':520,'pro':28,'mins':35},
            {'name':'Mixed Dal + Rice + Aloo Sabzi','cal':490,'pro':20,'mins':25},
            {'name':'Paneer Butter Masala + 2 Rotis + Salad','cal':580,'pro':26,'mins':30},
            {'name':'Chana Dal + Rice + Baingan Bharta','cal':500,'pro':19,'mins':35},
        ],
        'snack': [
            {'name':'Roasted Chana + Masala Chai','cal':200,'pro':11,'mins':5},
            {'name':'Peanut Butter + Banana','cal':230,'pro':9,'mins':5},
            {'name':'Sprouts Chaat','cal':160,'pro':10,'mins':10},
            {'name':'Greek Yogurt + Honey + Nuts','cal':180,'pro':14,'mins':5},
            {'name':'Makhana (Fox Nuts, roasted)','cal':170,'pro':5,'mins':5},
            {'name':'Paneer Cubes + Black Pepper','cal':200,'pro':14,'mins':5},
            {'name':'Fruit + Peanut Butter (1 tbsp)','cal':180,'pro':5,'mins':5},
        ],
        'dinner': [
            {'name':'Vegetable Khichdi + Curd','cal':420,'pro':16,'mins':25},
            {'name':'Dal Makhani + 2 Rotis + Salad','cal':490,'pro':22,'mins':30},
            {'name':'Paneer Bhurji + 2 Rotis + Salad','cal':460,'pro':27,'mins':20},
            {'name':'Chana Masala + Brown Rice','cal':460,'pro':20,'mins':30},
            {'name':'Tofu Stir-fry + Quinoa + Veggies','cal':410,'pro':24,'mins':25},
            {'name':'Moong Dal Soup + 2 Rotis + Sabzi','cal':390,'pro':18,'mins':20},
        ]
    },
    'south_indian': {
        'breakfast': [
            {'name':'Idli (3) + Sambar + Coconut Chutney','cal':300,'pro':12,'mins':15},
            {'name':'Masala Dosa + Sambar + Chutney','cal':400,'pro':10,'mins':20},
            {'name':'Upma + Peanuts + Curd','cal':340,'pro':12,'mins':15},
            {'name':'Pesarattu (Green Moong Dosa, 2) + Chutney','cal':290,'pro':17,'mins':20},
            {'name':'Ven Pongal + Sambar','cal':360,'pro':12,'mins':25},
            {'name':'Rava Idli (3) + Sambar','cal':300,'pro':9,'mins':15},
        ],
        'lunch': [
            {'name':'Sambar Rice + Rasam + Papad + Veggies','cal':490,'pro':17,'mins':25},
            {'name':'Curd Rice + Pickle + Pappad','cal':390,'pro':11,'mins':10},
            {'name':'Rajma Sadham + Kootu + Salad','cal':510,'pro':21,'mins':30},
            {'name':'Bisi Bele Bath + Raita','cal':530,'pro':19,'mins':35},
            {'name':'Mor Kuzhambu + Rice + Papad','cal':430,'pro':13,'mins':20},
            {'name':'Rasam + Rice + Kootu + Papad','cal':450,'pro':14,'mins':20},
        ],
        'snack': [
            {'name':'Sundal (Chickpeas) + Chai','cal':190,'pro':10,'mins':10},
            {'name':'Banana + Peanuts','cal':190,'pro':8,'mins':5},
            {'name':'Buttermilk + Peanut Chikki','cal':180,'pro':7,'mins':5},
            {'name':'Curd + Fruits','cal':160,'pro':6,'mins':5},
        ],
        'dinner': [
            {'name':'Chapati (2) + Dal + Sabzi','cal':430,'pro':18,'mins':25},
            {'name':'Appam (2) + Vegetable Stew','cal':390,'pro':11,'mins':25},
            {'name':'Idiyappam (2) + Coconut Milk + Veggie Curry','cal':380,'pro':9,'mins':20},
            {'name':'Uttapam (2) + Sambar + Chutney','cal':370,'pro':10,'mins':20},
        ]
    },
    'gujarati': {
        'breakfast': [
            {'name':'Thepla (2) + Curd + Pickle','cal':350,'pro':12,'mins':20},
            {'name':'Methi Khakhra (3) + Chutney','cal':270,'pro':9,'mins':10},
            {'name':'Moong Dal Dhokla + Green Chutney','cal':260,'pro':14,'mins':25},
            {'name':'Handvo + Curd','cal':340,'pro':15,'mins':30},
            {'name':'Poha + Peanuts + Sev','cal':330,'pro':10,'mins':15},
        ],
        'lunch': [
            {'name':'Dal Dhokli + Ghee + Jaggery','cal':480,'pro':15,'mins':35},
            {'name':'Kadhi + Rice + Sabzi + Papad','cal':460,'pro':14,'mins':30},
            {'name':'Undhiyu + Rice + Chapati','cal':520,'pro':16,'mins':40},
            {'name':'Toor Dal + Rotla + Bhakhri + Shaak','cal':490,'pro':18,'mins':30},
        ],
        'snack': [
            {'name':'Fafda + Green Chutney + Chai','cal':200,'pro':6,'mins':5},
            {'name':'Chikki (Peanut) + Chai','cal':210,'pro':7,'mins':5},
            {'name':'Roasted Makhana + Masala','cal':170,'pro':5,'mins':5},
        ],
        'dinner': [
            {'name':'Khichdi + Kadhi + Papad','cal':410,'pro':15,'mins':25},
            {'name':'Chapati + Dal + Sabzi','cal':420,'pro':17,'mins':25},
            {'name':'Bajra Rotla + Ringan no Olo + Curd','cal':400,'pro':13,'mins':25},
        ]
    },
    'general': {
        'breakfast': [
            {'name':'Oatmeal + Banana + Peanut Butter + Nuts','cal':420,'pro':16,'mins':10},
            {'name':'Scrambled Tofu + Veggies + Toast','cal':360,'pro':20,'mins':15},
            {'name':'Greek Yogurt Bowl + Granola + Berries','cal':350,'pro':19,'mins':5},
            {'name':'Protein Smoothie (Banana, Peanut Butter, Milk)','cal':380,'pro':18,'mins':5},
            {'name':'Paneer Scramble + Whole Grain Toast','cal':400,'pro':22,'mins':10},
        ],
        'lunch': [
            {'name':'Quinoa Buddha Bowl + Chickpeas + Tahini','cal':490,'pro':24,'mins':20},
            {'name':'Lentil Soup + Whole Grain Bread','cal':430,'pro':22,'mins':25},
            {'name':'Tofu Stir-fry + Brown Rice + Veggies','cal':460,'pro':26,'mins':20},
            {'name':'Black Bean Burrito Bowl','cal':500,'pro':20,'mins':20},
        ],
        'snack': [
            {'name':'Mixed Nuts + Dried Fruits','cal':200,'pro':7,'mins':0},
            {'name':'Cottage Cheese + Sliced Fruits','cal':170,'pro':15,'mins':5},
            {'name':'Hummus + Veggie Sticks','cal':180,'pro':7,'mins':5},
            {'name':'Peanut Butter + Apple Slices','cal':220,'pro':8,'mins':5},
        ],
        'dinner': [
            {'name':'Lentil Pasta + Marinara + Salad','cal':430,'pro':22,'mins':20},
            {'name':'Tofu Curry + Brown Rice','cal':440,'pro':23,'mins':25},
            {'name':'Black Bean Tacos (2) + Salsa','cal':420,'pro':19,'mins':20},
            {'name':'Veggie Burger + Salad','cal':450,'pro':20,'mins':20},
        ]
    }
}

def get_meals_for_cuisine(cuisine):
    return MEALS.get(cuisine, MEALS['north_indian'])

def generate_day_plan(profile):
    cuisine = profile['cuisine_preference'] or 'north_indian'
    cooking_time = profile['cooking_time'] or 30
    meals = get_meals_for_cuisine(cuisine)
    def pick(lst):
        eligible = [m for m in lst if m['mins'] <= cooking_time]
        return random.choice(eligible if eligible else lst)
    b=pick(meals['breakfast']); l=pick(meals['lunch']); s=pick(meals['snack']); d=pick(meals['dinner'])
    return {'breakfast':b,'lunch':l,'snack':s,'dinner':d,
            'total_calories':b['cal']+l['cal']+s['cal']+d['cal'],
            'total_protein':b['pro']+l['pro']+s['pro']+d['pro']}

# ─────────────────────────────────────────────
#  ★ FEATURE 1: RECIPES DATABASE
# ─────────────────────────────────────────────
RECIPES = {
    'Moong Dal Chilla + Peanut Chutney + Fruit': {
        'description': 'High-protein savoury pancakes made from green moong dal — a breakfast staple for fitness-focused vegetarians.',
        'prep_time': '10 min (+ 4 hr soak)', 'cook_time': '15 min', 'servings': 2,
        'nutrition': {'cal':320,'pro':18,'carbs':38,'fat':8},
        'ingredients': ['1 cup moong dal (soaked 4 hrs, drained)','1 green chilli','½ inch ginger',
            '½ tsp cumin seeds','Salt to taste','¼ cup finely chopped onion + tomato',
            '2 tbsp chopped coriander','Oil for cooking',
            '— Peanut Chutney —','3 tbsp roasted peanuts','1 green chilli','½ lemon (juice)','Salt + water to blend'],
        'steps': ['Grind soaked moong dal with green chilli, ginger, cumin, and a little water into a thick batter.',
            'Stir in chopped onion, tomato, coriander, and salt.',
            'Heat a non-stick tawa on medium heat, grease with ½ tsp oil.',
            'Pour a ladle of batter and spread in circles — like a dosa.',
            'Cook 2–3 min until edges lift and bottom is golden, then flip and cook 1 min.',
            'For chutney: blend peanuts, chilli, lemon juice, salt and water until smooth.',
            'Serve 2 chillas with chutney and a banana or seasonal fruit.'],
        'tips': 'For extra protein, add 2 tbsp paneer crumbles to the batter before cooking.',
    },
    'Paneer Paratha (2) + Curd': {
        'description': 'Stuffed whole wheat flatbread with spiced crumbled paneer — rich in protein and very filling.',
        'prep_time': '15 min', 'cook_time': '15 min', 'servings': 2,
        'nutrition': {'cal':460,'pro':24,'carbs':48,'fat':18},
        'ingredients': ['1.5 cups whole wheat flour','Water to knead','Salt to taste',
            '— Filling —','150g paneer (crumbled)','½ tsp cumin powder','½ tsp chilli powder',
            '2 tbsp chopped coriander','Salt to taste','1 cup curd for serving'],
        'steps': ['Knead wheat flour, salt and water into a soft dough. Rest 10 min.',
            'Mix crumbled paneer with all spices and coriander. Set aside.',
            'Divide dough into 2 balls. Roll each into a small circle.',
            'Place 2–3 tbsp filling in centre, fold edges over and seal.',
            'Gently roll again into a flat paratha (~6 inch).',
            'Cook on a hot tawa with a little ghee/oil, flipping twice until golden.',
            'Serve with cold curd and pickle.'],
        'tips': 'Press the stuffed paratha gently with a spatula while cooking for even heat distribution.',
    },
    'Besan Cheela (2) + Green Chutney': {
        'description': 'Quick chickpea-flour pancakes — one of the fastest high-protein breakfasts you can make.',
        'prep_time': '5 min', 'cook_time': '10 min', 'servings': 2,
        'nutrition': {'cal':280,'pro':16,'carbs':32,'fat':7},
        'ingredients': ['1 cup besan (chickpea flour)','½ cup water','¼ tsp turmeric',
            '½ tsp ajwain (carom seeds)','1 green chilli (chopped)','2 tbsp chopped onion',
            '2 tbsp chopped coriander','Salt to taste',
            '— Green Chutney —','1 cup coriander leaves','2 green chillies','1 tbsp lemon juice','Salt + water'],
        'steps': ['Whisk besan, water, turmeric, ajwain, and salt into a smooth lump-free batter.',
            'Fold in chopped onion, chilli, and coriander.',
            'Heat a tawa, grease lightly, pour batter and spread thin.',
            'Cook 2–3 min until bubbles form, flip and cook 1 min.',
            'Blend all chutney ingredients until smooth.',
            'Serve 2 cheelas with green chutney.'],
        'tips': 'Add 2 tbsp curd to the batter for softer, fluffier cheelas.',
    },
    'Dal Tadka + Brown Rice + Paneer Sabzi + Salad': {
        'description': 'The classic high-protein vegetarian thali — dal + paneer together give a complete amino acid profile.',
        'prep_time': '10 min', 'cook_time': '30 min', 'servings': 2,
        'nutrition': {'cal':580,'pro':30,'carbs':72,'fat':14},
        'ingredients': ['¾ cup toor dal','1 cup brown rice','200g paneer (cubed)',
            '2 medium tomatoes','1 onion','1 tsp cumin','½ tsp mustard seeds','½ tsp turmeric',
            '1 tsp coriander powder','1 tsp garam masala','2 garlic cloves + 1 inch ginger',
            '2 tbsp oil/ghee','Salt to taste',
            '— Salad —','Cucumber, tomato, onion, lemon juice, salt'],
        'steps': ['Pressure cook toor dal with turmeric and water (3 whistles). Mash and set aside.',
            'Cook brown rice with 2 cups water until done.',
            'For dal tadka: heat ghee, splutter cumin + mustard. Add garlic, ginger, onion — sauté till golden. Add tomatoes + spices. Pour over cooked dal, simmer 5 min.',
            'For paneer sabzi: heat 1 tbsp oil, sauté onion till golden. Add tomatoes, spices. Add paneer cubes, toss gently. Cook 5 min.',
            'Chop salad vegetables, squeeze lemon, add salt.',
            'Serve together as a thali.'],
        'tips': 'Add a squeeze of lemon to dal before serving — it brightens the flavour and improves iron absorption.',
    },
    'Rajma Chawal + Raita + Salad': {
        'description': "North India's favourite comfort food — kidney beans over rice with cooling raita. High protein, high fibre.",
        'prep_time': '8 hr soak + 15 min', 'cook_time': '35 min', 'servings': 2,
        'nutrition': {'cal':530,'pro':23,'carbs':82,'fat':8},
        'ingredients': ['1 cup rajma (soaked overnight)','1 cup basmati or brown rice',
            '2 onions (puréed)','3 tomatoes (puréed)','1 tsp ginger-garlic paste',
            '1 tsp cumin','1 tsp coriander','½ tsp chilli powder','1 tsp garam masala',
            '2 tbsp oil','Salt to taste',
            '— Raita —','1 cup curd','1 cucumber (grated)','cumin powder, salt'],
        'steps': ['Pressure cook soaked rajma with salt and water (6–7 whistles) until soft.',
            'Cook rice separately.',
            'Heat oil in a kadhai. Add cumin, then onion purée — cook 10 min until golden.',
            'Add ginger-garlic paste, cook 2 min. Add tomato purée + all spices, cook 10 min.',
            'Add cooked rajma with some cooking water. Simmer 10 min until thick.',
            'Whisk curd with grated cucumber, cumin powder and salt for raita.',
            'Serve rajma over rice with raita on the side.'],
        'tips': 'Use an Instant Pot to skip overnight soaking — pressure cook dry rajma for 45 min.',
    },
    'Palak Paneer + 2 Rotis + Dal': {
        'description': 'Classic spinach-paneer curry — iron from spinach + protein from paneer = one of the most nutritious vegetarian curries.',
        'prep_time': '10 min', 'cook_time': '25 min', 'servings': 2,
        'nutrition': {'cal':520,'pro':28,'carbs':45,'fat':20},
        'ingredients': ['200g paneer (cubed)','2 large bunches spinach (blanched)',
            '1 onion','2 tomatoes','1 tsp ginger-garlic paste',
            '½ tsp cumin','¼ tsp nutmeg','1 tsp garam masala',
            '2 tbsp cream or cashew paste (optional)','2 tbsp oil','Salt',
            '4 whole wheat rotis','½ cup any dal (cooked, for the side)'],
        'steps': ['Blanch spinach in boiling water 2 min, then transfer to ice water. Blend smooth.',
            'Fry paneer cubes lightly in 1 tsp oil until golden. Set aside.',
            'In same pan, heat oil. Add cumin, then diced onion — sauté 8 min.',
            'Add ginger-garlic paste + tomatoes, cook 8 min until oil separates.',
            'Add spinach purée + all spices, mix well and simmer 5 min.',
            'Add paneer, fold in gently. Simmer 3 min. Stir in cream if using.',
            'Serve with warm rotis and a small bowl of dal.'],
        'tips': 'Blanching and ice-bathing spinach keeps the gravy bright green and preserves nutrients.',
    },
    'Vegetable Khichdi + Curd': {
        'description': "India's original one-pot comfort food — easily digestible, balanced macros, and very soothing.",
        'prep_time': '10 min', 'cook_time': '25 min', 'servings': 2,
        'nutrition': {'cal':420,'pro':16,'carbs':58,'fat':10},
        'ingredients': ['½ cup moong dal','½ cup rice','1 cup mixed vegetables (peas, carrot, beans)',
            '1 tsp cumin','½ tsp turmeric','1 tsp ginger (grated)',
            '1 bay leaf','2 cloves','1 tsp ghee','Salt to taste','1 cup curd for serving'],
        'steps': ['Wash and soak rice + moong dal together 20 min.',
            'Heat ghee in a pressure cooker. Add bay leaf, cloves, cumin — let splutter.',
            'Add ginger, sauté 1 min. Add vegetables, turmeric and salt.',
            'Add drained rice + dal, mix well. Add 3.5 cups water.',
            'Pressure cook 3 whistles on medium heat.',
            'Let pressure release naturally. Adjust consistency with hot water.',
            'Serve with cold curd.'],
        'tips': 'Add 1 tbsp lemon juice after cooking for a flavour boost without extra calories.',
    },
    'Paneer Bhurji + 2 Rotis + Salad': {
        'description': 'Scrambled spiced paneer — the vegetarian answer to scrambled eggs. Fast, high protein, very satisfying.',
        'prep_time': '5 min', 'cook_time': '15 min', 'servings': 2,
        'nutrition': {'cal':460,'pro':27,'carbs':35,'fat':22},
        'ingredients': ['250g paneer (crumbled)','1 onion (finely chopped)','2 tomatoes (chopped)',
            '1 capsicum (chopped)','1 tsp cumin','½ tsp turmeric',
            '1 tsp chilli powder','½ tsp garam masala','2 tbsp oil','Salt + coriander to garnish',
            '4 whole wheat rotis'],
        'steps': ['Heat oil, add cumin. Once it splutters, add onion and sauté 5 min.',
            'Add capsicum, cook 2 min. Add tomatoes + all spices, cook until soft.',
            "Crumble in paneer, fold gently. Cook 3–4 min — don't over-mix.",
            'Garnish with coriander. Serve with warm rotis and a simple cucumber-tomato salad.'],
        'tips': 'Soak packaged paneer in warm water 10 min before using to make it softer.',
    },
    'Chana Masala + Brown Rice': {
        'description': 'Spiced chickpea curry — one of the best plant-based protein sources with complex flavour from whole spices.',
        'prep_time': '8 hr soak + 10 min', 'cook_time': '30 min', 'servings': 2,
        'nutrition': {'cal':460,'pro':20,'carbs':72,'fat':8},
        'ingredients': ['1 cup kabuli chana (soaked overnight)','1 cup brown rice',
            '2 onions (finely chopped)','3 tomatoes (puréed)',
            '1 tsp ginger-garlic paste','1 tsp chana masala powder',
            '1 tsp coriander','½ tsp cumin','½ tsp amchur (dry mango)',
            '2 tbsp oil','Salt + coriander leaves'],
        'steps': ['Pressure cook soaked chana with salt and water — 5 whistles.',
            'Cook brown rice separately.',
            'Heat oil, add cumin. Add onions, fry 10 min until deep golden.',
            'Add ginger-garlic paste, fry 2 min. Add tomato purée + all spices.',
            'Cook masala 10 min until oil separates.',
            'Add cooked chana + some cooking water. Simmer 10–12 min.',
            'Garnish with coriander and a squeeze of lemon. Serve with brown rice.'],
        'tips': "Amchur (dry mango powder) gives that signature tangy punch — don't skip it.",
    },
    'Oatmeal + Banana + Peanut Butter': {
        'description': 'Simple, fast and highly effective — complex carbs + banana sugar + peanut butter protein for sustained energy.',
        'prep_time': '2 min', 'cook_time': '5 min', 'servings': 1,
        'nutrition': {'cal':400,'pro':14,'carbs':52,'fat':14},
        'ingredients': ['½ cup rolled oats','1 cup milk (or water)','1 ripe banana',
            '2 tbsp peanut butter','1 tsp honey (optional)','Pinch of cinnamon'],
        'steps': ['Add oats and milk to a saucepan. Cook on medium heat 3–4 min, stirring.',
            'Pour into a bowl. Top with sliced banana.',
            'Add peanut butter on top — it melts slightly from the heat.',
            'Drizzle honey and sprinkle cinnamon.'],
        'tips': 'Overnight version: soak oats in milk overnight in the fridge. Add toppings in the morning — zero cooking required.',
    },
    'Sprouts Chaat': {
        'description': 'No-cook high-protein snack — sprouted moong are nutritionally superior to cooked, with extra vitamin C.',
        'prep_time': '5 min', 'cook_time': '0 min', 'servings': 1,
        'nutrition': {'cal':160,'pro':10,'carbs':22,'fat':2},
        'ingredients': ['1 cup mixed sprouts (moong + chana)','1 small tomato (chopped)',
            '½ cucumber (chopped)','1 small onion (finely chopped)','1 green chilli (optional)',
            '1 tbsp lemon juice','Chaat masala + salt to taste','Coriander leaves to garnish'],
        'steps': ['If using raw sprouts, microwave or steam 2 min for safety.',
            'Mix all chopped vegetables with sprouts.',
            'Add lemon juice, chaat masala and salt.',
            'Toss well and garnish with coriander.'],
        'tips': 'Grow your own sprouts: soak moong dal overnight, drain, keep in a wet cloth 24–36 hrs. Free protein!',
    },
    'Greek Yogurt + Honey + Nuts': {
        'description': 'Effortless high-protein snack — Greek yogurt has nearly 2x the protein of regular curd.',
        'prep_time': '2 min', 'cook_time': '0 min', 'servings': 1,
        'nutrition': {'cal':180,'pro':14,'carbs':18,'fat':7},
        'ingredients': ['150g Greek yogurt (plain)','1 tsp honey',
            '10 almonds or walnuts (roughly chopped)','Pinch of cinnamon'],
        'steps': ['Spoon Greek yogurt into a bowl.','Drizzle honey on top.',
            'Add chopped nuts and a pinch of cinnamon.',
            'Eat immediately or refrigerate up to 2 hours.'],
        'tips': 'Make your own Greek yogurt: hang regular curd in a muslin cloth 2–3 hours to drain whey. Same protein, half the cost.',
    },
    'Roasted Chana + Masala Chai': {
        'description': 'The simplest high-protein Indian snack — roasted Bengal gram is one of the best protein-per-rupee foods.',
        'prep_time': '1 min', 'cook_time': '5 min', 'servings': 1,
        'nutrition': {'cal':200,'pro':11,'carbs':28,'fat':4},
        'ingredients': ['50g roasted Bengal gram (ready-to-eat)','Chaat masala (optional)','Salt if needed',
            '— Masala Chai —','1 cup water','½ cup milk',
            '1 tsp tea leaves','½ inch ginger','2 cardamom pods','1 tsp sugar'],
        'steps': ['The chana needs no cooking — pour into a bowl and add chaat masala.',
            'For chai: boil water with ginger and crushed cardamom.',
            'Add tea leaves, boil 1 min. Add milk and sugar, boil 2 more min.',
            'Strain and serve alongside the chana.'],
        'tips': '50g roasted chana = 10–11g protein for under ₹10. Best value protein snack in India.',
    },
    'Idli (3) + Sambar + Coconut Chutney': {
        'description': "South India's iconic breakfast — fermented batter idlis with lentil sambar. Light yet nutritious.",
        'prep_time': '12 hr fermentation', 'cook_time': '20 min', 'servings': 2,
        'nutrition': {'cal':300,'pro':12,'carbs':52,'fat':5},
        'ingredients': ['2 cups idli rice + 1 cup urad dal (soaked and blended, fermented 8–12 hrs)',
            '— Sambar —','½ cup toor dal','1 tomato','½ tsp tamarind paste',
            '1 tsp sambar powder','¼ tsp mustard + curry leaves','1 tbsp oil',
            '— Coconut Chutney —','½ cup grated coconut','1 green chilli',
            '1 tbsp roasted chana dal','Salt + water'],
        'steps': ['Blend soaked urad dal smooth. Mix with ground rice batter. Add salt and ferment 8–12 hrs.',
            'Pour batter into greased idli moulds, steam 10–12 min.',
            'For sambar: pressure cook toor dal. Prepare tadka of mustard, curry leaves, tomato + sambar powder. Mix with dal + tamarind. Simmer 8 min.',
            'Blend coconut, chilli, chana dal and salt with water for chutney.',
            'Serve 3 idlis with sambar and chutney.'],
        'tips': 'Use instant idli mix if fermentation feels like too much effort — still a healthy breakfast!',
    },
    'Quinoa Buddha Bowl + Chickpeas + Tahini': {
        'description': 'A complete protein bowl — quinoa is one of the few plant foods with all 9 essential amino acids.',
        'prep_time': '10 min', 'cook_time': '20 min', 'servings': 1,
        'nutrition': {'cal':490,'pro':24,'carbs':58,'fat':16},
        'ingredients': ['½ cup dry quinoa','1 cup cooked chickpeas','1 cup mixed greens',
            '½ roasted sweet potato','½ cucumber + ½ avocado',
            '— Tahini Dressing —','2 tbsp tahini','1 tbsp lemon juice',
            '1 garlic clove (minced)','2 tbsp water','Salt + pepper'],
        'steps': ['Rinse quinoa well, cook in 1 cup water 15 min. Fluff with fork.',
            'Roast sweet potato cubes at 200°C for 20 min with olive oil + salt.',
            'Warm chickpeas in a pan with cumin + salt.',
            'Whisk all dressing ingredients until smooth.',
            'Build bowl: quinoa base, then chickpeas, greens, sweet potato, cucumber, avocado.',
            'Drizzle tahini dressing generously.'],
        'tips': 'Rinse quinoa thoroughly before cooking to remove the bitter coating (saponin).',
    },
    'Tofu Stir-fry + Quinoa + Veggies': {
        'description': 'High-protein tofu with nutty quinoa and stir-fried vegetables — fast, colourful, and filling.',
        'prep_time': '10 min', 'cook_time': '20 min', 'servings': 1,
        'nutrition': {'cal':410,'pro':24,'carbs':42,'fat':14},
        'ingredients': ['200g firm tofu (pressed, cubed)','½ cup quinoa',
            '1 cup mixed vegetables (capsicum, broccoli, peas, carrot)',
            '2 tbsp soy sauce','1 tsp sesame oil','1 tsp ginger-garlic paste',
            '1 tbsp oil','Spring onions + sesame seeds to garnish'],
        'steps': ['Press tofu between paper towels 10 min to remove moisture. Cut into cubes.',
            'Cook quinoa in 1 cup water, 15 min.',
            'Heat oil in a wok on high heat. Add tofu and fry until golden on all sides.',
            'Push tofu aside. Add ginger-garlic, then vegetables. Stir-fry 3–4 min on high.',
            'Add soy sauce and sesame oil. Toss everything together.',
            'Serve over quinoa, garnish with spring onions and sesame.'],
        'tips': 'For crispier tofu: dust with cornflour before frying, or bake at 200°C for 20 min.',
    },
}

def get_recipe(meal_name):
    if meal_name in RECIPES:
        return RECIPES[meal_name]
    for key, recipe in RECIPES.items():
        if key.lower() in meal_name.lower() or meal_name.lower() in key.lower():
            return recipe
    return None

# ─────────────────────────────────────────────
#  ★ FEATURE 2: STREAK SYSTEM
# ─────────────────────────────────────────────
BADGES = [
    {'days':3,  'icon':'🌱','name':'Sprouting',   'desc':'3-day protein streak'},
    {'days':7,  'icon':'🔥','name':'On Fire',      'desc':'7 days straight — one full week!'},
    {'days':14, 'icon':'⚡','name':'Unstoppable',  'desc':'14-day streak — two weeks strong!'},
    {'days':21, 'icon':'💫','name':'Habit Formed', 'desc':'21 days — habit is now permanent!'},
    {'days':30, 'icon':'💎','name':'Diamond',      'desc':'30-day streak — absolutely incredible!'},
    {'days':60, 'icon':'🏆','name':'Legend',       'desc':'60-day streak — you are a legend!'},
]

def get_streak_data(user_id):
    conn = get_db()
    profile = conn.execute('SELECT daily_protein FROM profiles WHERE user_id=?', (user_id,)).fetchone()
    if not profile:
        conn.close()
        return {'current':0,'longest':0,'badges':[],'next_badge':None,'total_days_logged':0}
    target = profile['daily_protein'] * 0.8
    rows = conn.execute('''SELECT log_date, SUM(protein) as total_protein
        FROM meal_logs WHERE user_id=? GROUP BY log_date ORDER BY log_date DESC''', (user_id,)).fetchall()
    conn.close()
    if not rows:
        return {'current':0,'longest':0,'badges':[],'next_badge':None,'total_days_logged':0}
    days_hit = set(r['log_date'] for r in rows if r['total_protein'] >= target)
    total_logged = len(rows)
    # Current streak
    current = 0
    check = date.today()
    for _ in range(365):
        ds = check.isoformat()
        if ds in days_hit:
            current += 1
            check -= timedelta(days=1)
        elif check == date.today():
            check -= timedelta(days=1)  # today not logged yet is OK
        else:
            break
    # Longest streak
    longest = 0
    if days_hit:
        sorted_days = sorted(days_hit)
        run = 1
        for i in range(1, len(sorted_days)):
            prev = date.fromisoformat(sorted_days[i-1])
            curr = date.fromisoformat(sorted_days[i])
            run = run + 1 if (curr - prev).days == 1 else 1
            longest = max(longest, run)
        longest = max(longest, 1 if sorted_days else 0)
    earned     = [b for b in BADGES if longest >= b['days']]
    next_badge = next((b for b in BADGES if longest < b['days']), None)
    return {'current':current,'longest':longest,'badges':earned,'next_badge':next_badge,'total_days_logged':total_logged}

# ─────────────────────────────────────────────
#  GROCERY
# ─────────────────────────────────────────────
GROCERY = {
    '🥦 Proteins & Legumes': [
        ('Moong Dal','500 g'),('Toor Dal','500 g'),('Masoor Dal','250 g'),
        ('Chana Dal','250 g'),('Rajma','500 g'),('Chickpeas (Kabuli)','500 g'),
        ('Paneer','500 g'),('Tofu','400 g'),
    ],
    '🥛 Dairy & Alternatives': [
        ('Curd / Yogurt','1 kg'),('Milk','2 L'),('Greek Yogurt','400 g'),('Paneer (extra)','200 g'),
    ],
    '🌾 Grains & Cereals': [
        ('Brown Rice','1 kg'),('Oats','500 g'),('Whole Wheat Flour','1 kg'),
        ('Quinoa','300 g'),('Semolina (Rava)','250 g'),('Poha','250 g'),
    ],
    '🥕 Vegetables': [
        ('Spinach / Palak','300 g'),('Tomatoes','500 g'),('Onions','500 g'),
        ('Potatoes','500 g'),('Mixed Vegetables','500 g'),('Capsicum','2 pcs'),('Brinjal','2 pcs'),
    ],
    '🍎 Fruits': [
        ('Bananas','1 dozen'),('Apples','6 pcs'),('Seasonal Fruits','500 g'),
    ],
    '🥜 Nuts, Seeds & Condiments': [
        ('Peanuts','250 g'),('Almonds','200 g'),('Peanut Butter','1 jar (350 g)'),
        ('Chia Seeds','100 g'),('Makhana (Fox Nuts)','100 g'),('Roasted Chana','250 g'),
    ],
    '🫙 Spices & Staples': [
        ('Cumin Seeds','50 g'),('Mustard Seeds','50 g'),('Turmeric','50 g'),
        ('Coriander Powder','50 g'),('Garam Masala','50 g'),
        ('Salt','as needed'),('Cooking Oil / Ghee','500 ml'),
    ],
}

# ─────────────────────────────────────────────
#  ★ FEATURE 3: AI COACH HELPERS
# ─────────────────────────────────────────────
def get_api_key(user_id):
    conn = get_db()
    row = conn.execute('SELECT gemini_api_key FROM user_settings WHERE user_id=?',(user_id,)).fetchone()
    conn.close()
    return row['gemini_api_key'] if row else None

def build_coach_system_prompt(user_id):
    conn = get_db()
    profile    = conn.execute('SELECT * FROM profiles WHERE user_id=?',(user_id,)).fetchone()
    username   = conn.execute('SELECT username FROM users WHERE id=?',(user_id,)).fetchone()
    today      = date.today().isoformat()
    today_logs = conn.execute(
        'SELECT meal_name, meal_type, calories, protein FROM meal_logs WHERE user_id=? AND log_date=?',
        (user_id, today)).fetchall()
    plan_row   = conn.execute('SELECT * FROM meal_plans WHERE user_id=? AND plan_date=?',(user_id, today)).fetchone()
    last_wt    = conn.execute('SELECT weight FROM weight_logs WHERE user_id=? ORDER BY log_date DESC LIMIT 1',(user_id,)).fetchone()
    streak     = get_streak_data(user_id)
    conn.close()
    if not profile:
        return "You are VegNutri AI Coach, a helpful vegetarian nutrition assistant for Indian users."
    total_cal = sum(l['calories'] for l in today_logs)
    total_pro = sum(l['protein']  for l in today_logs)
    logs_text = '\n'.join(
        f"  - {l['meal_type'].title()}: {l['meal_name']} ({l['calories']} kcal, {l['protein']}g protein)"
        for l in today_logs) or '  (Nothing logged yet today)'
    plan_text = ''
    if plan_row:
        def pj(v):
            try: return json.loads(v).get('name','?')
            except: return '?'
        plan_text = (f"\nToday's Meal Plan:\n"
                     f"  Breakfast: {pj(plan_row['breakfast'])}\n"
                     f"  Lunch: {pj(plan_row['lunch'])}\n"
                     f"  Snack: {pj(plan_row['snack'])}\n"
                     f"  Dinner: {pj(plan_row['dinner'])}\n")
    goal_map     = {'fat_loss':'Fat Loss','muscle_gain':'Muscle Gain','maintenance':'Maintenance'}
    activity_map = {'sedentary':'Sedentary','light':'Lightly Active','moderate':'Moderately Active',
                    'active':'Very Active','very_active':'Extremely Active'}
    return f"""You are VegNutri AI Coach — a warm, knowledgeable, and encouraging vegetarian nutrition coach.

You are speaking with {username['username'] if username else 'the user'}.

== THEIR PROFILE ==
Age: {profile['age']} | Gender: {profile['gender'].title()} | Height: {profile['height']} cm | Weight: {profile['weight']} kg
Goal: {goal_map.get(profile['goal'], profile['goal'])} | Activity: {activity_map.get(profile['activity_level'], '')}
Cuisine: {profile['cuisine_preference'].replace('_',' ').title()} | Allergies: {profile['allergies'] or 'None'}
Daily Target: {profile['daily_calories']} kcal | Protein Target: {profile['daily_protein']}g
Current Weight: {last_wt['weight'] if last_wt else 'Not logged'} kg
Streak: {streak['current']} day(s) current | {streak['longest']} day(s) longest

== TODAY ({today}) ==
Calories consumed: {total_cal} / {profile['daily_calories']} kcal (remaining: {profile['daily_calories'] - total_cal})
Protein consumed: {total_pro}g / {profile['daily_protein']}g (remaining: {profile['daily_protein'] - total_pro}g)

Today's logged meals:
{logs_text}
{plan_text}
== YOUR ROLE ==
- Answer questions about vegetarian nutrition, protein, their meal plan, and healthy eating
- Suggest specific Indian vegetarian foods and recipes based on their cuisine preference
- If they ask "what should I eat?", recommend based on their remaining calories/protein
- Be concise, warm, and practical — use friendly tone and occasional relevant emojis
- You are a nutrition coach, not a doctor — recommend consulting a doctor for medical issues
- Keep responses to 2–4 paragraphs max unless a recipe is requested"""

def get_recent_chat(user_id, limit=20):
    conn = get_db()
    rows = conn.execute(
        'SELECT role, content FROM chat_history WHERE user_id=? ORDER BY created_at DESC LIMIT ?',
        (user_id, limit)).fetchall()
    conn.close()
    return list(reversed(rows))

def save_message(user_id, role, content):
    conn = get_db()
    conn.execute('INSERT INTO chat_history (user_id, role, content) VALUES (?,?,?)', (user_id, role, content))
    conn.commit(); conn.close()

def clear_chat_history(user_id):
    conn = get_db()
    conn.execute('DELETE FROM chat_history WHERE user_id=?', (user_id,))
    conn.commit(); conn.close()

# ─────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────
@app.route('/')
def index():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email    = request.form['email'].strip()
        password = hash_password(request.form['password'])
        conn = get_db()
        try:
            conn.execute('INSERT INTO users (username, email, password) VALUES (?,?,?)',(username,email,password))
            conn.commit()
            flash('Account created! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists.', 'error')
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = hash_password(request.form['password'])
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE email=? AND password=?',(email,password)).fetchone()
        conn.close()
        if user:
            session['user_id']  = user['id']
            session['username'] = user['username']
            flash(f'Welcome back, {user["username"]}! 🌿', 'success')
            conn = get_db()
            profile = conn.execute('SELECT id FROM profiles WHERE user_id=?',(user['id'],)).fetchone()
            conn.close()
            return redirect(url_for('setup_profile') if not profile else url_for('dashboard'))
        flash('Invalid email or password.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); flash('Logged out.','info'); return redirect(url_for('index'))

@app.route('/profile', methods=['GET','POST'])
def setup_profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        f = request.form
        age=int(f['age']); height=float(f['height']); weight=float(f['weight'])
        gender=f['gender']; goal=f['goal']; activity=f['activity_level']
        cuisine=f['cuisine']; allergies=f.get('allergies',''); cooking_time=int(f['cooking_time'])
        cals, pro = calculate_targets(age, height, weight, gender, goal, activity)
        conn = get_db()
        conn.execute('''INSERT OR REPLACE INTO profiles
            (user_id,age,height,weight,gender,goal,activity_level,cuisine_preference,allergies,cooking_time,daily_calories,daily_protein)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (session['user_id'],age,height,weight,gender,goal,activity,cuisine,allergies,cooking_time,cals,pro))
        conn.commit(); conn.close()
        flash('Profile saved! Your personalised plan is ready. 🎉', 'success')
        return redirect(url_for('dashboard'))
    conn = get_db()
    profile = conn.execute('SELECT * FROM profiles WHERE user_id=?',(session['user_id'],)).fetchone()
    conn.close()
    return render_template('setup_profile.html', profile=profile)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    profile = conn.execute('SELECT * FROM profiles WHERE user_id=?',(session['user_id'],)).fetchone()
    if not profile: conn.close(); return redirect(url_for('setup_profile'))
    today = date.today().isoformat()
    today_logs = conn.execute(
        'SELECT * FROM meal_logs WHERE user_id=? AND log_date=? ORDER BY log_time',(session['user_id'],today)).fetchall()
    total_cal_today = sum(l['calories'] for l in today_logs)
    total_pro_today = sum(l['protein']  for l in today_logs)
    plan_row   = conn.execute('SELECT * FROM meal_plans WHERE user_id=? AND plan_date=?',(session['user_id'],today)).fetchone()
    today_plan = _parse_plan(plan_row)
    days7, pro7 = [], []
    for i in range(6,-1,-1):
        d = (date.today()-timedelta(days=i)).isoformat()
        days7.append(d[-5:])
        row = conn.execute('SELECT SUM(protein) p FROM meal_logs WHERE user_id=? AND log_date=?',(session['user_id'],d)).fetchone()
        pro7.append(round(float(row['p'] or 0),1))
    last_weight = conn.execute('SELECT weight FROM weight_logs WHERE user_id=? ORDER BY log_date DESC LIMIT 1',(session['user_id'],)).fetchone()
    conn.close()
    streak_data  = get_streak_data(session['user_id'])
    water_today  = get_water_today(session['user_id'])
    tip_of_day   = get_tip_of_day()
    achievements = get_achievements(session['user_id'])
    unlocked_cnt = sum(1 for a in achievements if a['unlocked'])
    return render_template('dashboard.html', profile=profile, today_logs=today_logs,
        total_cal_today=total_cal_today, total_pro_today=total_pro_today,
        today_plan=today_plan, days7=days7, pro7=pro7,
        last_weight=last_weight['weight'] if last_weight else None,
        streak_data=streak_data, water_today=water_today, water_goal=WATER_GOAL_ML,
        tip_of_day=tip_of_day, unlocked_cnt=unlocked_cnt, total_ach=len(ALL_ACHIEVEMENTS))

@app.route('/meal-plan')
def meal_plan():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    profile = conn.execute('SELECT * FROM profiles WHERE user_id=?',(session['user_id'],)).fetchone()
    if not profile: conn.close(); flash('Complete your profile first.','warning'); return redirect(url_for('setup_profile'))
    weekly = []
    for i in range(7):
        d = (date.today()+timedelta(days=i)).isoformat()
        row = conn.execute('SELECT * FROM meal_plans WHERE user_id=? AND plan_date=?',(session['user_id'],d)).fetchone()
        if not row:
            plan = generate_day_plan(dict(profile))
            conn.execute('''INSERT INTO meal_plans (user_id,plan_date,breakfast,lunch,snack,dinner,total_calories,total_protein)
                VALUES (?,?,?,?,?,?,?,?)''',
                (session['user_id'],d,json.dumps(plan['breakfast']),json.dumps(plan['lunch']),
                 json.dumps(plan['snack']),json.dumps(plan['dinner']),plan['total_calories'],plan['total_protein']))
            conn.commit()
            row = conn.execute('SELECT * FROM meal_plans WHERE user_id=? AND plan_date=?',(session['user_id'],d)).fetchone()
        weekly.append(_parse_plan(row))
    conn.close()
    return render_template('meal_plan.html', weekly=weekly, profile=profile, today=date.today().isoformat())

@app.route('/regenerate/<plan_date>/<meal_type>', methods=['POST'])
def regenerate(plan_date, meal_type):
    if 'user_id' not in session: return jsonify({'error':'unauth'}), 401
    conn = get_db()
    profile  = conn.execute('SELECT * FROM profiles WHERE user_id=?',(session['user_id'],)).fetchone()
    meals    = get_meals_for_cuisine(profile['cuisine_preference'])
    new_meal = random.choice(meals[meal_type])
    conn.execute(f'UPDATE meal_plans SET {meal_type}=? WHERE user_id=? AND plan_date=?',
                 (json.dumps(new_meal), session['user_id'], plan_date))
    conn.commit(); conn.close()
    return jsonify(new_meal)

@app.route('/log-meal', methods=['GET','POST'])
def log_meal():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        conn = get_db()
        conn.execute('INSERT INTO meal_logs (user_id,meal_name,meal_type,calories,protein,log_date) VALUES (?,?,?,?,?,?)',
                     (session['user_id'],request.form['meal_name'],request.form['meal_type'],
                      int(request.form['calories']),float(request.form['protein']),
                      request.form.get('log_date',date.today().isoformat())))
        conn.commit(); conn.close()
        flash('Meal logged! 🥗', 'success')
        return redirect(url_for('log_meal'))
    conn = get_db()
    today   = date.today().isoformat()
    logs    = conn.execute('SELECT * FROM meal_logs WHERE user_id=? AND log_date=? ORDER BY log_time DESC',(session['user_id'],today)).fetchall()
    profile = conn.execute('SELECT * FROM profiles WHERE user_id=?',(session['user_id'],)).fetchone()
    conn.close()
    total_cal = sum(l['calories'] for l in logs)
    total_pro = sum(l['protein']  for l in logs)
    top_foods = list(FOODS.items())[:20]
    return render_template('log_meal.html', logs=logs, foods=FOODS, top_foods=top_foods,
                           total_cal=total_cal, total_pro=total_pro, profile=profile, today=today)

@app.route('/delete-log/<int:lid>', methods=['POST'])
def delete_log(lid):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    conn.execute('DELETE FROM meal_logs WHERE id=? AND user_id=?',(lid,session['user_id']))
    conn.commit(); conn.close()
    flash('Entry removed.','info')
    return redirect(url_for('log_meal'))

@app.route('/grocery')
def grocery():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('grocery.html', grocery=GROCERY)

@app.route('/progress', methods=['GET','POST'])
def progress():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        conn = get_db()
        conn.execute('INSERT OR REPLACE INTO weight_logs (user_id,weight,log_date) VALUES (?,?,?)',
                     (session['user_id'],float(request.form['weight']),request.form.get('log_date',date.today().isoformat())))
        conn.commit(); conn.close()
        flash('Weight logged! 📊','success')
        return redirect(url_for('progress'))
    conn = get_db()
    profile = conn.execute('SELECT * FROM profiles WHERE user_id=?',(session['user_id'],)).fetchone()
    wt_logs = conn.execute('SELECT * FROM weight_logs WHERE user_id=? ORDER BY log_date ASC LIMIT 30',(session['user_id'],)).fetchall()
    days30, pro30, cal30 = [], [], []
    for i in range(29,-1,-1):
        d = (date.today()-timedelta(days=i)).isoformat()
        days30.append(d[-5:])
        row = conn.execute('SELECT SUM(protein) p, SUM(calories) c FROM meal_logs WHERE user_id=? AND log_date=?',(session['user_id'],d)).fetchone()
        pro30.append(round(float(row['p'] or 0),1))
        cal30.append(round(float(row['c'] or 0),1))
    days_met = sum(1 for p in pro30[-7:] if profile and p >= profile['daily_protein']*0.8)
    score = int(days_met/7*100)
    conn.close()
    return render_template('progress.html', profile=profile, wt_logs=wt_logs,
                           days30=days30, pro30=pro30, cal30=cal30, score=score, today=date.today().isoformat())

# ─────────────────────────────────────────────
#  ★ NEW ROUTES
# ─────────────────────────────────────────────
@app.route('/api/recipe')
def api_recipe():
    meal_name = request.args.get('meal','')
    recipe = get_recipe(meal_name)
    if recipe:
        return jsonify({'found':True,'meal':meal_name,**recipe})
    return jsonify({'found':False,'meal':meal_name})

@app.route('/ai-coach')
def ai_coach():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    profile = conn.execute('SELECT * FROM profiles WHERE user_id=?',(session['user_id'],)).fetchone()
    conn.close()
    api_key    = get_api_key(session['user_id'])
    history    = get_recent_chat(session['user_id'], 30)
    streak_data = get_streak_data(session['user_id'])
    return render_template('ai_coach.html', profile=profile, has_key=bool(api_key),
                           history=history, streak_data=streak_data)

@app.route('/ai-coach/save-key', methods=['POST'])
def save_api_key():
    if 'user_id' not in session: return redirect(url_for('login'))
    key = request.form.get('api_key','').strip()
    if not key.startswith('AIza'):
        flash('Invalid API key — Gemini keys start with AIza', 'error')
        return redirect(url_for('ai_coach'))
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO user_settings (user_id, gemini_api_key) VALUES (?,?)',(session['user_id'],key))
    conn.commit(); conn.close()
    flash('API key saved! Your AI Coach is ready. 🤖', 'success')
    return redirect(url_for('ai_coach'))

@app.route('/ai-coach/clear', methods=['POST'])
def clear_chat():
    if 'user_id' not in session: return redirect(url_for('login'))
    clear_chat_history(session['user_id'])
    flash('Chat cleared.','info')
    return redirect(url_for('ai_coach'))

@app.route('/api/chat', methods=['POST'])
def api_chat():
    if 'user_id' not in session: return jsonify({'error':'Not logged in'}), 401
    data    = request.get_json()
    message = (data or {}).get('message','').strip()
    if not message: return jsonify({'error':'Empty message'}), 400
    api_key = get_api_key(session['user_id'])
    if not api_key:
        return jsonify({'error':'no_key','message':'Please add your Gemini API key in the settings panel first.'}), 400
    history  = get_recent_chat(session['user_id'], 20)
    messages = [{'role':r['role'],'content':r['content']} for r in history]
    messages.append({'role':'user','content':message})
    save_message(session['user_id'], 'user', message)
    try:
        import urllib.request, urllib.error
        system_prompt = build_coach_system_prompt(session['user_id'])
        # Build Gemini request - inject system as first user turn
        gemini_messages = []
        # Add system context as first user message if no history
        if not history:
            gemini_messages.append({
                'role': 'user',
                'parts': [{'text': system_prompt + '\n\nUser: ' + message}]
            })
        else:
            gemini_messages.append({
                'role': 'user',
                'parts': [{'text': system_prompt}]
            })
            gemini_messages.append({
                'role': 'model',
                'parts': [{'text': 'Understood! I am your VegNutri AI Coach. I have your full profile and nutrition data. How can I help you today?'}]
            })
            for m in messages[:-1]:  # all except last (new message)
                role = 'model' if m['role'] == 'assistant' else 'user'
                gemini_messages.append({'role': role, 'parts': [{'text': m['content']}]})
            gemini_messages.append({'role': 'user', 'parts': [{'text': message}]})

        payload = json.dumps({
            'contents': gemini_messages,
            'generationConfig': {
                'temperature': 0.7,
                'maxOutputTokens': 800,
                'topP': 0.9,
            },
            'safetySettings': [
                {'category': 'HARM_CATEGORY_HARASSMENT', 'threshold': 'BLOCK_ONLY_HIGH'},
                {'category': 'HARM_CATEGORY_HATE_SPEECH', 'threshold': 'BLOCK_ONLY_HIGH'},
            ]
        }).encode('utf-8')

        # Preferred models in order of priority (updated April 2026)
        PREFERRED_MODELS = ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.0-flash', 'gemini-2.0-flash-lite']

        # Dynamically fetch available models to avoid using deprecated ones
        def get_available_model_names(key):
            try:
                list_url = f'https://generativelanguage.googleapis.com/v1beta/models?key={key}&pageSize=50'
                list_req = urllib.request.Request(list_url)
                with urllib.request.urlopen(list_req, timeout=10) as r:
                    data = json.loads(r.read().decode('utf-8'))
                available = set()
                for m in data.get('models', []):
                    name = m.get('name', '').replace('models/', '')
                    if 'generateContent' in m.get('supportedGenerationMethods', []):
                        available.add(name)
                return available
            except Exception:
                return set()

        available_names = get_available_model_names(api_key)
        if available_names:
            models_to_try = [m for m in PREFERRED_MODELS if m in available_names] or PREFERRED_MODELS
        else:
            models_to_try = PREFERRED_MODELS
        all_errors = []
        last_error = None

        for model in models_to_try:
            url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}'
            req = urllib.request.Request(url, data=payload,
                                         headers={'Content-Type': 'application/json'}, method='POST')
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read().decode('utf-8'))
                # Success
                candidates = result.get('candidates', [])
                if not candidates:
                    # Safety filter or empty response
                    reply = "I couldn't generate a response for that. Could you rephrase your question?"
                else:
                    reply = candidates[0]['content']['parts'][0]['text']
                save_message(session['user_id'], 'assistant', reply)
                return jsonify({'reply': reply, 'model': model})
            except urllib.error.HTTPError as e:
                body = e.read().decode('utf-8', errors='ignore')
                import sys
                print(f"[AI Coach] Model={model} HTTP {e.code}: {body[:300]}", file=sys.stderr)
                if e.code == 429:
                    last_error = ('rate_limit', model)
                    import time; time.sleep(3)
                    continue
                elif e.code == 400:
                    # Parse Gemini error message if available
                    try:
                        err_json = json.loads(body)
                        gemini_msg = err_json.get('error', {}).get('message', body[:200])
                    except Exception:
                        gemini_msg = body[:200]
                    return jsonify({'error': 'api_error',
                                    'message': f'❌ Gemini 400 error on {model}: {gemini_msg}'}), 400
                elif e.code == 403:
                    return jsonify({'error': 'api_error',
                                    'message': '❌ API key rejected (403). Check your key at aistudio.google.com'}), 400
                else:
                    last_error = ('http', e.code, body[:300])
                    all_errors.append(f'{model}=HTTP{e.code}')
                    continue

        # All models exhausted
        if last_error and last_error[0] == 'rate_limit':
            return jsonify({
                'error': 'rate_limit',
                'message': '⏳ Rate limit hit on all models. Please wait 10–15 seconds and try again.',
                'retry_after': 15
            }), 429
        if last_error and last_error[0] == 'http':
            _, code, body = last_error
            summary = ' | '.join(all_errors) if all_errors else 'unknown'
            return jsonify({'error': 'api_error',
                            'message': f'❌ All models failed ({summary}). Last: HTTP {code}: {body}'}), 500
        return jsonify({'error': 'api_error', 'message': 'API error — unknown failure.'}), 500

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        if e.code in (400, 403):
            msg = '❌ Invalid API key. Get yours free at aistudio.google.com'
        elif e.code == 429:
            msg = '⏳ Rate limit. Please wait a moment and try again.'
        else:
            msg = f'API error {e.code}'
        return jsonify({'error': 'api_error', 'message': msg}), 500
    except Exception as e:
        err = str(e)
        if 'timeout' in err.lower():
            msg = '⏳ Request timed out. Please try again.'
        else:
            msg = f'Something went wrong: {err[:100]}'
        return jsonify({'error': 'api_error', 'message': msg}), 500

@app.route('/api/search-food')
def search_food():
    q = request.args.get('q','').lower()
    results = [{'name':k,'cal':v['cal'],'pro':v['pro']} for k,v in FOODS.items() if q in k.lower()]
    return jsonify(results)

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def _parse_plan(row):
    if not row: return None
    def sj(v):
        try: return json.loads(v)
        except: return {}
    return {'plan_date':row['plan_date'],'breakfast':sj(row['breakfast']),'lunch':sj(row['lunch']),
            'snack':sj(row['snack']),'dinner':sj(row['dinner']),
            'total_calories':row['total_calories'],'total_protein':row['total_protein']}

# ═══════════════════════════════════════════════
#  ★★★ V3 FEATURES ★★★
# ═══════════════════════════════════════════════

# ─── NUTRITION TIPS ────────────────────────────
DAILY_TIPS = [
    {"icon":"💪","tip":"Combine dal + rice to get all 9 essential amino acids in one meal. Together they form a complete protein."},
    {"icon":"🥛","tip":"Greek yogurt has ~17g protein per 150g — nearly 2x regular curd. Swap it into your breakfast for an easy protein boost."},
    {"icon":"🌱","tip":"Sprouting moong dal overnight boosts its protein digestibility and adds Vitamin C — try sprouts chaat as a snack."},
    {"icon":"🔥","tip":"Eating protein at breakfast reduces hunger hormones for the whole day. Start with besan cheela or moong dal chilla."},
    {"icon":"🧠","tip":"Vegetarians should prioritise iron absorption: eat vitamin C-rich foods (lemon, tomato) alongside spinach and dals."},
    {"icon":"💧","tip":"Drinking 500ml water before meals can reduce calorie intake by ~13% — try it 30 min before lunch and dinner."},
    {"icon":"🫘","tip":"Roasted chana (Bengal gram) gives ~10g protein per 50g for under ₹10 — the best protein-per-rupee snack in India."},
    {"icon":"🥜","tip":"Peanut butter is 25% protein by weight. 2 tbsp with an apple = 8g protein in 5 minutes. Perfect pre-workout snack."},
    {"icon":"⏰","tip":"Eating protein within 30 min of exercise maximises muscle protein synthesis — have curd, paneer, or a peanut butter snack."},
    {"icon":"🌿","tip":"Paneer made from 1L milk gives ~180-200g paneer with 32-36g protein. Making it at home is cheaper and fresher."},
    {"icon":"🥗","tip":"Adding chia seeds (2 tbsp) to your morning oats adds 5g protein + 10g fibre without changing the taste."},
    {"icon":"🫙","tip":"Quinoa contains all 9 essential amino acids and has 8g protein per cooked cup — a rare complete plant protein."},
    {"icon":"🌙","tip":"A casein-rich bedtime snack (curd or paneer) releases protein slowly overnight, supporting muscle repair during sleep."},
    {"icon":"🏋️","tip":"For muscle gain, aim for 0.4g protein per kg per meal across 4 meals rather than loading it all at once."},
    {"icon":"💊","tip":"Vitamin B12 is only in animal foods — vegetarians should supplement or consume B12-fortified foods like some cereals and plant milks."},
    {"icon":"🌞","tip":"Sunlight is the best source of Vitamin D. 15-20 min of morning sun on arms and legs gives your daily requirement."},
    {"icon":"🫀","tip":"Legumes (dal, beans, chickpeas) lower LDL cholesterol. Eating them daily is one of the best dietary choices you can make."},
    {"icon":"🧂","tip":"Most Indians consume 2-3x the recommended sodium. Reducing added salt and avoiding processed foods improves blood pressure significantly."},
    {"icon":"🥦","tip":"Broccoli has more Vitamin C than oranges and decent protein for a vegetable. Steam it lightly to preserve nutrients."},
    {"icon":"🫐","tip":"The best time to eat fruit is on an empty stomach — it digests faster and its nutrients absorb more efficiently."},
]

def get_tip_of_day():
    day_of_year = date.today().timetuple().tm_yday
    return DAILY_TIPS[day_of_year % len(DAILY_TIPS)]

# ─── ACHIEVEMENTS SYSTEM ───────────────────────
ALL_ACHIEVEMENTS = [
    # Streak
    {'id':'streak_3',  'cat':'streak',  'icon':'🌱','name':'Sprouting',      'desc':'Maintain a 3-day protein streak',    'target':3},
    {'id':'streak_7',  'cat':'streak',  'icon':'🔥','name':'On Fire',         'desc':'Maintain a 7-day protein streak',    'target':7},
    {'id':'streak_14', 'cat':'streak',  'icon':'⚡','name':'Unstoppable',     'desc':'Maintain a 14-day protein streak',   'target':14},
    {'id':'streak_30', 'cat':'streak',  'icon':'💎','name':'Diamond',         'desc':'Maintain a 30-day protein streak',   'target':30},
    # Logging
    {'id':'log_1',     'cat':'logging', 'icon':'📝','name':'First Log',       'desc':'Log your very first meal',           'target':1},
    {'id':'log_10',    'cat':'logging', 'icon':'📊','name':'Tracking Star',   'desc':'Log 10 total meals',                 'target':10},
    {'id':'log_50',    'cat':'logging', 'icon':'🏅','name':'Dedicated',       'desc':'Log 50 total meals',                 'target':50},
    {'id':'log_100',   'cat':'logging', 'icon':'🌟','name':'Centurion',       'desc':'Log 100 total meals',                'target':100},
    # Protein
    {'id':'pro_hit_1', 'cat':'protein', 'icon':'💪','name':'Protein Day',     'desc':'Hit your protein goal for the first time', 'target':1},
    {'id':'pro_hit_7', 'cat':'protein', 'icon':'🥩','name':'Protein Week',    'desc':'Hit protein goal on 7 different days','target':7},
    {'id':'pro_hit_30','cat':'protein', 'icon':'🏆','name':'Protein Master',  'desc':'Hit protein goal on 30 different days','target':30},
    # Water
    {'id':'water_1',   'cat':'water',   'icon':'💧','name':'First Sip',       'desc':'Log water for the first time',       'target':1},
    {'id':'water_7',   'cat':'water',   'icon':'🌊','name':'Hydrated',        'desc':'Hit 2L water goal for 7 days',       'target':7},
    # Weight
    {'id':'weight_1',  'cat':'weight',  'icon':'⚖️','name':'Weigh In',        'desc':'Log your weight for the first time', 'target':1},
    {'id':'weight_10', 'cat':'weight',  'icon':'📉','name':'Consistent',      'desc':'Log weight 10 times',                'target':10},
    # Custom foods
    {'id':'custom_1',  'cat':'custom',  'icon':'🍳','name':'Chef',            'desc':'Add your first custom food',         'target':1},
    # Mood
    {'id':'mood_7',    'cat':'mood',    'icon':'😊','name':'Mindful',         'desc':'Track your mood for 7 days',         'target':7},
    # Plan
    {'id':'plan_gen',  'cat':'plan',    'icon':'📅','name':'Planner',         'desc':'Generate your first meal plan',      'target':1},
]

def get_achievements(user_id):
    conn = get_db()
    profile   = conn.execute('SELECT daily_protein FROM profiles WHERE user_id=?',(user_id,)).fetchone()
    target    = (profile['daily_protein']*0.8) if profile else 80
    streak    = get_streak_data(user_id)
    # Counts
    total_logs= conn.execute('SELECT COUNT(*) c FROM meal_logs WHERE user_id=?',(user_id,)).fetchone()['c']
    pro_days  = conn.execute('''SELECT COUNT(*) c FROM (
        SELECT log_date FROM meal_logs WHERE user_id=? GROUP BY log_date HAVING SUM(protein)>=?)''',(user_id,target)).fetchone()['c']
    water_days= conn.execute('''SELECT COUNT(*) c FROM (
        SELECT log_date FROM water_logs WHERE user_id=? GROUP BY log_date HAVING SUM(amount_ml)>=2000)''',(user_id,)).fetchone()['c']
    wt_count  = conn.execute('SELECT COUNT(*) c FROM weight_logs WHERE user_id=?',(user_id,)).fetchone()['c']
    cf_count  = conn.execute('SELECT COUNT(*) c FROM custom_foods WHERE user_id=?',(user_id,)).fetchone()['c']
    mood_days = conn.execute('SELECT COUNT(DISTINCT log_date) c FROM mood_logs WHERE user_id=?',(user_id,)).fetchone()['c']
    plan_count= conn.execute('SELECT COUNT(*) c FROM meal_plans WHERE user_id=?',(user_id,)).fetchone()['c']
    water_logged = conn.execute('SELECT COUNT(*) c FROM water_logs WHERE user_id=?',(user_id,)).fetchone()['c']
    conn.close()

    def prog(ach):
        c = ach['cat']
        if c=='streak':  return min(streak['longest'], ach['target']), ach['target']
        if c=='logging': return min(total_logs, ach['target']), ach['target']
        if c=='protein': return min(pro_days, ach['target']), ach['target']
        if c=='water':
            if ach['id']=='water_1': return min(water_logged, 1), 1
            return min(water_days, ach['target']), ach['target']
        if c=='weight':
            if ach['id']=='weight_1': return min(wt_count,1), 1
            return min(wt_count, ach['target']), ach['target']
        if c=='custom':  return min(cf_count, 1), 1
        if c=='mood':    return min(mood_days, ach['target']), ach['target']
        if c=='plan':    return min(plan_count, 1), 1
        return 0, ach['target']

    result = []
    for a in ALL_ACHIEVEMENTS:
        cur, tgt = prog(a)
        result.append({**a, 'current': cur, 'unlocked': cur >= tgt,
                        'pct': int(min(cur/tgt*100, 100))})
    return result

# ─── WATER TRACKER HELPERS ─────────────────────
WATER_GOAL_ML = 2000
def get_water_today(user_id):
    today = date.today().isoformat()
    conn = get_db()
    row = conn.execute('SELECT SUM(amount_ml) s FROM water_logs WHERE user_id=? AND log_date=?',
                       (user_id, today)).fetchone()
    conn.close()
    return int(row['s'] or 0)

# ─── CALENDAR DATA ─────────────────────────────
def get_calendar_data(user_id, year, month):
    import calendar
    conn  = get_db()
    profile = conn.execute('SELECT daily_calories, daily_protein FROM profiles WHERE user_id=?',(user_id,)).fetchone()
    cal_target = profile['daily_calories'] if profile else 2000
    pro_target = profile['daily_protein']  if profile else 80
    # All logs for month
    prefix = f'{year:04d}-{month:02d}'
    rows = conn.execute('''SELECT log_date, SUM(calories) cal, SUM(protein) pro
        FROM meal_logs WHERE user_id=? AND log_date LIKE ? GROUP BY log_date''',
        (user_id, prefix+'%')).fetchall()
    water_rows = conn.execute('''SELECT log_date, SUM(amount_ml) w
        FROM water_logs WHERE user_id=? AND log_date LIKE ? GROUP BY log_date''',
        (user_id, prefix+'%')).fetchall()
    conn.close()
    by_date = {r['log_date']: {'cal': r['cal'] or 0, 'pro': r['pro'] or 0} for r in rows}
    water_by_date = {r['log_date']: r['w'] or 0 for r in water_rows}
    _, days_in_month = calendar.monthrange(year, month)
    result = []
    for d in range(1, days_in_month+1):
        ds = f'{year:04d}-{month:02d}-{d:02d}'
        data = by_date.get(ds, {})
        w = water_by_date.get(ds, 0)
        cal_ok = data.get('cal',0) >= cal_target*0.7
        pro_ok = data.get('pro',0) >= pro_target*0.8
        water_ok = w >= WATER_GOAL_ML
        status = 'none'
        if data:
            if cal_ok and pro_ok: status = 'great'
            elif pro_ok or cal_ok: status = 'good'
            else: status = 'logged'
        result.append({'date':ds,'day':d,'status':status,
                       'cal':int(data.get('cal',0)),'pro':round(data.get('pro',0),1),'water':w,
                       'water_ok':water_ok})
    # week offset
    import calendar as cal_mod
    first_dow = cal_mod.monthrange(year, month)[0]  # 0=Mon
    return result, first_dow, days_in_month

# ─── BMI & BODY STATS ──────────────────────────
def calc_bmi_stats(height_cm, weight_kg, age, gender):
    h = height_cm / 100
    bmi = round(weight_kg / (h*h), 1)
    if   bmi < 18.5: cat = ('Underweight','#2196F3')
    elif bmi < 25.0: cat = ('Normal','#4CAF50')
    elif bmi < 30.0: cat = ('Overweight','#FF9800')
    else:            cat = ('Obese','#F44336')
    # Ideal weight (Devine formula)
    if gender == 'male':
        ideal = 50 + 2.3 * ((height_cm - 152.4) / 2.54)
    else:
        ideal = 45.5 + 2.3 * ((height_cm - 152.4) / 2.54)
    ideal = round(max(ideal, 40), 1)
    to_ideal = round(weight_kg - ideal, 1)
    return {'bmi': bmi, 'category': cat[0], 'color': cat[1],
            'ideal_weight': ideal, 'diff_from_ideal': to_ideal}

# ═══════════════════════════════════════════════
#  ★★★ V3 ROUTES ★★★
# ═══════════════════════════════════════════════

@app.route('/water', methods=['GET','POST'])
def water():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        amount = int(request.form.get('amount', 250))
        conn = get_db()
        conn.execute('INSERT INTO water_logs (user_id, amount_ml, log_date) VALUES (?,?,?)',
                     (session['user_id'], amount, request.form.get('log_date', date.today().isoformat())))
        conn.commit(); conn.close()
        return jsonify({'total': get_water_today(session['user_id']), 'goal': WATER_GOAL_ML})
    # GET
    today = date.today().isoformat()
    conn  = get_db()
    logs  = conn.execute('SELECT * FROM water_logs WHERE user_id=? AND log_date=? ORDER BY log_time DESC',
                         (session['user_id'], today)).fetchall()
    # 7-day history
    days7, water7 = [], []
    for i in range(6,-1,-1):
        d = (date.today()-timedelta(days=i)).isoformat()
        days7.append(d[-5:])
        row = conn.execute('SELECT SUM(amount_ml) s FROM water_logs WHERE user_id=? AND log_date=?',
                           (session['user_id'],d)).fetchone()
        water7.append(int(row['s'] or 0))
    conn.close()
    total_today = sum(l['amount_ml'] for l in logs)
    return render_template('water.html', logs=logs, total_today=total_today,
                           goal=WATER_GOAL_ML, days7=days7, water7=water7, today=today)

@app.route('/api/log-water', methods=['POST'])
def api_log_water():
    if 'user_id' not in session: return jsonify({'error':'unauth'}),401
    data   = request.get_json()
    amount = int((data or {}).get('amount', 250))
    conn   = get_db()
    conn.execute('INSERT INTO water_logs (user_id, amount_ml, log_date) VALUES (?,?,?)',
                 (session['user_id'], amount, date.today().isoformat()))
    conn.commit(); conn.close()
    total = get_water_today(session['user_id'])
    return jsonify({'total': total, 'goal': WATER_GOAL_ML,
                    'pct': min(int(total/WATER_GOAL_ML*100),100)})

@app.route('/api/delete-water/<int:wid>', methods=['POST'])
def delete_water(wid):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    conn.execute('DELETE FROM water_logs WHERE id=? AND user_id=?',(wid, session['user_id']))
    conn.commit(); conn.close()
    return redirect(url_for('water'))

@app.route('/achievements')
def achievements():
    if 'user_id' not in session: return redirect(url_for('login'))
    ach  = get_achievements(session['user_id'])
    unlocked = [a for a in ach if a['unlocked']]
    locked   = [a for a in ach if not a['unlocked']]
    streak   = get_streak_data(session['user_id'])
    return render_template('achievements.html', unlocked=unlocked, locked=locked,
                           total=len(ach), streak=streak)

@app.route('/calendar')
def nutrition_calendar():
    if 'user_id' not in session: return redirect(url_for('login'))
    today = date.today()
    year  = int(request.args.get('year',  today.year))
    month = int(request.args.get('month', today.month))
    # Clamp
    if month < 1:  month = 12; year -= 1
    if month > 12: month = 1;  year += 1
    cal_data, first_dow, days_in = get_calendar_data(session['user_id'], year, month)
    prev_m = month-1 if month>1 else 12
    prev_y = year   if month>1 else year-1
    next_m = month+1 if month<12 else 1
    next_y = year   if month<12 else year+1
    import calendar as cal_mod
    month_name = cal_mod.month_name[month]
    conn = get_db()
    profile = conn.execute('SELECT daily_protein, daily_calories FROM profiles WHERE user_id=?',
                           (session['user_id'],)).fetchone()
    conn.close()
    return render_template('calendar.html', cal_data=cal_data, first_dow=first_dow,
                           year=year, month=month, month_name=month_name,
                           prev_y=prev_y, prev_m=prev_m, next_y=next_y, next_m=next_m,
                           today=today.isoformat(), profile=profile)

@app.route('/my-foods', methods=['GET','POST'])
def my_foods():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        action = request.form.get('action','add')
        if action == 'delete':
            conn = get_db()
            conn.execute('DELETE FROM custom_foods WHERE id=? AND user_id=?',
                         (int(request.form['food_id']), session['user_id']))
            conn.commit(); conn.close()
            flash('Food deleted.','info')
        else:
            conn = get_db()
            conn.execute('''INSERT INTO custom_foods (user_id,name,calories,protein,carbs,fat,serving_size)
                VALUES (?,?,?,?,?,?,?)''',
                (session['user_id'], request.form['name'].strip(),
                 int(request.form['calories']), float(request.form['protein']),
                 float(request.form.get('carbs',0)), float(request.form.get('fat',0)),
                 request.form.get('serving_size','1 serving')))
            conn.commit(); conn.close()
            flash(f'✅ "{request.form["name"]}" added to your food library!','success')
        return redirect(url_for('my_foods'))
    conn  = get_db()
    foods = conn.execute('SELECT * FROM custom_foods WHERE user_id=? ORDER BY created_at DESC',
                         (session['user_id'],)).fetchall()
    conn.close()
    return render_template('my_foods.html', foods=foods)

@app.route('/mood', methods=['GET','POST'])
def mood_tracker():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        conn = get_db()
        conn.execute('INSERT OR REPLACE INTO mood_logs (user_id,mood,energy_level,note,log_date) VALUES (?,?,?,?,?)',
                     (session['user_id'], request.form['mood'],
                      int(request.form.get('energy',3)), request.form.get('note',''),
                      request.form.get('log_date', date.today().isoformat())))
        conn.commit(); conn.close()
        flash('Mood logged! 😊','success')
        return redirect(url_for('mood_tracker'))
    conn  = get_db()
    logs  = conn.execute('SELECT * FROM mood_logs WHERE user_id=? ORDER BY log_date DESC LIMIT 30',
                         (session['user_id'],)).fetchall()
    conn.close()
    today = date.today().isoformat()
    mood_counts = {}
    for l in logs:
        mood_counts[l['mood']] = mood_counts.get(l['mood'], 0) + 1
    return render_template('mood.html', logs=logs, today=today, mood_counts=mood_counts)

@app.route('/api/search-food-all')
def search_food_all():
    """Search both built-in and custom foods"""
    if 'user_id' not in session: return jsonify([])
    q = request.args.get('q','').lower()
    results = [{'name':k,'cal':v['cal'],'pro':v['pro'],'carbs':0,'fat':0,'source':'built-in'}
               for k,v in FOODS.items() if q in k.lower()]
    conn = get_db()
    custom = conn.execute('SELECT * FROM custom_foods WHERE user_id=? AND LOWER(name) LIKE ?',
                          (session['user_id'], f'%{q}%')).fetchall()
    conn.close()
    for c in custom:
        results.append({'name':c['name'],'cal':c['calories'],'pro':c['protein'],
                        'carbs':c['carbs'],'fat':c['fat'],'source':'custom',
                        'serving': c['serving_size']})
    return jsonify(results[:12])

@app.route('/stats')
def body_stats():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    profile = conn.execute('SELECT * FROM profiles WHERE user_id=?',(session['user_id'],)).fetchone()
    if not profile:
        conn.close()
        flash('Complete your profile first.','warning')
        return redirect(url_for('setup_profile'))
    wt_logs = conn.execute('SELECT * FROM weight_logs WHERE user_id=? ORDER BY log_date DESC LIMIT 30',
                           (session['user_id'],)).fetchall()
    conn.close()
    current_weight = wt_logs[0]['weight'] if wt_logs else profile['weight']
    bmi_stats = calc_bmi_stats(profile['height'], current_weight, profile['age'], profile['gender'])
    tip = get_tip_of_day()
    return render_template('body_stats.html', profile=profile, bmi_stats=bmi_stats,
                           current_weight=current_weight, wt_logs=wt_logs, tip=tip)

@app.route('/api/dashboard-water')
def api_dashboard_water():
    if 'user_id' not in session: return jsonify({'total':0,'goal':WATER_GOAL_ML,'pct':0})
    total = get_water_today(session['user_id'])
    return jsonify({'total':total,'goal':WATER_GOAL_ML,'pct':min(int(total/WATER_GOAL_ML*100),100)})


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)

# ═══════════════════════════════════════════════
#  ★★★ V4 NEW FEATURES ★★★
# ═══════════════════════════════════════════════

@app.route('/api/today-summary')
def api_today_summary():
    """Quick API: remaining calories and protein for today"""
    if 'user_id' not in session: return jsonify({}), 401
    conn = get_db()
    profile = conn.execute('SELECT daily_calories, daily_protein FROM profiles WHERE user_id=?',
                           (session['user_id'],)).fetchone()
    today = date.today().isoformat()
    row = conn.execute('SELECT SUM(calories) c, SUM(protein) p FROM meal_logs WHERE user_id=? AND log_date=?',
                       (session['user_id'], today)).fetchone()
    conn.close()
    if not profile: return jsonify({})
    eaten_cal = int(row['c'] or 0)
    eaten_pro = round(float(row['p'] or 0), 1)
    return jsonify({
        'target_cal': profile['daily_calories'], 'eaten_cal': eaten_cal,
        'remaining_cal': profile['daily_calories'] - eaten_cal,
        'target_pro': profile['daily_protein'], 'eaten_pro': eaten_pro,
        'remaining_pro': round(profile['daily_protein'] - eaten_pro, 1),
    })

@app.route('/api/macro-breakdown')
def api_macro_breakdown():
    """Last 7 days macro breakdown for charts"""
    if 'user_id' not in session: return jsonify([]), 401
    conn = get_db()
    days = []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        row = conn.execute(
            'SELECT SUM(calories) c, SUM(protein) p, SUM(carbs) carb, SUM(fat) f FROM meal_logs WHERE user_id=? AND log_date=?',
            (session['user_id'], d)).fetchone()
        days.append({'date': d[-5:], 'cal': int(row['c'] or 0), 'pro': round(float(row['p'] or 0), 1),
                     'carb': round(float(row['carb'] or 0), 1), 'fat': round(float(row['f'] or 0), 1)})
    conn.close()
    return jsonify(days)

@app.route('/api/delete-meal-log/<int:lid>', methods=['POST'])
def api_delete_meal_log(lid):
    """AJAX delete meal log entry"""
    if 'user_id' not in session: return jsonify({'error': 'unauth'}), 401
    conn = get_db()
    conn.execute('DELETE FROM meal_logs WHERE id=? AND user_id=?', (lid, session['user_id']))
    conn.commit()
    today = date.today().isoformat()
    row = conn.execute('SELECT SUM(calories) c, SUM(protein) p FROM meal_logs WHERE user_id=? AND log_date=?',
                       (session['user_id'], today)).fetchone()
    conn.close()
    return jsonify({'cal': int(row['c'] or 0), 'pro': round(float(row['p'] or 0), 1)})