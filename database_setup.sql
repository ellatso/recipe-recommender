-- ============================================================
-- 食材搭配與料理推薦系統 - 資料庫建置腳本
-- Database: recipe_recommender
-- 適用: MySQL 8.0+
-- ============================================================

DROP DATABASE IF EXISTS recipe_recommender;
CREATE DATABASE recipe_recommender
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
USE recipe_recommender;

-- -----------------------------------------------------------
-- 1. 分類表 (Categories)
-- -----------------------------------------------------------
CREATE TABLE categories (
    category_id   INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- -----------------------------------------------------------
-- 2. 食材表 (Ingredients)
-- -----------------------------------------------------------
CREATE TABLE ingredients (
    ingredient_id   INT AUTO_INCREMENT PRIMARY KEY,
    ingredient_name VARCHAR(100) NOT NULL UNIQUE,
    category        VARCHAR(30) DEFAULT '其他'
        COMMENT '肉類/海鮮/蔬菜/調味料/穀物澱粉/蛋奶/水果/乾貨香料/油脂/飲品原料/其他'
) ENGINE=InnoDB;

-- -----------------------------------------------------------
-- 3. 食譜表 (Recipes)
-- -----------------------------------------------------------
CREATE TABLE recipes (
    recipe_id       INT AUTO_INCREMENT PRIMARY KEY,
    recipe_name     VARCHAR(120) NOT NULL,
    category_id     INT,
    cuisine         VARCHAR(30)  DEFAULT '中式家常',
    difficulty      TINYINT      DEFAULT 3 CHECK (difficulty BETWEEN 1 AND 5),
    cooking_time_min INT         DEFAULT 30,
    servings        TINYINT      DEFAULT 2,
    calories        INT          DEFAULT NULL,
    steps_summary   TEXT,
    image_url       VARCHAR(255) DEFAULT NULL,
    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(category_id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- -----------------------------------------------------------
-- 4. 食譜-食材 關聯表 (多對多核心)
-- -----------------------------------------------------------
CREATE TABLE recipe_ingredients (
    recipe_id     INT NOT NULL,
    ingredient_id INT NOT NULL,
    is_optional   BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (recipe_id, ingredient_id),
    FOREIGN KEY (recipe_id)     REFERENCES recipes(recipe_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (ingredient_id) REFERENCES ingredients(ingredient_id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- -----------------------------------------------------------
-- 5. 會員表 (Users)
-- -----------------------------------------------------------
CREATE TABLE users (
    user_id        INT AUTO_INCREMENT PRIMARY KEY,
    username       VARCHAR(50)  NOT NULL UNIQUE,
    email          VARCHAR(100) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    display_name   VARCHAR(50),
    avatar_url     VARCHAR(255) DEFAULT NULL,
    excluded_ingredients TEXT DEFAULT NULL
        COMMENT '不吃的食材，以分號分隔',
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- -----------------------------------------------------------
-- 6. 收藏表 (Favorites)
-- -----------------------------------------------------------
CREATE TABLE favorites (
    user_id    INT NOT NULL,
    recipe_id  INT NOT NULL,
    saved_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, recipe_id),
    FOREIGN KEY (user_id)   REFERENCES users(user_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- -----------------------------------------------------------
-- 7. 烹飪紀錄表 (Cook History)
-- -----------------------------------------------------------
CREATE TABLE cook_history (
    history_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    recipe_id  INT NOT NULL,
    cooked_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    rating     TINYINT DEFAULT NULL CHECK (rating BETWEEN 1 AND 5),
    FOREIGN KEY (user_id)   REFERENCES users(user_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- -----------------------------------------------------------
-- 8. 評論表 (Reviews)
-- -----------------------------------------------------------
CREATE TABLE reviews (
    review_id  INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    recipe_id  INT NOT NULL,
    content    TEXT NOT NULL,
    stars      TINYINT NOT NULL CHECK (stars BETWEEN 1 AND 5),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)   REFERENCES users(user_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (recipe_id) REFERENCES recipes(recipe_id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- -----------------------------------------------------------
-- 建立索引 (加速查詢)
-- -----------------------------------------------------------
CREATE INDEX idx_recipes_category  ON recipes(category_id);
CREATE INDEX idx_recipes_cuisine   ON recipes(cuisine);
CREATE INDEX idx_recipes_difficulty ON recipes(difficulty);
CREATE INDEX idx_ri_ingredient     ON recipe_ingredients(ingredient_id);
CREATE INDEX idx_cook_user         ON cook_history(user_id);
CREATE INDEX idx_reviews_recipe    ON reviews(recipe_id);

-- -----------------------------------------------------------
-- 預設測試帳號
-- -----------------------------------------------------------
INSERT INTO users (username, email, password_hash, display_name) VALUES
('demo',  'demo@example.com',  'pbkdf2:sha256:demo123',  '示範帳號'),
('alice', 'alice@example.com', 'pbkdf2:sha256:alice123', 'Alice'),
('bob',   'bob@example.com',   'pbkdf2:sha256:bob123',   'Bob');

-- ============================================================
-- 🎲 今晚吃什麼 - 隨機推薦 SQL 範例
-- ============================================================
-- SELECT r.recipe_id, r.recipe_name, r.cuisine, r.difficulty,
--        c.category_name, r.cooking_time_min
-- FROM recipes r
-- LEFT JOIN categories c ON r.category_id = c.category_id
-- WHERE r.difficulty <= 3
--   AND r.cooking_time_min <= 45
-- ORDER BY RAND()
-- LIMIT 1;

-- ============================================================
-- 🔍 食材匹配推薦 SQL 範例 (核心查詢)
-- ============================================================
-- SET @user_ingredients = '雞蛋,醬油,蔥,蒜,鹽';
--
-- SELECT r.recipe_id, r.recipe_name, r.cuisine, r.difficulty,
--        COUNT(ri.ingredient_id)  AS matched_count,
--        t.total_required,
--        ROUND(COUNT(ri.ingredient_id) * 100.0 / t.total_required) AS match_pct
-- FROM recipes r
-- JOIN recipe_ingredients ri ON r.recipe_id = ri.recipe_id
-- JOIN ingredients i ON ri.ingredient_id = i.ingredient_id
-- JOIN (
--     SELECT recipe_id, COUNT(*) AS total_required
--     FROM recipe_ingredients
--     WHERE is_optional = FALSE
--     GROUP BY recipe_id
-- ) t ON r.recipe_id = t.recipe_id
-- WHERE i.ingredient_name IN ('雞蛋','醬油','蔥','蒜','鹽')
--   AND ri.is_optional = FALSE
-- GROUP BY r.recipe_id
-- HAVING match_pct >= 30
-- ORDER BY match_pct DESC, matched_count DESC
-- LIMIT 20;
