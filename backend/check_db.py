from dotenv import load_dotenv
import os
load_dotenv()

print('=== CONFIGURACIÓN SQL-AGENT ===')
print(f'SUPABASE_URL: {os.getenv("SUPABASE_URL")}')
print()

from app.db.supabase_client import get_db_client
db = get_db_client()

print('=== TOP 10 PRODUCTOS (por unidades vendidas) ===')
items = db._get_table('ml_items', select='item_id,title,price,total_sold,category_id', order='total_sold.desc.nullslast', limit=10)
for i, item in enumerate(items, 1):
    title = item.get("title", "")[:45]
    price = item.get("price", 0) or 0
    sold = item.get("total_sold", 0) or 0
    print(f'{i:2}. {title} | ${price:,} | {sold} vendidos')
