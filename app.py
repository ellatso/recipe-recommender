"""
app.py - 食材搭配與料理推薦系統
Flask Web Application
"""
import os
import sqlite3
import random
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, g)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.urandom(24)
DB_PATH = os.path.join(os.path.dirname(__file__), 'recipe.db')


# ============================================================
# Database helpers
# ============================================================
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db: db.close()

def query_db(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv


# ============================================================
# Auth decorator
# ============================================================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('請先登入', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ============================================================
# ROUTES: Auth (會員管理)
# ============================================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        display_name = request.form.get('display_name', username).strip()

        if not username or not email or not password:
            flash('所有欄位都必須填寫', 'danger')
            return render_template('register.html')

        db = get_db()
        if query_db("SELECT 1 FROM users WHERE username=? OR email=?", (username, email), one=True):
            flash('使用者名稱或信箱已被使用', 'danger')
            return render_template('register.html')

        db.execute(
            "INSERT INTO users (username, email, password_hash, display_name) VALUES (?,?,?,?)",
            (username, email, generate_password_hash(password), display_name)
        )
        db.commit()
        flash('註冊成功！請登入', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        user = query_db("SELECT * FROM users WHERE username=?", (username,), one=True)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['display_name'] = user['display_name'] or user['username']
            flash(f'歡迎回來，{session["display_name"]}！', 'success')
            return redirect(url_for('index'))
        flash('帳號或密碼錯誤', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('已登出', 'info')
    return redirect(url_for('index'))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    db = get_db()
    user = query_db("SELECT * FROM users WHERE user_id=?", (session['user_id'],), one=True)

    if request.method == 'POST':
        display_name = request.form.get('display_name', '').strip()
        excluded = request.form.get('excluded_ingredients', '').strip()
        new_password = request.form.get('new_password', '').strip()

        if display_name:
            db.execute("UPDATE users SET display_name=?, excluded_ingredients=? WHERE user_id=?",
                       (display_name, excluded, session['user_id']))
            session['display_name'] = display_name

        if new_password:
            db.execute("UPDATE users SET password_hash=? WHERE user_id=?",
                       (generate_password_hash(new_password), session['user_id']))

        db.commit()
        flash('個人資料已更新', 'success')
        return redirect(url_for('profile'))

    # Get stats
    fav_count = query_db("SELECT COUNT(*) as c FROM favorites WHERE user_id=?",
                         (session['user_id'],), one=True)['c']
    cook_count = query_db("SELECT COUNT(*) as c FROM cook_history WHERE user_id=?",
                          (session['user_id'],), one=True)['c']
    review_count = query_db("SELECT COUNT(*) as c FROM reviews WHERE user_id=?",
                            (session['user_id'],), one=True)['c']

    return render_template('profile.html', user=user,
                           fav_count=fav_count, cook_count=cook_count, review_count=review_count)


# ============================================================
# ROUTES: Home & Browse (食譜瀏覽)
# ============================================================
@app.route('/')
def index():
    categories = query_db("SELECT * FROM categories ORDER BY category_name")
    popular = query_db("""
        SELECT r.*, c.category_name,
               COALESCE(AVG(rv.stars), 0) AS avg_rating,
               COUNT(DISTINCT rv.review_id) AS review_count
        FROM recipes r
        LEFT JOIN categories c ON r.category_id = c.category_id
        LEFT JOIN reviews rv ON r.recipe_id = rv.recipe_id
        GROUP BY r.recipe_id
        ORDER BY avg_rating DESC, review_count DESC
        LIMIT 8
    """)
    total_recipes = query_db("SELECT COUNT(*) as c FROM recipes", one=True)['c']
    total_ingredients = query_db("SELECT COUNT(*) as c FROM ingredients", one=True)['c']

    # Get all distinct cuisines
    cuisines = query_db("SELECT DISTINCT cuisine FROM recipes ORDER BY cuisine")

    return render_template('index.html', categories=categories, popular=popular,
                           total_recipes=total_recipes, total_ingredients=total_ingredients,
                           cuisines=cuisines)


@app.route('/browse')
def browse():
    page = request.args.get('page', 1, type=int)
    per_page = 12
    category = request.args.get('category', '')
    cuisine = request.args.get('cuisine', '')
    difficulty = request.args.get('difficulty', 0, type=int)
    search = request.args.get('q', '').strip()
    sort = request.args.get('sort', 'name')

    where_clauses = []
    params = []

    if category:
        where_clauses.append("c.category_name = ?")
        params.append(category)
    if cuisine:
        where_clauses.append("r.cuisine = ?")
        params.append(cuisine)
    if difficulty:
        where_clauses.append("r.difficulty = ?")
        params.append(difficulty)
    if search:
        where_clauses.append("(r.recipe_name LIKE ? OR r.cuisine LIKE ?)")
        params.extend([f'%{search}%', f'%{search}%'])

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    order_map = {
        'name': 'r.recipe_name',
        'time': 'r.cooking_time_min',
        'difficulty': 'r.difficulty',
        'calories': 'r.calories',
    }
    order_sql = order_map.get(sort, 'r.recipe_name')

    total = query_db(f"""
        SELECT COUNT(*) as c FROM recipes r
        LEFT JOIN categories c ON r.category_id = c.category_id
        WHERE {where_sql}
    """, params, one=True)['c']

    recipes = query_db(f"""
        SELECT r.*, c.category_name FROM recipes r
        LEFT JOIN categories c ON r.category_id = c.category_id
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
    """, params + [per_page, (page - 1) * per_page])

    categories = query_db("SELECT * FROM categories ORDER BY category_name")
    cuisines = query_db("SELECT DISTINCT cuisine FROM recipes ORDER BY cuisine")
    total_pages = (total + per_page - 1) // per_page

    return render_template('browse.html', recipes=recipes, categories=categories,
                           cuisines=cuisines, page=page, total_pages=total_pages,
                           total=total, category=category, cuisine=cuisine,
                           difficulty=difficulty, search=search, sort=sort)


@app.route('/recipe/<int:recipe_id>')
def recipe_detail(recipe_id):
    recipe = query_db("""
        SELECT r.*, c.category_name FROM recipes r
        LEFT JOIN categories c ON r.category_id = c.category_id
        WHERE r.recipe_id = ?
    """, (recipe_id,), one=True)

    if not recipe:
        flash('找不到這道食譜', 'warning')
        return redirect(url_for('browse'))

    ingredients = query_db("""
        SELECT i.*, ri.is_optional FROM recipe_ingredients ri
        JOIN ingredients i ON ri.ingredient_id = i.ingredient_id
        WHERE ri.recipe_id = ?
        ORDER BY ri.is_optional, i.ingredient_name
    """, (recipe_id,))

    reviews = query_db("""
        SELECT rv.*, u.display_name, u.username FROM reviews rv
        JOIN users u ON rv.user_id = u.user_id
        WHERE rv.recipe_id = ?
        ORDER BY rv.created_at DESC
    """, (recipe_id,))

    avg_rating = query_db(
        "SELECT COALESCE(AVG(stars),0) as avg FROM reviews WHERE recipe_id=?",
        (recipe_id,), one=True)['avg']

    is_favorited = False
    if 'user_id' in session:
        is_favorited = query_db(
            "SELECT 1 FROM favorites WHERE user_id=? AND recipe_id=?",
            (session['user_id'], recipe_id), one=True) is not None

    return render_template('recipe_detail.html', recipe=recipe, ingredients=ingredients,
                           reviews=reviews, avg_rating=avg_rating, is_favorited=is_favorited)


# ============================================================
# ROUTES: 食材匹配推薦 (核心功能)
# ============================================================
@app.route('/recommend', methods=['GET', 'POST'])
def recommend():
    results = None
    selected = []
    all_ingredients = query_db("""
        SELECT DISTINCT i.ingredient_id, i.ingredient_name, i.category
        FROM ingredients i
        JOIN recipe_ingredients ri ON i.ingredient_id = ri.ingredient_id
        ORDER BY i.category, i.ingredient_name
    """)

    # Group by category
    ing_by_cat = {}
    for ing in all_ingredients:
        cat = ing['category'] or '其他'
        if cat not in ing_by_cat:
            ing_by_cat[cat] = []
        ing_by_cat[cat].append(ing)

    if request.method == 'POST':
        selected_ids = request.form.getlist('ingredients')
        selected_names = request.form.get('ingredient_text', '').strip()

        # Combine checkbox + text input
        ids = [int(x) for x in selected_ids if x.isdigit()]

        if selected_names:
            for name in selected_names.replace('，', ',').replace('、', ',').replace(';', ',').split(','):
                name = name.strip()
                if name:
                    ing = query_db("SELECT ingredient_id FROM ingredients WHERE ingredient_name LIKE ?",
                                   (f'%{name}%',), one=True)
                    if ing and ing['ingredient_id'] not in ids:
                        ids.append(ing['ingredient_id'])

        if ids:
            placeholders = ','.join('?' * len(ids))
            results = query_db(f"""
                SELECT r.recipe_id, r.recipe_name, r.cuisine, r.difficulty,
                       r.cooking_time_min, r.calories, c.category_name,
                       COUNT(ri.ingredient_id) AS matched,
                       t.total_required,
                       ROUND(COUNT(ri.ingredient_id) * 100.0 / t.total_required) AS match_pct
                FROM recipes r
                JOIN recipe_ingredients ri ON r.recipe_id = ri.recipe_id
                JOIN categories c ON r.category_id = c.category_id
                JOIN (
                    SELECT recipe_id, COUNT(*) AS total_required
                    FROM recipe_ingredients WHERE is_optional = 0
                    GROUP BY recipe_id
                ) t ON r.recipe_id = t.recipe_id
                WHERE ri.ingredient_id IN ({placeholders})
                  AND ri.is_optional = 0
                GROUP BY r.recipe_id
                HAVING match_pct >= 20
                ORDER BY match_pct DESC, matched DESC
                LIMIT 30
            """, ids)

            selected = query_db(f"SELECT * FROM ingredients WHERE ingredient_id IN ({placeholders})", ids)

    return render_template('recommend.html', results=results, selected=selected,
                           ing_by_cat=ing_by_cat)


# ============================================================
# ROUTES: 🎲 今晚吃什麼？
# ============================================================
@app.route('/random-pick')
def random_pick():
    max_diff = request.args.get('max_difficulty', 5, type=int)
    max_time = request.args.get('max_time', 999, type=int)
    cuisine = request.args.get('cuisine', '')
    category = request.args.get('category', '')

    where_clauses = ["r.difficulty <= ?", "r.cooking_time_min <= ?"]
    params = [max_diff, max_time]

    if cuisine:
        where_clauses.append("r.cuisine = ?")
        params.append(cuisine)
    if category:
        where_clauses.append("c.category_name = ?")
        params.append(category)

    where_sql = " AND ".join(where_clauses)

    candidates = query_db(f"""
        SELECT r.*, c.category_name FROM recipes r
        LEFT JOIN categories c ON r.category_id = c.category_id
        WHERE {where_sql}
    """, params)

    if not candidates:
        return jsonify({'error': '沒有符合條件的食譜，請放寬條件再試'}), 404

    pick = random.choice(candidates)
    ingredients = query_db("""
        SELECT i.ingredient_name FROM recipe_ingredients ri
        JOIN ingredients i ON ri.ingredient_id = i.ingredient_id
        WHERE ri.recipe_id = ?
    """, (pick['recipe_id'],))

    return jsonify({
        'recipe_id': pick['recipe_id'],
        'recipe_name': pick['recipe_name'],
        'cuisine': pick['cuisine'],
        'category': pick['category_name'],
        'difficulty': pick['difficulty'],
        'cooking_time_min': pick['cooking_time_min'],
        'calories': pick['calories'],
        'servings': pick['servings'],
        'ingredients': [i['ingredient_name'] for i in ingredients],
        'steps_summary': pick['steps_summary'],
    })

@app.route('/dice')
def dice_page():
    categories = query_db("SELECT * FROM categories ORDER BY category_name")
    cuisines = query_db("SELECT DISTINCT cuisine FROM recipes ORDER BY cuisine")
    return render_template('dice.html', categories=categories, cuisines=cuisines)


# ============================================================
# ROUTES: 收藏 & 烹飪紀錄
# ============================================================
@app.route('/toggle-favorite/<int:recipe_id>', methods=['POST'])
@login_required
def toggle_favorite(recipe_id):
    db = get_db()
    existing = query_db("SELECT 1 FROM favorites WHERE user_id=? AND recipe_id=?",
                        (session['user_id'], recipe_id), one=True)
    if existing:
        db.execute("DELETE FROM favorites WHERE user_id=? AND recipe_id=?",
                   (session['user_id'], recipe_id))
        status = 'removed'
    else:
        db.execute("INSERT INTO favorites (user_id, recipe_id) VALUES (?,?)",
                   (session['user_id'], recipe_id))
        status = 'added'
    db.commit()
    return jsonify({'status': status})


@app.route('/my-favorites')
@login_required
def my_favorites():
    recipes = query_db("""
        SELECT r.*, c.category_name, f.saved_at FROM favorites f
        JOIN recipes r ON f.recipe_id = r.recipe_id
        LEFT JOIN categories c ON r.category_id = c.category_id
        WHERE f.user_id = ?
        ORDER BY f.saved_at DESC
    """, (session['user_id'],))
    return render_template('favorites.html', recipes=recipes)


@app.route('/log-cook/<int:recipe_id>', methods=['POST'])
@login_required
def log_cook(recipe_id):
    rating = request.form.get('rating', type=int)
    db = get_db()
    db.execute("INSERT INTO cook_history (user_id, recipe_id, rating) VALUES (?,?,?)",
               (session['user_id'], recipe_id, rating))
    db.commit()
    flash('已記錄烹飪紀錄！', 'success')
    return redirect(url_for('recipe_detail', recipe_id=recipe_id))


@app.route('/my-history')
@login_required
def my_history():
    records = query_db("""
        SELECT ch.*, r.recipe_name, r.cuisine, c.category_name
        FROM cook_history ch
        JOIN recipes r ON ch.recipe_id = r.recipe_id
        LEFT JOIN categories c ON r.category_id = c.category_id
        WHERE ch.user_id = ?
        ORDER BY ch.cooked_at DESC
    """, (session['user_id'],))
    return render_template('history.html', records=records)


# ============================================================
# ROUTES: 評論
# ============================================================
@app.route('/add-review/<int:recipe_id>', methods=['POST'])
@login_required
def add_review(recipe_id):
    content = request.form.get('content', '').strip()
    stars = request.form.get('stars', 5, type=int)

    if not content:
        flash('評論內容不能為空', 'warning')
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))

    stars = max(1, min(5, stars))
    db = get_db()
    db.execute("INSERT INTO reviews (user_id, recipe_id, content, stars) VALUES (?,?,?,?)",
               (session['user_id'], recipe_id, content, stars))
    db.commit()
    flash('評論已送出！', 'success')
    return redirect(url_for('recipe_detail', recipe_id=recipe_id))


# ============================================================
# ROUTES: API endpoints for AJAX
# ============================================================
@app.route('/api/search-ingredients')
def api_search_ingredients():
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify([])

    results = query_db("""
        SELECT DISTINCT i.ingredient_id, i.ingredient_name, i.category
        FROM ingredients i
        JOIN recipe_ingredients ri ON i.ingredient_id = ri.ingredient_id
        WHERE i.ingredient_name LIKE ?
        ORDER BY i.ingredient_name
        LIMIT 20
    """, (f'%{q}%',))
    return jsonify([dict(r) for r in results])


@app.route('/api/stats')
def api_stats():
    stats = {
        'total_recipes': query_db("SELECT COUNT(*) c FROM recipes", one=True)['c'],
        'total_ingredients': query_db("SELECT COUNT(*) c FROM ingredients", one=True)['c'],
        'total_users': query_db("SELECT COUNT(*) c FROM users", one=True)['c'],
        'total_reviews': query_db("SELECT COUNT(*) c FROM reviews", one=True)['c'],
        'cuisines': [r['cuisine'] for r in query_db("SELECT DISTINCT cuisine FROM recipes")],
        'categories': [dict(r) for r in query_db(
            "SELECT c.category_name, COUNT(r.recipe_id) as cnt FROM categories c LEFT JOIN recipes r ON c.category_id=r.category_id GROUP BY c.category_id ORDER BY cnt DESC"
        )],
    }
    return jsonify(stats)


# ============================================================
# Initialize & Run
# ============================================================
def init_app():
    """Auto-seed if DB doesn't exist."""
    if not os.path.exists(DB_PATH):
        excel_path = os.path.join(os.path.dirname(__file__), 'recipe_database_cleaned.xlsx')
        if os.path.exists(excel_path):
            from seed_data import seed_from_excel
            seed_from_excel(excel_path)
        else:
            from seed_data import init_db
            init_db()
            print("Warning: No Excel file found. Database created with empty tables.")

init_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
