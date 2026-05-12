#!/usr/bin/env python3
"""
Update Team table schema for Round 3 Memory Grid enhancements.
Adds color and selected_theme_ids columns if they don't exist.
"""

from app.database import engine
import sqlalchemy as sa

def check_and_update_schema():
    """Check current schema and add missing columns for Round 3."""
    inspector = sa.inspect(engine)
    columns = inspector.get_columns('teams')
    
    print('Current Team table columns:')
    for col in columns:
        print(f'  - {col["name"]}: {col["type"]}')
    
    # Check if color column exists
    color_exists = any(col['name'] == 'color' for col in columns)
    selected_theme_ids_exists = any(col['name'] == 'selected_theme_ids' for col in columns)
    
    print(f'\nColor column exists: {color_exists}')
    print(f'Selected_theme_ids column exists: {selected_theme_ids_exists}')
    
    if not color_exists or not selected_theme_ids_exists:
        print('\nNeed to update database schema...')
        # For SQLite, we can use ALTER TABLE
        with engine.connect() as conn:
            if not color_exists:
                print('Adding color column...')
                conn.execute(sa.text('ALTER TABLE teams ADD COLUMN color VARCHAR'))
            if not selected_theme_ids_exists:
                print('Adding selected_theme_ids column...')
                conn.execute(sa.text('ALTER TABLE teams ADD COLUMN selected_theme_ids TEXT'))
            conn.commit()
        print('Database schema updated successfully!')
    else:
        print('\nDatabase schema already up to date.')
    
    # Verify the update
    print('\nVerifying updated schema...')
    columns = inspector.get_columns('teams')
    for col in columns:
        print(f'  - {col["name"]}: {col["type"]}')

if __name__ == '__main__':
    check_and_update_schema()