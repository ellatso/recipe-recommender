# 🍳 食在好料 — 食材搭配與料理推薦系統

> 資料庫管理期末專題

## 系統簡介

「食在好料」是一套以食材為核心的料理推薦系統。使用者可以輸入手邊現有的食材，系統透過多對多關聯查詢，自動計算食材匹配度，推薦最適合的料理。系統涵蓋 421 道中外食譜、1,648 種食材，支援 11 種菜系分類。

## 核心功能

1. **會員管理** — 註冊 / 登入 / 個人偏好設定（不吃的食材）
2. **食材配對推薦**（主打功能）— 輸入食材，推薦匹配度最高的料理
3. **食譜瀏覽與收藏** — 依分類/菜系/難度瀏覽、收藏喜歡的食譜
4. **烹飪紀錄與評論** — 記錄做過的菜、打星評分、留下評論
5. **🎲 今晚吃什麼** — 隨機推薦一道菜，支援條件篩選

## 技術架構

- **後端**: Python Flask
- **資料庫**: SQLite (demo) / MySQL 8.0 (正式環境)
- **前端**: HTML + CSS + JavaScript (Jinja2 模板)
- **資料來源**: HowToCook (GitHub, Unlicense)、手動建立台灣菜色

## 環境設定與啟動

### 1. 安裝依賴

```bash
pip install flask openpyxl werkzeug pandas
```

### 2. 啟動應用程式

```bash
cd FinalProject
python app.py
```

系統會自動偵測是否已有資料庫，若無則自動從 `recipe_database_cleaned.xlsx` 匯入資料。

### 3. 開啟瀏覽器

前往 http://localhost:5000

### 測試帳號

| 帳號  | 密碼      |
|-------|----------|
| demo  | demo123  |
| alice | alice123 |
| bob   | bob123   |

## 資料庫結構

共 8 張資料表：

| 表名 | 說明 | 關鍵欄位 |
|------|------|---------|
| categories | 食譜分類 | category_id (PK), category_name |
| ingredients | 食材 | ingredient_id (PK), ingredient_name, category |
| recipes | 食譜 | recipe_id (PK), category_id (FK), cuisine, difficulty |
| recipe_ingredients | 食譜-食材關聯 (M:N) | recipe_id (FK), ingredient_id (FK) |
| users | 會員 | user_id (PK), username, email |
| favorites | 收藏 | user_id (FK), recipe_id (FK) |
| cook_history | 烹飪紀錄 | user_id (FK), recipe_id (FK), rating |
| reviews | 評論 | user_id (FK), recipe_id (FK), stars, content |

## 核心 SQL 查詢

### 食材匹配推薦

```sql
SELECT r.recipe_id, r.recipe_name,
       COUNT(ri.ingredient_id) AS matched,
       t.total_required,
       ROUND(COUNT(ri.ingredient_id) * 100.0 / t.total_required) AS match_pct
FROM recipes r
JOIN recipe_ingredients ri ON r.recipe_id = ri.recipe_id
JOIN (SELECT recipe_id, COUNT(*) AS total_required
      FROM recipe_ingredients WHERE is_optional = 0
      GROUP BY recipe_id) t ON r.recipe_id = t.recipe_id
WHERE ri.ingredient_id IN (使用者選擇的食材ID)
GROUP BY r.recipe_id
HAVING match_pct >= 20
ORDER BY match_pct DESC
LIMIT 20;
```

## 檔案結構

```
FinalProject/
├── app.py                          # Flask 主程式（所有路由）
├── seed_data.py                    # 資料庫建置與匯入腳本
├── database_setup.sql              # MySQL DDL + 索引 + 範例查詢
├── recipe_database_cleaned.xlsx    # 清洗後的種子資料
├── recipe.db                       # SQLite 資料庫（自動生成）
├── README.md                       # 說明文件
└── templates/
    ├── base.html                   # 基底模板（導覽列、CSS）
    ├── index.html                  # 首頁
    ├── login.html                  # 登入頁
    ├── register.html               # 註冊頁
    ├── browse.html                 # 食譜瀏覽（篩選+分頁）
    ├── recipe_detail.html          # 食譜詳情（食材+步驟+評論）
    ├── recommend.html              # 食材配對推薦
    ├── dice.html                   # 🎲 今晚吃什麼
    ├── favorites.html              # 我的收藏
    ├── history.html                # 烹飪紀錄
    └── profile.html                # 個人資料
```
