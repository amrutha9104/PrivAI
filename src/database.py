import sqlite3
import pickle
import numpy as np
from datetime import datetime
import os

class PrivAIDatabase:
    def __init__(self, db_path="privai_users.db"):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else '.', exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS authorized_users (
                user_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                face_embedding BLOB,
                voice_embedding BLOB,
                created_at TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS privacy_settings (
                user_id TEXT PRIMARY KEY,
                blur_unknown_faces BOOLEAN DEFAULT 1,
                blur_objects BOOLEAN DEFAULT 1,
                mute_unknown_audio BOOLEAN DEFAULT 1,
                noise_suppression BOOLEAN DEFAULT 1,
                background_mode TEXT DEFAULT 'blur'
            )
        ''')
        self.conn.commit()
    
    def add_user(self, user_id, name, face_embedding, voice_embedding):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO authorized_users 
            (user_id, name, face_embedding, voice_embedding, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, name, pickle.dumps(face_embedding), 
              pickle.dumps(voice_embedding), datetime.now()))
        self.conn.commit()
    
    def get_user_face_embedding(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT face_embedding FROM authorized_users WHERE user_id=?', (user_id,))
        result = cursor.fetchone()
        return pickle.loads(result[0]) if result and result[0] else None
    
    def get_user_voice_embedding(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT voice_embedding FROM authorized_users WHERE user_id=?', (user_id,))
        result = cursor.fetchone()
        return pickle.loads(result[0]) if result and result[0] else None
    
    def get_all_authorized_face_embeddings(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id, face_embedding FROM authorized_users')
        results = cursor.fetchall()
        return [(uid, pickle.loads(emb)) for uid, emb in results if emb]

    def update_privacy_settings(self, user_id, settings):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO privacy_settings 
            (user_id, blur_unknown_faces, blur_objects, mute_unknown_audio, 
             noise_suppression, background_mode)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, settings.get('blur_unknown_faces', True),
              settings.get('blur_objects', True),
              settings.get('mute_unknown_audio', True),
              settings.get('noise_suppression', True),
              settings.get('background_mode', 'blur')))
        self.conn.commit()
    
    # ADD THIS METHOD
    def get_privacy_settings(self, user_id):
        """Retrieve privacy settings for a user"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM privacy_settings WHERE user_id=?', (user_id,))
        result = cursor.fetchone()
        if result:
            return {
                'user_id': result[0],
                'blur_unknown_faces': bool(result[1]),
                'blur_objects': bool(result[2]),
                'mute_unknown_audio': bool(result[3]),
                'noise_suppression': bool(result[4]),
                'background_mode': result[5]
            }
        return None