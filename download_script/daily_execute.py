import os
import time
import schedule

def run_script(script_name):
    print(f"実行中: {script_name}")
    os.system(f"python {script_name}")

# 実行するスクリプトと時間を指定
scripts_to_run = [
    {"name": "download_script/stock_download.py", "time": "04:00"},
    {"name": "download_script/tdnet_download.py", "time": "03:00"},
    {"name": "download_script/news_download.py", "time": "02:00"}
]

# スケジュールを設定
for script in scripts_to_run:
    schedule.every().day.at(script["time"]).do(run_script, script["name"])

# メインループ
while True:
    schedule.run_pending()
    time.sleep(60)