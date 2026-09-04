#!/usr/bin/env python3
"""Export SQLite schema/data as a SQL file suitable for review/import in phpMyAdmin."""
import argparse, sqlite3
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('database',type=Path);p.add_argument('-o','--output',type=Path,required=True);a=p.parse_args()
 if not a.database.is_file(): p.error('database not found')
 con=sqlite3.connect(a.database); con.execute('PRAGMA integrity_check').fetchone(); sql='-- Generated export; review before importing into MySQL/MariaDB.\nSET NAMES utf8mb4;\n'
 for line in con.iterdump():
  if line.startswith('BEGIN') or line.startswith('COMMIT'): continue
  sql += line.replace('"','`')+'\n'
 con.close(); a.output.write_text(sql,encoding='utf-8'); print(f'Exported {a.output} ({a.output.stat().st_size} bytes)')
if __name__=='__main__':main()
