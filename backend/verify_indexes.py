"""
Project: APEX AI Portfolio Management System
Course: Graduation Project / Engineering Project
Team Members:
- Saleem A. S. AbuZaid
- Rashad Naghdiyev
Advisor:
Prof.Dr. Selim Akyokuş
Description:
- Project source/configuration file supporting the APEX AI Portfolio Management System.
"""
import sqlite3

def check_indexes():
    conn = sqlite3.connect('backend/apex_ai.db')
    cursor = conn.cursor()
    tables = ['price_history', 'sentiment', 'recommendation']
    
    with open('proofs/step11_query_optimization.txt', 'w', encoding='utf-8') as f:
        f.write("STEP 11: SQL QUERY OPTIMIZATION PROOF\n")
        f.write("=====================================\n\n")
        
        for table in tables:
            f.write(f"Table: {table}\n")
            cursor.execute(f"PRAGMA index_list('{table}');")
            indexes = cursor.fetchall()
            if indexes:
                for idx in indexes:
                    f.write(f" - Index Found: {idx[1]} (Unique: {idx[2]})\n")
            else:
                f.write(" - No indexes found (ERROR)\n")
            f.write("\n")
            
    conn.close()
    print("Optimization proof generated.")

if __name__ == "__main__":
    check_indexes()
