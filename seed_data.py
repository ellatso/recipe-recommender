"""
seed_data.py - 從 Excel 匯入食譜資料到 SQLite
用於本地 demo；正式環境改用 database_setup.sql 建 MySQL
"""
import sqlite3
import os
import re

DB_PATH = os.path.join(os.path.dirname(__file__), 'recipe.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS categories (
        category_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        category_name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE IF NOT EXISTS ingredients (
        ingredient_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        ingredient_name TEXT NOT NULL UNIQUE,
        category        TEXT DEFAULT '其他'
    );
    CREATE TABLE IF NOT EXISTS recipes (
        recipe_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_name      TEXT NOT NULL,
        category_id      INTEGER,
        cuisine          TEXT DEFAULT '中式家常',
        difficulty       INTEGER DEFAULT 3,
        cooking_time_min INTEGER DEFAULT 30,
        servings         INTEGER DEFAULT 2,
        calories         INTEGER,
        steps_summary    TEXT,
        image_url        TEXT,
        created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (category_id) REFERENCES categories(category_id)
    );
    CREATE TABLE IF NOT EXISTS recipe_ingredients (
        recipe_id     INTEGER NOT NULL,
        ingredient_id INTEGER NOT NULL,
        is_optional   INTEGER DEFAULT 0,
        PRIMARY KEY (recipe_id, ingredient_id),
        FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id) ON DELETE CASCADE,
        FOREIGN KEY (ingredient_id) REFERENCES ingredients(ingredient_id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS users (
        user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT NOT NULL UNIQUE,
        email         TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        display_name  TEXT,
        excluded_ingredients TEXT,
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS favorites (
        user_id   INTEGER NOT NULL,
        recipe_id INTEGER NOT NULL,
        saved_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, recipe_id),
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
        FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS cook_history (
        history_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        recipe_id  INTEGER NOT NULL,
        cooked_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        rating     INTEGER,
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
        FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS reviews (
        review_id  INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        recipe_id  INTEGER NOT NULL,
        content    TEXT NOT NULL,
        stars      INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
        FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id) ON DELETE CASCADE
    );
    """)

    # Create indexes
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_recipes_cat ON recipes(category_id)",
        "CREATE INDEX IF NOT EXISTS idx_recipes_cuisine ON recipes(cuisine)",
        "CREATE INDEX IF NOT EXISTS idx_ri_ing ON recipe_ingredients(ingredient_id)",
        "CREATE INDEX IF NOT EXISTS idx_cook_user ON cook_history(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_reviews_recipe ON reviews(recipe_id)",
    ]:
        c.execute(idx_sql)

    conn.commit()
    return conn


def seed_from_excel(excel_path):
    """Import data from cleaned Excel file."""
    import pandas as pd

    conn = init_db()
    c = conn.cursor()

    # Check if already seeded
    c.execute("SELECT COUNT(*) FROM recipes")
    if c.fetchone()[0] > 0:
        print("Database already seeded, skipping.")
        conn.close()
        return

    print("Seeding database from Excel...")

    # 1. Load sheets
    recipes_df = pd.read_excel(excel_path, sheet_name='recipes')
    ingredients_df = pd.read_excel(excel_path, sheet_name='ingredients')
    ri_df = pd.read_excel(excel_path, sheet_name='recipe_ingredients')

    # 2. Insert categories
    categories = sorted(recipes_df['category'].dropna().unique())
    cat_map = {}
    for cat in categories:
        c.execute("INSERT OR IGNORE INTO categories (category_name) VALUES (?)", (cat,))
        c.execute("SELECT category_id FROM categories WHERE category_name=?", (cat,))
        cat_map[cat] = c.fetchone()[0]

    # 3. Insert ingredients
    ing_map = {}
    for _, row in ingredients_df.iterrows():
        name = str(row['ingredient_name']).strip()
        cat = str(row['category']) if pd.notna(row['category']) else '其他'
        c.execute("INSERT OR IGNORE INTO ingredients (ingredient_name, category) VALUES (?,?)",
                  (name, cat))
        c.execute("SELECT ingredient_id FROM ingredients WHERE ingredient_name=?", (name,))
        result = c.fetchone()
        if result:
            ing_map[name] = result[0]

    # 4. Insert recipes
    recipe_id_map = {}
    for _, row in recipes_df.iterrows():
        old_id = int(row['recipe_id'])
        cat_id = cat_map.get(row['category'])
        c.execute("""
            INSERT INTO recipes (recipe_name, category_id, cuisine, difficulty,
                                 cooking_time_min, servings, calories, steps_summary)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            row['recipe_name'],
            cat_id,
            row['cuisine'] if pd.notna(row['cuisine']) else '中式家常',
            int(row['difficulty']) if pd.notna(row['difficulty']) else 3,
            int(row['cooking_time_min']) if pd.notna(row['cooking_time_min']) else 30,
            int(row['servings']) if pd.notna(row['servings']) else 2,
            int(row['calories']) if pd.notna(row['calories']) else None,
            str(row['steps_summary'])[:1000] if pd.notna(row['steps_summary']) else '',
        ))
        recipe_id_map[old_id] = c.lastrowid

    # 5. Insert recipe_ingredients relations
    for _, row in ri_df.iterrows():
        old_rid = int(row['recipe_id'])
        new_rid = recipe_id_map.get(old_rid)
        ing_name = str(row['ingredient_name']).strip()
        ing_id = ing_map.get(ing_name)

        if not ing_id:
            c.execute("INSERT OR IGNORE INTO ingredients (ingredient_name) VALUES (?)", (ing_name,))
            c.execute("SELECT ingredient_id FROM ingredients WHERE ingredient_name=?", (ing_name,))
            result = c.fetchone()
            if result:
                ing_id = result[0]
                ing_map[ing_name] = ing_id

        if new_rid and ing_id:
            c.execute("INSERT OR IGNORE INTO recipe_ingredients (recipe_id, ingredient_id, is_optional) VALUES (?,?,?)",
                      (new_rid, ing_id, 0))

    # 6. Insert demo users
    from werkzeug.security import generate_password_hash
    demo_users = [
        ('demo', 'demo@example.com', 'demo123', '示範帳號'),
        ('alice', 'alice@example.com', 'alice123', 'Alice'),
        ('bob', 'bob@example.com', 'bob123', 'Bob'),
    ]
    for uname, email, pwd, dname in demo_users:
        c.execute("INSERT OR IGNORE INTO users (username, email, password_hash, display_name) VALUES (?,?,?,?)",
                  (uname, email, generate_password_hash(pwd), dname))

    # 7. Add some sample reviews
    sample_reviews = [
        (1, 1, '超級好吃！第一次做就成功了', 5),
        (2, 1, '步驟清楚，推薦新手', 4),
        (1, 5, '味道很棒，家人都很喜歡', 5),
        (3, 10, '簡單又快速', 4),
    ]
    for uid, rid, content, stars in sample_reviews:
        actual_rid = recipe_id_map.get(rid, rid)
        c.execute("INSERT OR IGNORE INTO reviews (user_id, recipe_id, content, stars) VALUES (?,?,?,?)",
                  (uid, actual_rid, content, stars))

    conn.commit()
    c.execute("SELECT COUNT(*) FROM recipes")
    print(f"  Recipes: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM ingredients")
    print(f"  Ingredients: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM recipe_ingredients")
    print(f"  Relations: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM users")
    print(f"  Users: {c.fetchone()[0]}")
    print("Seeding complete!")
    conn.close()


if __name__ == '__main__':
    seed_from_excel('recipe_database_cleaned.xlsx')
