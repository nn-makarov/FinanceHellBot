import sqlite3
from datetime import datetime

class Database:
    def __init__(self, db_name='finance.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        # Таблица категорий (основная)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                emoji TEXT DEFAULT '➕',
                is_deleted INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, name)
            )
        ''')
        
        # Таблица расходов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES user_categories (id)
            )
        ''')
        
        # Добавляем стандартные категории при первом запуске для нового пользователя
        default_categories = [
            ('Еда', '🍕'),
            ('Транспорт', '🚗'),
            ('Одежда', '👕'),
            ('Развлечения', '🎬')
        ]
        self.conn.commit()
    
    # --- Методы для категорий ---
    def init_user_categories(self, user_id):
        """Инициализирует стандартные категории для нового пользователя"""
        default_categories = [
            ('Еда', '🍕'),
            ('Транспорт', '🚗'),
            ('Одежда', '👕'),
            ('Развлечения', '🎬')
        ]
        
        for name, emoji in default_categories:
            self.cursor.execute('''
                INSERT OR IGNORE INTO user_categories (user_id, name, emoji)
                VALUES (?, ?, ?)
            ''', (user_id, name, emoji))
        self.conn.commit()
    
    def get_user_categories(self, user_id, include_deleted=False):
        """Получает категории пользователя"""
        query = '''
            SELECT id, name, emoji 
            FROM user_categories 
            WHERE user_id = ? 
        '''
        if not include_deleted:
            query += ' AND is_deleted = 0'
        query += ' ORDER BY created_at'
        
        self.cursor.execute(query, (user_id,))
        return self.cursor.fetchall()
    
    def add_category(self, user_id, name, emoji='➕'):
        """Добавляет новую категорию"""
        self.cursor.execute('''
            INSERT OR REPLACE INTO user_categories (user_id, name, emoji, is_deleted)
            VALUES (?, ?, ?, 0)
        ''', (user_id, name, emoji))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def delete_category(self, user_id, category_id):
        """Помечает категорию как удаленную (мягкое удаление)"""
        self.cursor.execute('''
            UPDATE user_categories 
            SET is_deleted = 1 
            WHERE id = ? AND user_id = ?
        ''', (category_id, user_id))
        self.conn.commit()
        return self.cursor.rowcount > 0
    
    # --- Методы для расходов ---
    def add_expense(self, user_id, category_id, amount):
        """Добавляет расход"""
        self.cursor.execute('''
            INSERT INTO expenses (user_id, category_id, amount)
            VALUES (?, ?, ?)
        ''', (user_id, category_id, amount))
        self.conn.commit()
    
    def get_category_stats(self, user_id, days=30):
        """Статистика по категориям за N дней"""
        self.cursor.execute('''
            SELECT uc.name || ' ' || uc.emoji as category, SUM(e.amount) as total
            FROM expenses e
            JOIN user_categories uc ON e.category_id = uc.id
            WHERE e.user_id = ? 
            AND e.created_at >= datetime('now', ?)
            AND uc.is_deleted = 0
            GROUP BY uc.id
            ORDER BY total DESC
        ''', (user_id, f'-{days} days'))
        return self.cursor.fetchall()
    
    def get_today_expenses(self, user_id):
        """Сумма расходов за сегодня"""
        self.cursor.execute('''
            SELECT SUM(amount) FROM expenses 
            WHERE user_id = ? AND date(created_at) = date('now')
        ''', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result[0] else 0
    
    def get_recent_expenses(self, user_id, limit=10):
        """Последние расходы"""
        self.cursor.execute('''
            SELECT e.amount, uc.name || ' ' || uc.emoji, e.created_at
            FROM expenses e
            JOIN user_categories uc ON e.category_id = uc.id
            WHERE e.user_id = ? AND uc.is_deleted = 0
            ORDER BY e.created_at DESC 
            LIMIT ?
        ''', (user_id, limit))
        return self.cursor.fetchall()

    def close(self):
        self.conn.close()

    def clear_user_statistics(self, user_id):
        """Полностью очищает статистику пользователя"""
        self.cursor.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
        self.conn.commit()
        return self.cursor.rowcount  

    def clear_category_statistics(self, user_id, category_id):
        """Очищает статистику по конкретной категории"""
        self.cursor.execute(
        "DELETE FROM expenses WHERE user_id = ? AND category_id = ?",
        (user_id, category_id))
        self.conn.commit()
        return self.cursor.rowcount