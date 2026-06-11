import psycopg2

conn = psycopg2.connect(
    host="aws-1-us-east-2.pooler.supabase.com",
    port=5432,
    dbname="postgres",
    user="postgres.xfkvusxbqijlguxwjbho",
    password="nHRo8FTXZSaPb9SX",
    sslmode="require"
)
print("Connected!")
conn.close()