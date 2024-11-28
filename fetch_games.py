import requests
import sqlite3
import time
from typing import List, Dict, Optional
from decouple import config

class IGDBGameDatabaseFetcher:
    def __init__(self, client_id: str, access_token: str, db_path: str):
        """
        Initialize the IGDB Game Fetcher with authentication and database connection.
        
        :param client_id: Your IGDB API client ID
        :param access_token: Your IGDB API access token
        :param db_path: Path to SQLite database
        """
        self.base_url = "https://api.igdb.com/v4"
        self.headers = {
            'Client-ID': client_id,
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        self.rate_limit_delay = 0.25  # 4 requests per second
        
        # Setup database connection and create tables
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self._create_tables()
    
    def _create_tables(self):
        """
        Create necessary tables in the SQLite database.
        """
        # Main tables (same as previous implementation)
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY,
            name TEXT,
            summary TEXT,
            first_release_date INTEGER,
            total_rating REAL,
            total_rating_count INTEGER,
            cover_url TEXT,
            category INTEGER
        )''')
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS alternative_names (
            id INTEGER PRIMARY KEY,
            game_id INTEGER,
            name TEXT,
            FOREIGN KEY(game_id) REFERENCES games(id)
        )''')
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS franchises (
            id INTEGER PRIMARY KEY,
            game_id INTEGER,
            franchise_id INTEGER,
            franchise_name TEXT,
            FOREIGN KEY(game_id) REFERENCES games(id)
        )''')
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS genres (
            id INTEGER PRIMARY KEY,
            game_id INTEGER,
            genre_name TEXT,
            FOREIGN KEY(game_id) REFERENCES games(id)
        )''')
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS platforms (
            id INTEGER PRIMARY KEY,
            game_id INTEGER,
            platform_name TEXT,
            FOREIGN KEY(game_id) REFERENCES games(id)
        )''')
        
        # Pagination metadata table
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS pagination_metadata (
            id INTEGER PRIMARY KEY,
            query TEXT UNIQUE,
            total_games INTEGER DEFAULT 0,
            last_offset INTEGER DEFAULT 0,
            last_fetch_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        
        self.conn.commit()
    
    def count_total_games(self, query: Optional[str] = None) -> int:
        """
        Count the total number of games matching the query.
        
        :param query: Optional query string for filtering
        :return: Total number of games
        """
        endpoint = f"{self.base_url}/games/count"
        body = "fields id;"
        
        if query:
            body += f"{query}"
        
        try:
            time.sleep(self.rate_limit_delay)
            
            response = requests.post(
                endpoint, 
                headers=self.headers, 
                data=body
            )
            
            response.raise_for_status()
            return response.json().get('count', 0)
        
        except requests.RequestException as e:
            print(f"Error counting games: {e}")
            return 0
    
    def fetch_games(self, 
                    query: Optional[str] = None, 
                    limit: int = 50,
                    offset: int = 0) -> List[Dict]:
        """
        Fetch games from IGDB API with pagination support.
        
        :param query: Optional IGDB query string
        :param limit: Number of results per page
        :param offset: Pagination offset
        :return: List of game dictionaries
        """
        endpoint = f"{self.base_url}/games"
        body = f"""
        fields 
            name, 
            summary, 
            category,
            first_release_date, 
            total_rating, 
            total_rating_count, 
            alternative_names.name, 
            franchise.name,
            genres.name,
            platforms.name,
            cover.url;
        """
        
        if query:
            body += f"{query}"
        
        body += f" limit {limit}; offset {offset};"
        
        try:
            # Rate limiting
            time.sleep(self.rate_limit_delay)
            
            # Make the request
            response = requests.post(
                endpoint, 
                headers=self.headers, 
                data=body
            )
            
            # Check for successful response
            response.raise_for_status()
            
            return response.json()
        
        except requests.RequestException as e:
            print(f"Error fetching games: {e}")
            return []
    
    def fetch_all_games(self, 
                        query: Optional[str] = None, 
                        page_size: int = 50) -> int:
        """
        Fetch and store all games with improved pagination.
        
        :param query: Optional query string for filtering
        :param page_size: Number of games to fetch per page
        :return: Total number of games fetched
        """
        # Prepare query string for metadata tracking
        query_key = query or "all_games"
        
        # Count total games
        total_games = self.count_total_games(query)
        if total_games == 0:
            print("No games found matching the query.")
            return 0
        
        # Update or insert pagination metadata
        self.cursor.execute('''
        INSERT OR REPLACE INTO pagination_metadata 
        (query, total_games, last_offset) 
        VALUES (?, ?, 0)
        ''', (query_key, total_games))
        
        total_games_fetched = 0
        current_offset = 0
        
        while current_offset < total_games:            
            # Fetch a page of games
            games = self.fetch_games(
                query=query, 
                limit=page_size, 
                offset=current_offset
            )
            
            # Break if no more games
            if not games:
                break
            
            # Insert fetched games
            self.insert_games(games)
            
            # Update tracking
            total_games_fetched += len(games)
            current_offset += page_size
            print(f'{total_games_fetched} games fetched')

            # Update last offset in metadata
            self.cursor.execute('''
            UPDATE pagination_metadata 
            SET last_offset = ?, last_fetch_timestamp = CURRENT_TIMESTAMP 
            WHERE query = ?
            ''', (current_offset, query_key))
            
            self.conn.commit()
            
            print(f"Fetched {total_games_fetched} / {total_games} games")
        
        return total_games_fetched
    
    def insert_games(self, games: List[Dict]):
        """
        Insert fetched games into SQLite database.
        """
        for game in games:
            # Insert main game data
            self.cursor.execute('''
            INSERT OR REPLACE INTO games 
            (id, name, summary, first_release_date, total_rating, total_rating_count, cover_url, category) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                game.get('id'),
                game.get('name'),
                game.get('summary'),
                game.get('first_release_date'),
                game.get('total_rating'),
                game.get('total_rating_count'),
                game.get('cover_url'),
                game.get('category')
            ))
            
            # Insert alternative names
            if 'alternative_names' in game:
                for alt_name in game.get('alternative_names', []):
                    self.cursor.execute('''
                    INSERT OR REPLACE INTO alternative_names 
                    (game_id, name) VALUES (?, ?)
                    ''', (game['id'], alt_name.get('name')))
            
            # Insert franchise
            if 'franchise' in game:
                self.cursor.execute('''
                INSERT OR REPLACE INTO franchises 
                (game_id, franchise_id, franchise_name) VALUES (?, ?, ?)
                ''', (
                    game['id'], 
                    game.get('franchise', {}).get('id'), 
                    game.get('franchise', {}).get('name')
                ))
            
            # Insert genres
            if 'genres' in game:
                for genre in game.get('genres', []):
                    self.cursor.execute('''
                    INSERT OR REPLACE INTO genres 
                    (game_id, genre_name) VALUES (?, ?)
                    ''', (game['id'], genre.get('name')))
            
            # Insert platforms
            if 'platforms' in game:
                for platform in game.get('platforms', []):
                    self.cursor.execute('''
                    INSERT OR REPLACE INTO platforms 
                    (game_id, platform_name) VALUES (?, ?)
                    ''', (game['id'], platform.get('name')))
        
        # Commit the transaction
        self.conn.commit()
    
    def close_connection(self):
        """
        Close the database connection.
        """
        self.conn.close()

def main():
    fetcher = IGDBGameDatabaseFetcher(
        config('CLIENT_ID'), 
        config('ACCESS_TOKEN'), 
        config('SQLITE_DATABASE_PATH')
    )
    
    try:
        total_fetched = fetcher.fetch_all_games(
            query=' where version_parent = null & (status = null | status = (0,4,5,8)) & category=(0,1,2,4,6,7,8,9,10,11);',
            page_size=500  
        )
        
        print(f"Total games fetched: {total_fetched}")
    
    finally:
        fetcher.close_connection()

if __name__ == "__main__":
    main()