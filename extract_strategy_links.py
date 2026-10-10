import pandas as pd
import yt_dlp
import re
from datetime import datetime

print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 Sifting through the 1,952 videos to extract pure Strategy Code/Links...")

# Load the master database
df = pd.read_csv("/home/ubuntu/algolab/data/youtube_deep_strategy_database.csv")

# Filter for videos that likely contain code or exact strategies
keywords = ['strategy', 'python', 'code', 'github', 'algo', 'bot', 'setup']
pattern = '|'.join(keywords)
filtered_df = df[df['Title'].str.contains(pattern, case=False, na=False)]

# Sort by views to get the most proven ones, take top 10 to process quickly
top_videos = filtered_df.sort_values(by='Views', ascending=False).head(10)

ydl_opts = {
    'quiet': True,
    'no_warnings': True,
    'skip_download': True, # Do not download video
    'write_description': False
}

results = []

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    for _, row in top_videos.iterrows():
        url = row['URL']
        title = row['Title']
        try:
            info = ydl.extract_info(url, download=False)
            desc = info.get('description', '')
            
            # Find URLs
            urls = re.findall(r'(https?://[^\s]+)', desc)
            
            # Filter for code/strategy resources
            code_links = [u for u in urls if any(domain in u for domain in ['github.com', 'drive.google.com', 'colab.research', 'pastebin'])]
            
            if code_links:
                results.append({
                    "Channel": row['Channel'],
                    "Title": title,
                    "Code/Resource Links": " | ".join(code_links)
                })
        except Exception as e:
            pass

if results:
    res_df = pd.DataFrame(results)
    print("\n--- EXACT STRATEGY RESOURCES EXTRACTED ---")
    print(res_df.to_string(index=False))
else:
    print("\n❌ No external code links found in the descriptions of the top 10 videos.")
    print("Many channels paste code directly in the video or require joining a Telegram group.")

