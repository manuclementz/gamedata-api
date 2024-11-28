import sqlite3
from flask import Flask, request, jsonify, render_template
from typing import List, Dict
from decouple import config

class GameSearchDatabase:
    def __init__(self, db_path: str):
        """
        Initialize database connection with full-text search setup.
        
        :param db_path: Path to SQLite database
        """
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._setup_fts()
    
    def _setup_fts(self):
        """
        Setup Full-Text Search (FTS) virtual table for efficient searching.
        """
        # Create FTS table with games and alternative names combined
        self.cursor.executescript('''
        -- Drop existing FTS table if it exists
        DROP TABLE IF EXISTS games_fts;

        -- Create unified FTS table
        CREATE VIRTUAL TABLE games_fts USING fts5(
            id,
            name,
            alternative_names,  -- All alternative names concatenated
            first_release_date,
            total_rating_count
        );
        ''')
        
        # Populate the FTS table
        self._populate_games_fts()
        self.conn.commit()
    
    def _populate_games_fts(self):
        """
        Populate full-text search table with games and their alternative names.
        """
        # Insert data with concatenated alternative names
        self.cursor.execute('''
        INSERT INTO games_fts (id, name, alternative_names, first_release_date, total_rating_count)
        SELECT 
            g.id, 
            g.name, 
            COALESCE(GROUP_CONCAT(alt.name, ', '), ''),  -- Concatenate alternative names            
            g.first_release_date,
            g.total_rating_count
        FROM 
            games g
        LEFT JOIN 
            alternative_names alt ON g.id = alt.game_id
        GROUP BY 
            g.id        
        ''')
    
    def search_games(self, query: str, limit: int = 10) -> List[Dict]:
        query = self.escape_fts5_query(query)
        """
        Search games by name or alternative name.
        
        :param query: Search term.
        :param limit: Maximum number of results.
        :return: List of matching games.
        """
        self.cursor.execute('''
        SELECT id, name, first_release_date, total_rating_count
        FROM games_fts
        WHERE games_fts MATCH ?
        ORDER BY total_rating_count DESC, rank DESC
        LIMIT ?                            
        ''', (query + '*', limit))
        
        return [dict(row) for row in self.cursor.fetchall()]
    
    def escape_fts5_query(self, query):
        """
        Escape special characters for SQLite FTS5 MATCH query
        """
        query = ''.join(char if char.isalnum() or char.isspace() else ' ' for char in query)
        
        # Wrap in quotes to prevent injection and handle special terms
        return f'{query}'

# Flask API setup
app = Flask(__name__)
game_db = GameSearchDatabase(config('SQLITE_DATABASE_PATH'))

@app.route('/api/search', methods=['GET'])
def search_games():
    """
    API endpoint for searching games.
    
    Query parameters:
    - q: Search query
    - limit: Maximum number of results (default 10)
    """
    query = request.args.get('q', '')
    limit = int(request.args.get('limit', 10))
    
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400
    
    try:
        results = game_db.search_games(query, limit)
        return jsonify(results)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/game/<int:game_id>', methods=['GET'])
def get_game_details(game_id):
    """
    API endpoint to get detailed game information.
    """
    try:
        # Fetch game details with associated data
        game_db.cursor.execute('''
        SELECT g.*, 
               GROUP_CONCAT(DISTINCT gen.genre_name) as genres,
               GROUP_CONCAT(DISTINCT p.platform_name) as platforms,
               GROUP_CONCAT(DISTINCT alt.name) as alternative_names,
               f.franchise_name
        FROM games g
        LEFT JOIN genres gen ON g.id = gen.game_id
        LEFT JOIN platforms p ON g.id = p.game_id
        LEFT JOIN alternative_names alt ON g.id = alt.game_id
        LEFT JOIN franchises f ON g.id = f.game_id
        WHERE g.id = ?
        GROUP BY g.id
        ''', (game_id,))
        
        game = game_db.cursor.fetchone()
        
        if not game:
            return jsonify({"error": "Game not found"}), 404
        
        return jsonify(dict(game))
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/search', methods=['GET'])
def search_page():
    """
    Serve a simple HTML page for live game searches.
    """
    return render_template('search.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
