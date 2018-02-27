import support_functions
import sqlite3

def get_processed_flightlines(proj_id):
    conn = sqlite3.connect(support_functions.STATUS_DB_LOCATION)
    c = conn.cursor()
    c.execute("SELECT * FROM flightlines WHERE processing_id IS (?)", (proj_id,))
    out = c.fetchall()
    conn.commit()
    c.close()
    return out